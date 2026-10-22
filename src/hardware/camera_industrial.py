"""Driver para cámara industrial GenICam/GigE Vision (ej. Huateng Vision).

Usa la librería genérica `harvesters`, que habla el estándar GenICam y por
lo tanto funciona con la mayoría de las cámaras industriales (Huateng,
Basler, FLIR, Lucid, etc.) sin atarse a un SDK de fabricante específico —
razonable mientras el cliente no confirme el modelo exacto (ver
proyecto_film/ARQUITECTURA.md §3).

Requiere un archivo .cti (GenTL producer) provisto por el fabricante de la
cámara. Si no está disponible, connect() falla con un error explícito en
vez de fallar en silencio.
"""

from __future__ import annotations

import os
from typing import Optional

import cv2
import numpy as np

from .camera_base import CameraDriver, CameraState, CameraStatus, CapturedFrame, CameraConnectionError

# Variable de entorno estándar para el producer GenTL (.cti) del fabricante.
CTI_ENV_VAR = "GENICAM_GENTL64_PATH"


class IndustrialCamera(CameraDriver):
    """Cámara industrial monocromática vía GenICam/GigE Vision (~1920x1200)."""

    def __init__(self, cti_path: Optional[str] = None, device_index: int = 0) -> None:
        super().__init__()
        self._cti_path = cti_path or os.environ.get(CTI_ENV_VAR)
        self._device_index = device_index
        self._harvester = None
        self._acquirer = None

    def connect(self) -> None:
        try:
            from harvesters.core import Harvester
        except ImportError as exc:
            self._state = CameraState(
                status=CameraStatus.ERROR,
                last_error="Falta la librería 'harvesters' (pip install harvesters) para hablar GenICam/GigE Vision.",
            )
            raise CameraConnectionError(self._state.last_error) from exc

        if not self._cti_path or not os.path.exists(self._cti_path):
            self._state = CameraState(
                status=CameraStatus.ERROR,
                last_error=(
                    "No se encontró el archivo .cti (GenTL producer) del fabricante de la cámara. "
                    f"Configurá la variable de entorno {CTI_ENV_VAR} o pasá cti_path= al construir IndustrialCamera."
                ),
            )
            raise CameraConnectionError(self._state.last_error)

        self._harvester = Harvester()
        self._harvester.add_file(self._cti_path)
        self._harvester.update()

        if not self._harvester.device_info_list:
            self._state = CameraState(status=CameraStatus.ERROR, last_error="No se detectó ninguna cámara GenICam conectada.")
            raise CameraConnectionError(self._state.last_error)

        self._acquirer = self._harvester.create(self._device_index)
        self._acquirer.start()
        self._state = CameraState(status=CameraStatus.CONNECTED, extra={"mode": "industrial"})

    def disconnect(self) -> None:
        if self._acquirer is not None:
            self._acquirer.stop()
            self._acquirer.destroy()
            self._acquirer = None
        if self._harvester is not None:
            self._harvester.reset()
            self._harvester = None
        self._state = CameraState(status=CameraStatus.DISCONNECTED)

    def _fetch_frame(self) -> np.ndarray:
        if self._acquirer is None:
            raise CameraConnectionError("IndustrialCamera no está conectada: llamá a connect() primero.")
        with self._acquirer.fetch(timeout=5) as buffer:
            component = buffer.payload.components[0]
            array = component.data.reshape(component.height, component.width).copy()
        return array

    def get_preview_frame(self) -> np.ndarray:
        # CAVEAT para la integración con hardware real: este preview sale a
        # mitad de resolución que trigger_capture(). Las zonas de búsqueda y
        # el encuadre de referencia se calibran mirando el preview (pestañas
        # "Configuración"/"Entrada"), pero el recorte final (apply_crop) se
        # aplica sobre la imagen guardada a resolución completa. Si se deja
        # así tal cual, las coordenadas calibradas quedan desfasadas 2x.
        # Antes de calibrar con la cámara real, o bien sacar este resize (si
        # el preview a resolución completa no es demasiado lento), o agregar
        # un factor de escala explícito entre coordenadas de preview y de
        # captura — ver src/hardware/camera_simulated.py, que por eso NO
        # reescala, para servir de referencia de comportamiento correcto.
        mono = self._fetch_frame()
        preview = cv2.resize(mono, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        return cv2.cvtColor(preview, cv2.COLOR_GRAY2BGR)

    def trigger_capture(self, frame_index: int) -> CapturedFrame:
        mono = self._fetch_frame()
        # La cámara industrial entrega buffer crudo sin comprimir: se guarda
        # tal cual (storage/ decide si lo empaqueta como DNG).
        h, w = mono.shape[:2]
        return CapturedFrame(
            raw_bytes=mono.tobytes(),
            file_extension=".raw",
            width=w,
            height=h,
            frame_index=frame_index,
        )
