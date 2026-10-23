"""Pipeline de "Aplicar mejora": recalibra todos los fotogramas YA
ESCANEADOS de un proyecto contra el fotograma 0 (fijo), usando el registro
robusto por perforaciones (ver vision/robust_registration.py).

Es un paso de POST-procesamiento, separado del escaneo en vivo
(core/scan_controller.py): corre sobre los archivos ya guardados en
`raw/`, no requiere cámara ni motor conectados. Pensado para el pedido
del cliente: que la secuencia final no "gire" entre fotogramas, comparando
cada uno contra una única referencia fija en vez de depender únicamente
del par de perforaciones elegido durante el escaneo en vivo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import cv2

from ..storage.raw_dng_writer import ProjectStorage
from ..vision.perforation_detection import SearchZone, detect_perforations
from ..vision.robust_registration import (
    RobustAlignment,
    apply_robust_alignment,
    build_straightening_matrix,
    compute_precise_alignment,
    measure_absolute_tilt,
)
from ..vision.stabilization import ReferenceBox

OUTPUT_DIR_NAME = "mejorado"
FRAME_INDEX_PATTERN = re.compile(r"frame_(\d+)")


@dataclass
class ImprovedFrameResult:
    frame_index: int
    source_path: Path
    output_path: Optional[Path]
    alignment: Optional[RobustAlignment]
    error: Optional[str]
    # Inclinación absoluta que traía el fotograma 0 y que se corrigió para
    # definir el cero "recto para el ojo humano" (igual en todos los
    # resultados de una misma corrida; se repite por comodidad de la UI).
    reference_tilt_corrected_deg: Optional[float] = None


def _frame_index_from_filename(name: str, fallback: int) -> int:
    match = FRAME_INDEX_PATTERN.search(name)
    return int(match.group(1)) if match else fallback


def apply_improvement(
    storage: ProjectStorage,
    left_zone: SearchZone,
    right_zone: SearchZone,
    reference_box: ReferenceBox,
    ecc_zones: List[SearchZone] | None = None,
) -> List[ImprovedFrameResult]:
    """Recorre `storage.raw_dir` (ordenado), usa el PRIMER archivo como
    referencia fija (fotograma 0) y alinea el resto contra esa única
    referencia. Guarda cada resultado en `<project_dir>/mejorado/` con el
    sufijo "_mejorado", sin tocar los archivos originales en `raw/`.

    El fotograma 0 no se toma como viene: primero se mide su inclinación
    ABSOLUTA (recta ajustada por las perforaciones) y se lo endereza. Si
    no, toda la película hereda la inclinación con la que quedó esa
    primera toma — estable entre cuadros, pero torcida para el ojo.

    `ecc_zones`: máscara para el refinamiento ECC — por defecto
    `[left_zone, right_zone]` (solo perforaciones, lo que mejor funcionó
    al medirlo); ver advertencia en
    `vision/robust_registration.refine_alignment_with_ecc` antes de
    ampliar esto.
    """
    raw_files = sorted(p for p in storage.raw_dir.iterdir() if p.is_file())
    if not raw_files:
        return []

    output_dir = storage.project_dir / OUTPUT_DIR_NAME
    output_dir.mkdir(parents=True, exist_ok=True)

    reference_frame = cv2.imread(str(raw_files[0]))
    if reference_frame is None:
        return [
            ImprovedFrameResult(0, raw_files[0], None, None, "No se pudo leer el fotograma 0 (referencia).")
        ]

    # Cero absoluto: enderezar el fotograma 0 antes de usarlo de referencia.
    raw_reference_perfs = detect_perforations(reference_frame, left_zone, right_zone)
    tilt = measure_absolute_tilt(raw_reference_perfs)
    if tilt is not None and abs(tilt) > 1e-4:
        straighten = build_straightening_matrix(tilt, reference_frame.shape)
        height, width = reference_frame.shape[:2]
        reference_frame = cv2.warpAffine(
            reference_frame, straighten, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
        )
    reference_perfs = detect_perforations(reference_frame, left_zone, right_zone)

    results: List[ImprovedFrameResult] = []
    for position, raw_path in enumerate(raw_files):
        frame_index = _frame_index_from_filename(raw_path.name, position)
        frame = cv2.imread(str(raw_path))
        if frame is None:
            results.append(
                ImprovedFrameResult(frame_index, raw_path, None, None, "No se pudo leer el archivo.", tilt)
            )
            continue

        perfs = detect_perforations(frame, left_zone, right_zone)
        alignment = compute_precise_alignment(
            frame, reference_frame, perfs, reference_perfs, left_zone, right_zone, ecc_zones=ecc_zones
        )
        if alignment is None:
            results.append(
                ImprovedFrameResult(
                    frame_index,
                    raw_path,
                    None,
                    None,
                    "No se encontraron suficientes perforaciones para alinear.",
                    tilt,
                )
            )
            continue

        improved = apply_robust_alignment(frame, alignment.matrix, reference_box)
        output_path = output_dir / f"frame_{frame_index:05d}_mejorado.png"
        cv2.imwrite(str(output_path), improved)
        results.append(ImprovedFrameResult(frame_index, raw_path, output_path, alignment, None, tilt))

    return results
