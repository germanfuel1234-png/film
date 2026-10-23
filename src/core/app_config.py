"""Carga config/hardware_config.json — el único archivo que el cliente
necesita editar para conectar el programa a su hardware real (ver
config/README.md). Mientras no haya hardware, el programa arranca con los
valores por defecto (modo simulado) sin necesidad de este archivo.

Si el archivo falta o tiene un error de formato, NO se rompe la app: se
usan los valores por defecto y se avisa por consola — alguien editando un
JSON a mano se puede equivocar, y eso no debería tirar abajo el programa.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..vision.perforation_detection import SearchZone
from ..vision.stabilization import ReferenceBox

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "hardware_config.json"
PROJECT_ROOT = DEFAULT_CONFIG_PATH.parents[1]  # proyecto_film/


def resolve_project_path(raw_path: str) -> Path:
    """Resuelve una ruta de config/hardware_config.json: si es relativa
    (ej. "assets/real_frames"), la toma relativa a la raíz del proyecto
    (proyecto_film/), no al directorio desde donde se ejecutó Python."""
    path = Path(raw_path).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass
class CameraConfig:
    type: str = "simulated"
    industrial_cti_path: str = ""
    industrial_device_index: int = 0
    # Carpeta de fotogramas que usa la cámara simulada ("" = la carpeta
    # sintética por defecto de camera_simulated.py). Las imágenes acá
    # tienen que coincidir en geometría con las zonas de calibration.*
    # de abajo — si se cambia una, hay que recalibrar la otra.
    simulated_sample_dir: str = ""


@dataclass
class MotorConfig:
    mode: str = "simulated"  # "simulated" | "serial"
    port: str = ""
    baudrate: int = 115200
    steps_per_frame: int = 1000


@dataclass
class CalibrationDefaults:
    film_format: str = "35mm"
    search_zone_left: SearchZone = field(default_factory=lambda: SearchZone(10, 100, 110, 1200))
    search_zone_right: SearchZone = field(default_factory=lambda: SearchZone(760, 100, 860, 1200))
    reference_box: ReferenceBox = field(default_factory=lambda: ReferenceBox(220, 120, 680, 1180))
    # Rotación antihoraria por defecto (0/90/180/270) — ver
    # Calibrator.set_output_rotation en core/calibration.py.
    rotation_deg: int = 0


@dataclass
class AppConfig:
    camera: CameraConfig = field(default_factory=CameraConfig)
    motor: MotorConfig = field(default_factory=MotorConfig)
    calibration: CalibrationDefaults = field(default_factory=CalibrationDefaults)
    projects_root: str = "~/FILMS/projects"


def _zone(raw: dict, fallback: SearchZone) -> SearchZone:
    return SearchZone(
        x0=raw.get("x0", fallback.x0),
        y0=raw.get("y0", fallback.y0),
        x1=raw.get("x1", fallback.x1),
        y1=raw.get("y1", fallback.y1),
    )


def _reference_box(raw: dict, fallback: ReferenceBox) -> ReferenceBox:
    return ReferenceBox(
        x0=raw.get("x0", fallback.x0),
        y0=raw.get("y0", fallback.y0),
        x1=raw.get("x1", fallback.x1),
        y1=raw.get("y1", fallback.y1),
    )


def load_app_config(path: Path | str = DEFAULT_CONFIG_PATH) -> AppConfig:
    """Lee config/hardware_config.json. Si no existe o está mal formado,
    devuelve AppConfig() (todo en modo simulado) y avisa por consola en
    vez de lanzar una excepción que tiraría abajo la app."""
    path = Path(path).expanduser()
    if not path.exists():
        print(f"[config] No se encontró {path}; arrancando con valores por defecto (modo simulado).")
        return AppConfig()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[config] No se pudo leer {path} ({exc}); arrancando con valores por defecto (modo simulado).")
        return AppConfig()

    defaults = AppConfig()
    raw_camera = raw.get("camera", {})
    camera = CameraConfig(
        type=raw_camera.get("type", defaults.camera.type),
        industrial_cti_path=raw_camera.get("industrial_cti_path", defaults.camera.industrial_cti_path),
        industrial_device_index=raw_camera.get("industrial_device_index", defaults.camera.industrial_device_index),
        simulated_sample_dir=raw_camera.get("simulated_sample_dir", defaults.camera.simulated_sample_dir),
    )

    raw_motor = raw.get("motor", {})
    motor = MotorConfig(
        mode=raw_motor.get("mode", defaults.motor.mode),
        port=raw_motor.get("port", defaults.motor.port),
        baudrate=raw_motor.get("baudrate", defaults.motor.baudrate),
        steps_per_frame=raw_motor.get("steps_per_frame", defaults.motor.steps_per_frame),
    )

    raw_calib = raw.get("calibration", {})
    calibration = CalibrationDefaults(
        film_format=raw_calib.get("film_format", defaults.calibration.film_format),
        search_zone_left=_zone(raw_calib.get("search_zone_left", {}), defaults.calibration.search_zone_left),
        search_zone_right=_zone(raw_calib.get("search_zone_right", {}), defaults.calibration.search_zone_right),
        reference_box=_reference_box(raw_calib.get("reference_box", {}), defaults.calibration.reference_box),
        rotation_deg=raw_calib.get("rotation_deg", defaults.calibration.rotation_deg),
    )

    projects_root = raw.get("projects_root", defaults.projects_root)

    return AppConfig(camera=camera, motor=motor, calibration=calibration, projects_root=projects_root)


def _zone_to_dict(zone: SearchZone | ReferenceBox) -> dict:
    return {"x0": zone.x0, "y0": zone.y0, "x1": zone.x1, "y1": zone.y1}


def config_to_dict(config: AppConfig) -> dict:
    """Serializa un AppConfig al mismo esquema JSON que lee load_app_config."""
    return {
        "camera": {
            "type": config.camera.type,
            "industrial_cti_path": config.camera.industrial_cti_path,
            "industrial_device_index": config.camera.industrial_device_index,
            "simulated_sample_dir": config.camera.simulated_sample_dir,
        },
        "motor": {
            "mode": config.motor.mode,
            "port": config.motor.port,
            "baudrate": config.motor.baudrate,
            "steps_per_frame": config.motor.steps_per_frame,
        },
        "calibration": {
            "film_format": config.calibration.film_format,
            "search_zone_left": _zone_to_dict(config.calibration.search_zone_left),
            "search_zone_right": _zone_to_dict(config.calibration.search_zone_right),
            "reference_box": _zone_to_dict(config.calibration.reference_box),
            "rotation_deg": config.calibration.rotation_deg,
        },
        "projects_root": config.projects_root,
    }


def save_app_config(config: AppConfig, path: Path | str = DEFAULT_CONFIG_PATH) -> None:
    """Escribe config/hardware_config.json — usado por la pestaña "Ajustes"
    de la UI para que el cliente pueda guardar sus parámetros de hardware
    sin editar el JSON a mano."""
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config_to_dict(config), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
