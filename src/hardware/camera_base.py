"""Interfaz común que deben implementar todos los drivers de cámara.

core/scan_controller y el resto del pipeline solo conocen esta interfaz:
nunca importan un SDK de fabricante directamente. Esto es lo que permite
el "switch" de cámara en runtime (ver camera_factory.py).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np


class CameraStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class CameraState:
    status: CameraStatus = CameraStatus.DISCONNECTED
    last_error: Optional[str] = None
    extra: dict = field(default_factory=dict)


@dataclass
class CapturedFrame:
    """Resultado de un trigger_capture(): buffer crudo + metadata mínima."""

    raw_bytes: bytes
    file_extension: str  # ".dng", ".cr2", ".raw", etc.
    width: int
    height: int
    frame_index: int


class CameraDriver(ABC):
    """Contrato común para cámara industrial, DSLR o simulada.

    Cualquier driver concreto (camera_industrial, camera_dslr,
    camera_simulated) debe heredar de esta clase e implementar todos los
    métodos abstractos. `core/scan_controller` y la UI solo dependen de
    este tipo, nunca de la implementación concreta.
    """

    def __init__(self) -> None:
        self._state = CameraState()

    @property
    def state(self) -> CameraState:
        return self._state

    @abstractmethod
    def connect(self) -> None:
        """Abre la conexión con el dispositivo. Debe dejar self._state actualizado."""

    @abstractmethod
    def disconnect(self) -> None:
        """Cierra la conexión liberando los recursos del SDK/handle."""

    @abstractmethod
    def get_preview_frame(self) -> np.ndarray:
        """Devuelve un frame de baja resolución (BGR o mono) para preview/detección.

        Debe ser rápido: lo consume vision/perforation_detection en cada
        ciclo, no la captura final en RAW/DNG.
        """

    @abstractmethod
    def trigger_capture(self, frame_index: int) -> CapturedFrame:
        """Dispara una captura en resolución completa, en RAW/DNG. Nunca JPEG."""

    def get_status(self) -> CameraState:
        return self._state

    def __enter__(self) -> "CameraDriver":
        self.connect()
        return self

    def __exit__(self, *exc_info) -> None:
        self.disconnect()


class CameraConnectionError(RuntimeError):
    """Error al conectar o comunicarse con una cámara física."""
