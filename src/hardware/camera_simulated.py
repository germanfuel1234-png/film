"""Cámara simulada: reproduce una carpeta de fotogramas de ejemplo.

Es el driver por defecto mientras no esté confirmado qué 2 cámaras físicas
va a usar el cliente (ver proyecto_film/ARQUITECTURA.md §3). Permite
desarrollar y probar todo el pipeline (visión, estabilización, storage, UI)
sin hardware conectado, igual que el prototipo original corría en modo
"SIMULACIÓN".
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import cv2
import numpy as np

from .camera_base import CameraDriver, CameraState, CameraStatus, CapturedFrame, CameraConnectionError

DEFAULT_SAMPLE_DIR = Path(__file__).resolve().parents[2] / "assets" / "sample_frames"


class SimulatedCamera(CameraDriver):
    def __init__(self, sample_dir: Path | str = DEFAULT_SAMPLE_DIR, loop: bool = True) -> None:
        super().__init__()
        self._sample_dir = Path(sample_dir)
        self._loop = loop
        self._frames: List[Path] = []
        self._cursor = 0

    def connect(self) -> None:
        self._frames = sorted(self._sample_dir.glob("roll_*.png"))
        if not self._frames:
            # fallback: cualquier imagen disponible en la carpeta de muestras
            # (fotos reales del cliente vienen en .JPG, no solo .png sintético)
            patterns = ("*.png", "*.PNG", "*.jpg", "*.JPG", "*.jpeg", "*.JPEG")
            found = set()
            for pattern in patterns:
                found.update(self._sample_dir.glob(pattern))
            self._frames = sorted(found)
        if not self._frames:
            self._state = CameraState(
                status=CameraStatus.ERROR,
                last_error=f"No se encontraron fotogramas de ejemplo en {self._sample_dir}",
            )
            raise CameraConnectionError(self._state.last_error)
        self._cursor = 0
        self._state = CameraState(status=CameraStatus.CONNECTED, extra={"mode": "simulated", "n_frames": len(self._frames)})

    def disconnect(self) -> None:
        self._state = CameraState(status=CameraStatus.DISCONNECTED)

    def _current_path(self) -> Path:
        if not self._frames:
            raise CameraConnectionError("SimulatedCamera no está conectada: llamá a connect() primero.")
        idx = self._cursor % len(self._frames)
        if not self._loop and self._cursor >= len(self._frames):
            idx = len(self._frames) - 1
        return self._frames[idx]

    def get_preview_frame(self) -> np.ndarray:
        # A propósito, a la misma resolución que trigger_capture(): las
        # zonas de búsqueda y el encuadre de referencia se calibran mirando
        # el preview, pero el recorte final se aplica sobre la imagen
        # guardada (resolución completa) — si difieren, las coordenadas
        # calibradas quedan mal escaladas. Ver nota en camera_industrial.py
        # y camera_dslr.py: con cámaras reales, cuyo preview SÍ suele venir
        # en menor resolución que la captura, hay que reescalar las
        # coordenadas en vez de asumirlas iguales.
        img = cv2.imread(str(self._current_path()), cv2.IMREAD_COLOR)
        if img is None:
            raise CameraConnectionError(f"No se pudo leer el fotograma de ejemplo: {self._current_path()}")
        return img

    def trigger_capture(self, frame_index: int) -> CapturedFrame:
        path = self._current_path()
        img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if img is None:
            raise CameraConnectionError(f"No se pudo leer el fotograma de ejemplo: {path}")
        ok, buf = cv2.imencode(".png", img)
        if not ok:
            raise CameraConnectionError("Fallo al codificar el fotograma simulado.")
        self._cursor += 1
        h, w = img.shape[:2]
        return CapturedFrame(
            raw_bytes=buf.tobytes(),
            file_extension=".sim.png",  # marcado explícitamente como NO-RAW real; ver storage/README.md
            width=w,
            height=h,
            frame_index=frame_index,
        )
