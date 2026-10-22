"""Estimación de espacio en disco para un proyecto de escaneo.

No hay forma de saber el tamaño exacto de un RAW/DNG sin la cámara real
(depende del sensor, la compresión y el formato exacto que entregue el
fabricante) — por eso se usan valores aproximados por tipo de cámara como
punto de partida, y en cuanto hay fotogramas guardados se usa el tamaño
PROMEDIO REAL observado en disco, que es mucho más preciso que cualquier
estimación teórica.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from ..storage.raw_dng_writer import ProjectStorage

# Tamaños aproximados por fotograma, en bytes — valores de referencia para
# cuando todavía no se guardó ningún fotograma real, NO son exactos:
# dependen del sensor y formato concreto de cada cámara.
APPROX_BYTES_PER_FRAME = {
    "industrial": 1920 * 1200 * 1,  # mono 8-bit sin comprimir (~2.3 MB) — resolución típica mencionada por el cliente
    "dslr": 25 * 1024 * 1024,  # RAW/CR2 típico de una DSLR ~18MP (~25 MB)
    "simulated": 2 * 1024 * 1024,  # PNG sintético de prueba, no representativo de un RAW real
}
FALLBACK_BYTES_PER_FRAME = APPROX_BYTES_PER_FRAME["simulated"]


@dataclass
class StorageEstimate:
    frames_saved: int
    bytes_used: int
    average_bytes_per_frame: int
    is_estimate: bool  # True si average_bytes_per_frame es una suposición (todavía no se guardó nada real)
    expected_frame_count: int
    estimated_total_bytes: int
    free_disk_bytes: int
    output_dir: Path

    def fits_on_disk(self) -> bool:
        return self.estimated_total_bytes <= self.free_disk_bytes

    def remaining_bytes_needed(self) -> int:
        return max(0, self.estimated_total_bytes - self.bytes_used)


def human_size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


def estimate_storage(storage: ProjectStorage, expected_frame_count: int, camera_type: str) -> StorageEstimate:
    """Calcula cuánto espacio va a ocupar (o ya ocupa) un proyecto.

    `expected_frame_count` lo completa el operador (cuántos fotogramas
    tiene el rollo que está por escanear); si ya hay fotogramas guardados,
    el tamaño promedio se calcula sobre esos archivos reales en vez de
    usar la tabla de aproximaciones.
    """
    raw_files = [p for p in storage.raw_dir.iterdir() if p.is_file()]
    frames_saved = len(raw_files)
    bytes_used = sum(p.stat().st_size for p in raw_files)

    if frames_saved > 0:
        average_bytes_per_frame = bytes_used // frames_saved
        is_estimate = False
    else:
        average_bytes_per_frame = APPROX_BYTES_PER_FRAME.get(camera_type, FALLBACK_BYTES_PER_FRAME)
        is_estimate = True

    total_frames = max(expected_frame_count, frames_saved)
    estimated_total_bytes = average_bytes_per_frame * total_frames

    free_disk_bytes = shutil.disk_usage(storage.project_dir).free

    return StorageEstimate(
        frames_saved=frames_saved,
        bytes_used=bytes_used,
        average_bytes_per_frame=average_bytes_per_frame,
        is_estimate=is_estimate,
        expected_frame_count=expected_frame_count,
        estimated_total_bytes=estimated_total_bytes,
        free_disk_bytes=free_disk_bytes,
        output_dir=storage.project_dir,
    )
