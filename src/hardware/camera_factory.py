"""El "switch" de cámara: crea el CameraDriver correcto según configuración.

Como todavía no está definido qué 2 cámaras va a usar el cliente en
definitiva, el resto del sistema nunca instancia un driver concreto
directamente — siempre pasa por create_camera(). Cambiar de cámara (desde
la UI, un .json de config, o programáticamente) es cambiar un string, no
tocar el pipeline de visión/estabilización/storage.
"""

from __future__ import annotations

from enum import Enum

from .camera_base import CameraDriver


class CameraType(str, Enum):
    INDUSTRIAL = "industrial"
    DSLR = "dslr"
    SIMULATED = "simulated"


def create_camera(camera_type: str | CameraType, **kwargs) -> CameraDriver:
    """Instancia el driver de cámara correspondiente al switch seleccionado.

    Ejemplos:
        create_camera(CameraType.SIMULATED)
        create_camera("industrial", cti_path="/opt/huateng/genicam.cti")
        create_camera("dslr")
    """
    camera_type = CameraType(camera_type)

    if camera_type is CameraType.INDUSTRIAL:
        from .camera_industrial import IndustrialCamera

        return IndustrialCamera(**kwargs)

    if camera_type is CameraType.DSLR:
        from .camera_dslr import DslrCamera

        return DslrCamera(**kwargs)

    if camera_type is CameraType.SIMULATED:
        from .camera_simulated import SimulatedCamera

        return SimulatedCamera(**kwargs)

    raise ValueError(f"Tipo de cámara desconocido: {camera_type}")


def available_camera_types() -> list[str]:
    """Lista de valores válidos para poblar el selector/switch en la UI."""
    return [t.value for t in CameraType]
