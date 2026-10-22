"""Estado compartido entre las pestañas de la UI: proyecto activo,
calibración, driver de cámara actual (seleccionable por switch) y motor.

Todos los valores dependientes de hardware (tipo de cámara, puerto del
Arduino, zonas de búsqueda, encuadre de referencia) se leen al arrancar
desde config/hardware_config.json — ver core/app_config.py y
config/README.md. El cliente puede editar ese archivo a mano, o usar la
pestaña "Ajustes" de la UI (widgets/settings_tab no vive acá, pero llama
a AppContext.apply_config() para aplicar los cambios sin reiniciar).
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Signal

from ...core.app_config import AppConfig, load_app_config
from ...core.calibration import Calibrator
from ...core.project_manager import ProjectConfig, ProjectManager
from ...core.scan_controller import ScanController
from ...hardware.camera_base import CameraDriver
from ...hardware.camera_factory import create_camera
from ...hardware.motor.stepper_motor import SimulatedStepperMotor, StepperMotor
from ...storage.raw_dng_writer import ProjectStorage


class AppContext(QObject):
    """Objeto único compartido por toda la ventana principal.

    Centraliza el acceso a `core/` y `hardware/` para que cada pestaña no
    tenga que recrear sus propias instancias de ProjectManager, Calibrator,
    etc. Emite señales Qt cuando cambia algo que otras pestañas necesitan
    reflejar (ej. cambio de cámara, cambio de proyecto activo, guardado de
    configuración nueva desde la pestaña "Ajustes").
    """

    camera_changed = Signal(str)  # nuevo camera_type
    project_changed = Signal(object)  # ProjectConfig | None
    config_changed = Signal()  # se guardó/aplicó un AppConfig nuevo desde "Ajustes"

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        super().__init__()
        self.project_manager: Optional[ProjectManager] = None
        self.calibrator = Calibrator()
        self.camera: Optional[CameraDriver] = None
        self.camera_type: str = "simulated"
        self.motor: Optional[StepperMotor] = None

        self.current_project: Optional[ProjectConfig] = None
        self.storage: Optional[ProjectStorage] = None
        self.scan_controller: Optional[ScanController] = None

        self.apply_config(config or load_app_config())

    def _camera_kwargs(self, camera_type: str) -> dict:
        """Parámetros de conexión tomados de hardware_config.json para el
        tipo de cámara dado — ver config/README.md."""
        if camera_type == "industrial":
            kwargs = {"device_index": self.config.camera.industrial_device_index}
            if self.config.camera.industrial_cti_path:
                kwargs["cti_path"] = self.config.camera.industrial_cti_path
            return kwargs
        return {}

    def _build_motor(self) -> StepperMotor:
        if self.config.motor.mode == "serial" and self.config.motor.port:
            motor = StepperMotor(port=self.config.motor.port, baudrate=self.config.motor.baudrate)
            try:
                motor.connect()
            except Exception:
                pass  # el puerto puede no estar disponible todavía; se reintenta manualmente desde la UI
            return motor
        return SimulatedStepperMotor()

    # --- switch de cámara (pestaña "Entrada") ---
    def set_camera(self, camera_type: str, **kwargs) -> None:
        """Cambia el driver de cámara en runtime (el "switch" pedido por el
        cliente: no sabemos aún qué 2 cámaras va a usar en definitiva)."""
        try:
            if self.camera is not None and self.camera.state.status.value == "connected":
                self.camera.disconnect()
        except Exception:
            pass  # desconexión best-effort; no debe bloquear el cambio de cámara

        kwargs = kwargs or self._camera_kwargs(camera_type)
        self.camera = create_camera(camera_type, **kwargs)
        self.camera_type = camera_type
        self._rebuild_scan_controller()
        self.camera_changed.emit(camera_type)

    # --- proyecto activo ---
    def activate_project(self, project: ProjectConfig) -> None:
        self.current_project = project
        self.storage = self.project_manager.storage_for(project.project_id)
        self.calibrator.set_film_format(project.film_format)
        self._rebuild_scan_controller()
        self.project_changed.emit(project)

    # --- pestaña "Ajustes": aplicar + persistir un AppConfig nuevo ---
    def apply_config(self, new_config: AppConfig) -> None:
        """Aplica un AppConfig (nuevo o recién cargado) en caliente: cámara,
        motor, calibración por defecto y carpeta de proyectos. No escribe el
        archivo — eso lo hace core.app_config.save_app_config() desde la
        pestaña "Ajustes" antes o después de llamar acá."""
        self.config = new_config

        self.project_manager = ProjectManager(projects_root=new_config.projects_root)

        self.calibrator.set_film_format(new_config.calibration.film_format)
        self.calibrator.set_search_zones(new_config.calibration.search_zone_left, new_config.calibration.search_zone_right)
        self.calibrator.set_reference_box(new_config.calibration.reference_box)

        self.set_camera(new_config.camera.type, **self._camera_kwargs(new_config.camera.type))
        self.motor = self._build_motor()

        self._rebuild_scan_controller()
        self.config_changed.emit()

    def _rebuild_scan_controller(self) -> None:
        if self.storage is None or self.motor is None:
            self.scan_controller = None
            return
        self.scan_controller = ScanController(
            camera=self.camera,
            motor=self.motor,
            calibrator=self.calibrator,
            storage=self.storage,
            steps_per_frame=self.config.motor.steps_per_frame,
        )
