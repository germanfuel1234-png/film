"""Compone varios fotogramas ya mejorados (carpeta `mejorado/`) en una
sola imagen apilados verticalmente, uno debajo del otro, para verificar
de un vistazo que calzan sin saltos — el pedido del cliente de ver la
secuencia final "como si fuera una línea recta de película", igual a
cómo la presenta el video de referencia que mandó (ver
docs/referencia_gugusseroller si hace falta más contexto).

Es solo una vista de control de calidad: no se usa para exportar nada,
no modifica ni reemplaza los archivos de `mejorado/`.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

from ..storage.raw_dng_writer import ProjectStorage
from .post_stabilization import OUTPUT_DIR_NAME


def list_improved_frames(storage: ProjectStorage) -> List[Path]:
    """Archivos de `mejorado/` ordenados, o lista vacía si todavía no se
    corrió "Aplicar mejora" sobre este proyecto."""
    output_dir = storage.project_dir / OUTPUT_DIR_NAME
    if not output_dir.exists():
        return []
    return sorted(output_dir.glob("frame_*_mejorado.png"))


def build_filmstrip(frame_paths: List[Path], start: int = 0, count: int = 6) -> Optional[np.ndarray]:
    """Apila verticalmente hasta `count` fotogramas consecutivos de
    `frame_paths` a partir de `start`, en el mismo orden en que aparecen
    en la película (uno arriba, el siguiente debajo, etc).

    Todos los fotogramas de `mejorado/` de una misma corrida comparten el
    mismo tamaño (vienen del mismo `reference_box` + rotación), así que
    el apilado no necesita escalar ni recortar nada; si alguno llegara a
    tener un ancho distinto (otra corrida, otra calibración) se descarta
    en vez de romper el apilado.
    """
    selected = frame_paths[start : start + count]
    if not selected:
        return None

    frames = [cv2.imread(str(p)) for p in selected]
    frames = [f for f in frames if f is not None]
    if not frames:
        return None

    width = frames[0].shape[1]
    frames = [f for f in frames if f.shape[1] == width]
    if not frames:
        return None

    return cv2.vconcat(frames)
