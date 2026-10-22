"""Driver para cámara réflex Canon (ej. EOS Rebel T3i) vía gPhoto2.

gPhoto2 es la vía más simple para scripting multiplataforma (Linux/Windows
con libgphoto2 instalado). Si el cliente confirma uso de Windows puro y
necesita funciones avanzadas no cubiertas por gPhoto2, se puede agregar un
driver alternativo basado en Canon EDSDK detrás de la misma interfaz
CameraDriver sin tocar el resto del pipeline.
"""

from __future__ import annotations

import io
from typing import Optional

import cv2
import numpy as np

from .camera_base import CameraDriver, CameraState, CameraStatus, CapturedFrame, CameraConnectionError


class DslrCamera(CameraDriver):
    """Cámara réflex Canon vía gPhoto2. Captura en RAW (CR2), nunca JPEG."""

    def __init__(self) -> None:
        super().__init__()
        self._camera = None

    def connect(self) -> None:
        try:
            import gphoto2 as gp
        except ImportError as exc:
            self._state = CameraState(
                status=CameraStatus.ERROR,
                last_error="Falta la librería 'gphoto2' (pip install gphoto2; requiere libgphoto2 instalado en el sistema).",
            )
            raise CameraConnectionError(self._state.last_error) from exc

        try:
            self._camera = gp.Camera()
            self._camera.init()
        except gp.GPhoto2Error as exc:
            self._state = CameraState(
                status=CameraStatus.ERROR,
                last_error=f"No se pudo conectar con la cámara Canon por USB: {exc}",
            )
            raise CameraConnectionError(self._state.last_error) from exc

        self._ensure_raw_capture_format()
        self._state = CameraState(status=CameraStatus.CONNECTED, extra={"mode": "dslr"})

    def _ensure_raw_capture_format(self) -> None:
        """Fuerza el formato de captura a RAW en la cámara, si el config lo permite.

        El nombre exacto del widget de config varía por modelo; en la
        mayoría de las Canon EOS es 'imageformat' o 'imagequality'.
        """
        import gphoto2 as gp

        config = self._camera.get_config()
        for widget_name in ("imageformat", "imagequality"):
            try:
                widget = config.get_child_by_name(widget_name)
            except gp.GPhoto2Error:
                continue
            choices = [widget.get_choice(i) for i in range(widget.count_choices())]
            raw_choice = next((c for c in choices if "raw" in c.lower()), None)
            if raw_choice:
                widget.set_value(raw_choice)
                self._camera.set_config(config)
                return
        # Si no se encontró un choice RAW explícito, se deja constancia para
        # que el operador lo configure manualmente en la cámara: el
        # contrato del proyecto prohíbe entregar JPEG.
        self._state.extra["raw_format_warning"] = (
            "No se pudo confirmar automáticamente el formato RAW en la cámara; verificar manualmente."
        )

    def disconnect(self) -> None:
        if self._camera is not None:
            self._camera.exit()
            self._camera = None
        self._state = CameraState(status=CameraStatus.DISCONNECTED)

    def get_preview_frame(self) -> np.ndarray:
        # CAVEAT: el Live View de gPhoto2 normalmente viene en menor
        # resolución que capture() (ver nota equivalente en
        # camera_industrial.py). Calibrar zonas/encuadre con esta cámara
        # conectada y confirmar que coincide con la resolución de
        # trigger_capture() antes de dar por buena la calibración.
        import gphoto2 as gp

        if self._camera is None:
            raise CameraConnectionError("DslrCamera no está conectada: llamá a connect() primero.")
        camera_file = self._camera.capture_preview()
        file_data = camera_file.get_data_and_size()
        arr = np.frombuffer(bytes(file_data), dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise CameraConnectionError("No se pudo decodificar el preview (Live View) de la cámara Canon.")
        return img

    def trigger_capture(self, frame_index: int) -> CapturedFrame:
        import gphoto2 as gp

        if self._camera is None:
            raise CameraConnectionError("DslrCamera no está conectada: llamá a connect() primero.")

        file_path = self._camera.capture(gp.GP_CAPTURE_IMAGE)
        camera_file = self._camera.file_get(file_path.folder, file_path.name, gp.GP_FILE_TYPE_NORMAL)
        raw_bytes = bytes(camera_file.get_data_and_size())
        extension = "." + file_path.name.rsplit(".", 1)[-1].lower() if "." in file_path.name else ".cr2"

        return CapturedFrame(
            raw_bytes=raw_bytes,
            file_extension=extension,
            width=0,  # se completa luego al decodificar el RAW (rawpy) en storage/
            height=0,
            frame_index=frame_index,
        )
