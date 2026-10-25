"""Pipeline de "Aplicar mejora": recalibra todos los fotogramas YA
ESCANEADOS de un proyecto contra el fotograma 0 (fijo), usando el registro
robusto por perforaciones (ver vision/robust_registration.py).

Es un paso de POST-procesamiento, separado del escaneo en vivo
(core/scan_controller.py): corre sobre los archivos ya guardados en
`raw/`, no requiere cámara ni motor conectados. Pensado para el pedido
del cliente: que la secuencia final no "gire" entre fotogramas, comparando
cada uno contra una única referencia fija en vez de depender únicamente
del par de perforaciones elegido durante el escaneo en vivo.

Pensado para películas enteras (miles de fotogramas, posiblemente horas
de proceso en una Raspberry Pi): cada fotograma se guarda de forma
ATÓMICA apenas se procesa (nunca queda un archivo a medio escribir si el
proceso se corta), y si se vuelve a llamar sobre un proyecto que ya tiene
fotogramas mejorados en disco, esos se SALTEAN automáticamente — abrir de
nuevo el proyecto y tocar "Aplicar mejora" retoma donde quedó, no vuelve
a arrancar de cero.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

import cv2

from ..storage.raw_dng_writer import ProjectStorage
from ..vision.perforation_detection import SearchZone, detect_perforations
from ..vision.robust_registration import (
    RobustAlignment,
    apply_robust_alignment,
    build_straightening_matrix,
    compute_precise_alignment,
    measure_absolute_tilt,
    rotate_output,
)
from ..vision.stabilization import ReferenceBox

OUTPUT_DIR_NAME = "mejorado"
FRAME_INDEX_PATTERN = re.compile(r"frame_(\d+)")
TMP_PREFIX = ".tmp_"


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
    # True si este fotograma YA estaba resuelto de una corrida anterior
    # (se encontró su archivo en mejorado/) y no se volvió a procesar —
    # permite que la UI muestre el progreso real del proyecto sin pagar
    # el costo de recalcular lo que ya estaba hecho.
    already_done: bool = False


def _frame_index_from_filename(name: str, fallback: int) -> int:
    match = FRAME_INDEX_PATTERN.search(name)
    return int(match.group(1)) if match else fallback


def _cleanup_stray_temp_files(output_dir: Path) -> None:
    """Restos de una corrida anterior cortada a mitad de una escritura:
    el archivo final (sin el prefijo) nunca llega a existir si el proceso
    se corta durante `cv2.imwrite`, así que el único rastro es el
    temporal — se borra para no dejar basura acumulándose."""
    for stray in output_dir.glob(f"{TMP_PREFIX}frame_*_mejorado.png"):
        stray.unlink(missing_ok=True)


def apply_improvement(
    storage: ProjectStorage,
    left_zone: SearchZone,
    right_zone: SearchZone,
    reference_box: ReferenceBox,
    ecc_zones: List[SearchZone] | None = None,
    rotation_deg: int = 0,
    max_frames: Optional[int] = None,
    on_frame_processed: Optional[Callable[[ImprovedFrameResult], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
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

    `rotation_deg`: rotación final (múltiplo de 90°, antihoraria) para
    presentar el fotograma en orientación de lectura normal — ver
    `vision/robust_registration.rotate_output`. Se aplica DESPUÉS del
    recorte/alineación, como último paso antes de guardar.

    Pensado para películas enteras (miles de fotogramas):

    - `max_frames`: procesa como máximo esta cantidad de fotogramas
      NUEVOS en esta llamada (los ya resueltos de corridas anteriores no
      cuentan) — permite fraccionar un rollo largo en tandas, en vez de
      bloquear horas de una sola vez.
    - `on_frame_processed`: callback invocado por cada fotograma, tanto
      los recién procesados como los que ya estaban hechos
      (`already_done=True`) — para que la UI pueda mostrar el progreso
      real del proyecto completo, no solo de esta tanda.
    - `should_stop`: callback sin argumentos que, si devuelve True, corta
      el proceso ANTES de arrancar el próximo fotograma nuevo (cooperativo:
      nunca interrumpe a mitad de un fotograma ya empezado).
    - Resumible por diseño: si un fotograma ya tiene su archivo en
      `mejorado/` (de una corrida anterior, completa o cortada a mitad de
      camino), se saltea sin recalcularlo. Cada fotograma nuevo se escribe
      de forma ATÓMICA (a un archivo temporal + rename), así que un corte
      de luz/proceso a mitad de un `cv2.imwrite` nunca deja un archivo
      corrupto con el nombre final — en el peor caso, ese fotograma queda
      pendiente y se recalcula en la próxima corrida.
    """
    raw_files = sorted(p for p in storage.raw_dir.iterdir() if p.is_file())
    if not raw_files:
        return []

    output_dir = storage.project_dir / OUTPUT_DIR_NAME
    output_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_stray_temp_files(output_dir)

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
    new_frames_processed = 0
    for position, raw_path in enumerate(raw_files):
        frame_index = _frame_index_from_filename(raw_path.name, position)
        output_path = output_dir / f"frame_{frame_index:05d}_mejorado.png"

        if output_path.exists():
            result = ImprovedFrameResult(frame_index, raw_path, output_path, None, None, tilt, already_done=True)
            results.append(result)
            if on_frame_processed:
                on_frame_processed(result)
            continue

        if should_stop is not None and should_stop():
            break
        if max_frames is not None and new_frames_processed >= max_frames:
            break

        frame = cv2.imread(str(raw_path))
        if frame is None:
            result = ImprovedFrameResult(frame_index, raw_path, None, None, "No se pudo leer el archivo.", tilt)
            results.append(result)
            new_frames_processed += 1
            if on_frame_processed:
                on_frame_processed(result)
            continue

        perfs = detect_perforations(frame, left_zone, right_zone)
        alignment = compute_precise_alignment(
            frame, reference_frame, perfs, reference_perfs, left_zone, right_zone, ecc_zones=ecc_zones
        )
        if alignment is None:
            result = ImprovedFrameResult(
                frame_index,
                raw_path,
                None,
                None,
                "No se encontraron suficientes perforaciones para alinear.",
                tilt,
            )
            results.append(result)
            new_frames_processed += 1
            if on_frame_processed:
                on_frame_processed(result)
            continue

        improved = apply_robust_alignment(frame, alignment.matrix, reference_box)
        if rotation_deg % 360 != 0:
            improved = rotate_output(improved, rotation_deg)

        # Escritura atómica: se escribe con nombre temporal y recién se
        # renombra al nombre final cuando el archivo ya está completo en
        # disco — un corte a mitad de camino deja (a lo sumo) el temporal
        # huérfano, nunca un "frame_XXXXX_mejorado.png" corrupto.
        tmp_path = output_dir / f"{TMP_PREFIX}frame_{frame_index:05d}_mejorado.png"
        cv2.imwrite(str(tmp_path), improved)
        tmp_path.rename(output_path)

        result = ImprovedFrameResult(frame_index, raw_path, output_path, alignment, None, tilt)
        results.append(result)
        new_frames_processed += 1
        if on_frame_processed:
            on_frame_processed(result)

    return results
