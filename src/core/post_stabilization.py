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
from ..vision.robust_registration import RobustAlignment, apply_robust_alignment, compute_robust_alignment
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


def _frame_index_from_filename(name: str, fallback: int) -> int:
    match = FRAME_INDEX_PATTERN.search(name)
    return int(match.group(1)) if match else fallback


def apply_improvement(
    storage: ProjectStorage,
    left_zone: SearchZone,
    right_zone: SearchZone,
    reference_box: ReferenceBox,
) -> List[ImprovedFrameResult]:
    """Recorre `storage.raw_dir` (ordenado), usa el PRIMER archivo como
    referencia fija (fotograma 0) y alinea el resto contra esa única
    referencia. Guarda cada resultado en `<project_dir>/mejorado/` con el
    sufijo "_mejorado", sin tocar los archivos originales en `raw/`.
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
    reference_perfs = detect_perforations(reference_frame, left_zone, right_zone)

    results: List[ImprovedFrameResult] = []
    for position, raw_path in enumerate(raw_files):
        frame_index = _frame_index_from_filename(raw_path.name, position)
        frame = cv2.imread(str(raw_path))
        if frame is None:
            results.append(ImprovedFrameResult(frame_index, raw_path, None, None, "No se pudo leer el archivo."))
            continue

        perfs = detect_perforations(frame, left_zone, right_zone)
        alignment = compute_robust_alignment(perfs, reference_perfs)
        if alignment is None:
            results.append(
                ImprovedFrameResult(
                    frame_index, raw_path, None, None, "No se encontraron suficientes perforaciones para alinear."
                )
            )
            continue

        improved = apply_robust_alignment(frame, alignment.matrix, reference_box)
        output_path = output_dir / f"frame_{frame_index:05d}_mejorado.png"
        cv2.imwrite(str(output_path), improved)
        results.append(ImprovedFrameResult(frame_index, raw_path, output_path, alignment, None))

    return results
