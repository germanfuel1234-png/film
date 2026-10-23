"""Pestaña "Ajustes": edita y guarda config/hardware_config.json desde la
interfaz gráfica, para que el cliente no tenga que tocar el JSON a mano.

Al guardar: escribe el archivo Y lo aplica en caliente (cambia de cámara,
reconstruye el motor, actualiza la calibración por defecto) vía
AppContext.apply_config() — no hace falta reiniciar el programa.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ....core.app_config import AppConfig, CalibrationDefaults, CameraConfig, MotorConfig, load_app_config, save_app_config
from ....core.calibration import FILM_FORMATS
from ....vision.perforation_detection import SearchZone
from ....vision.stabilization import ReferenceBox
from ..app_context import AppContext

CAMERA_TYPES = ["simulated", "industrial", "dslr"]
MOTOR_MODES = ["simulated", "serial"]


def _zone_row(form: QFormLayout, prefix: str, zone) -> dict[str, QSpinBox]:
    spins: dict[str, QSpinBox] = {}
    for label, value in (("X inicial", zone.x0), ("Y inicial", zone.y0), ("X final", zone.x1), ("Y final", zone.y1)):
        spin = QSpinBox()
        spin.setRange(0, 10000)
        spin.setValue(value)
        form.addRow(f"{prefix} · {label}", spin)
        spins[label] = spin
    return spins


def _zone_from_spins(spins: dict[str, QSpinBox], cls):
    return cls(x0=spins["X inicial"].value(), y0=spins["Y inicial"].value(), x1=spins["X final"].value(), y1=spins["Y final"].value())


class SettingsTab(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx

        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        root = QVBoxLayout(content)

        intro = QLabel(
            "Estos son los parámetros de hardware que normalmente completa el cliente (ver config/README.md). "
            "Guardar acá escribe config/hardware_config.json y lo aplica al momento, sin reiniciar el programa."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        root.addWidget(self._build_camera_box())
        root.addWidget(self._build_motor_box())
        root.addWidget(self._build_calibration_box())
        root.addWidget(self._build_storage_box())

        buttons_row = QHBoxLayout()
        reload_btn = QPushButton("Recargar desde archivo")
        reload_btn.clicked.connect(self._reload_from_file)
        save_btn = QPushButton("Guardar y aplicar")
        save_btn.clicked.connect(self._save_and_apply)
        buttons_row.addWidget(reload_btn)
        buttons_row.addWidget(save_btn)
        root.addLayout(buttons_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        root.addStretch(1)

        self._load_into_fields(ctx.config)

    # --- construcción de secciones ---
    def _build_camera_box(self) -> QGroupBox:
        box = QGroupBox("Cámara")
        form = QFormLayout(box)

        self.camera_type_combo = QComboBox()
        self.camera_type_combo.addItems(CAMERA_TYPES)
        form.addRow("Tipo (al arrancar)", self.camera_type_combo)

        sample_dir_row = QHBoxLayout()
        self.sample_dir_edit = QLineEdit()
        sample_dir_browse = QPushButton("Examinar carpeta...")
        sample_dir_browse.clicked.connect(self._browse_sample_dir)
        sample_dir_row.addWidget(self.sample_dir_edit)
        sample_dir_row.addWidget(sample_dir_browse)
        form.addRow("Fotogramas de ejemplo (simulada)", sample_dir_row)

        cti_row = QHBoxLayout()
        self.cti_path_edit = QLineEdit()
        cti_browse = QPushButton("Examinar...")
        cti_browse.clicked.connect(self._browse_cti_path)
        cti_row.addWidget(self.cti_path_edit)
        cti_row.addWidget(cti_browse)
        form.addRow("Archivo .cti (GenTL, industrial)", cti_row)

        self.device_index_spin = QSpinBox()
        self.device_index_spin.setRange(0, 16)
        form.addRow("Índice de dispositivo (industrial)", self.device_index_spin)

        return box

    def _build_motor_box(self) -> QGroupBox:
        box = QGroupBox("Motor (Arduino)")
        form = QFormLayout(box)

        self.motor_mode_combo = QComboBox()
        self.motor_mode_combo.addItems(MOTOR_MODES)
        form.addRow("Modo", self.motor_mode_combo)

        port_row = QHBoxLayout()
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        detect_btn = QPushButton("Detectar puertos")
        detect_btn.clicked.connect(self._detect_ports)
        port_row.addWidget(self.port_combo)
        port_row.addWidget(detect_btn)
        form.addRow("Puerto serie", port_row)

        self.baudrate_spin = QSpinBox()
        self.baudrate_spin.setRange(300, 2_000_000)
        form.addRow("Baudrate", self.baudrate_spin)

        self.steps_per_frame_spin = QSpinBox()
        self.steps_per_frame_spin.setRange(1, 100000)
        form.addRow("Pasos por fotograma", self.steps_per_frame_spin)

        return box

    def _build_calibration_box(self) -> QGroupBox:
        box = QGroupBox("Calibración por defecto")
        form = QFormLayout(box)

        self.film_format_combo = QComboBox()
        self.film_format_combo.addItems(list(FILM_FORMATS.keys()))
        form.addRow("Formato de película", self.film_format_combo)

        self.left_zone_spins = _zone_row(form, "Zona izquierda", SearchZone(0, 0, 0, 0))
        self.right_zone_spins = _zone_row(form, "Zona derecha", SearchZone(0, 0, 0, 0))
        self.reference_box_spins = _zone_row(form, "Encuadre de referencia", ReferenceBox(0, 0, 0, 0))

        self.rotation_spin = QSpinBox()
        self.rotation_spin.setRange(0, 270)
        self.rotation_spin.setSingleStep(90)
        form.addRow("Rotación antihoraria por defecto [°]", self.rotation_spin)

        return box

    def _build_storage_box(self) -> QGroupBox:
        box = QGroupBox("Almacenamiento")
        form = QFormLayout(box)

        root_row = QHBoxLayout()
        self.projects_root_edit = QLineEdit()
        root_browse = QPushButton("Examinar carpeta...")
        root_browse.clicked.connect(self._browse_projects_root)
        root_row.addWidget(self.projects_root_edit)
        root_row.addWidget(root_browse)
        form.addRow("Carpeta de proyectos", root_row)

        return box

    # --- acciones ---
    def _browse_cti_path(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Elegir archivo .cti (GenTL)", "", "GenTL producer (*.cti);;Todos los archivos (*)")
        if path:
            self.cti_path_edit.setText(path)

    def _browse_sample_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Elegir carpeta de fotogramas de ejemplo")
        if path:
            self.sample_dir_edit.setText(path)

    def _browse_projects_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Elegir carpeta de proyectos")
        if path:
            self.projects_root_edit.setText(path)

    def _detect_ports(self) -> None:
        try:
            from serial.tools import list_ports
        except ImportError:
            self.status_label.setText("No se pudo importar pyserial para detectar puertos.")
            return
        current = self.port_combo.currentText()
        self.port_combo.clear()
        ports = [p.device for p in list_ports.comports()]
        self.port_combo.addItems(ports)
        if current:
            self.port_combo.setCurrentText(current)
        self.status_label.setText(f"{len(ports)} puerto(s) encontrado(s)." if ports else "No se detectó ningún puerto serie.")

    def _load_into_fields(self, config: AppConfig) -> None:
        self.camera_type_combo.setCurrentText(config.camera.type)
        self.sample_dir_edit.setText(config.camera.simulated_sample_dir)
        self.cti_path_edit.setText(config.camera.industrial_cti_path)
        self.device_index_spin.setValue(config.camera.industrial_device_index)

        self.motor_mode_combo.setCurrentText(config.motor.mode)
        self.port_combo.setCurrentText(config.motor.port)
        self.baudrate_spin.setValue(config.motor.baudrate)
        self.steps_per_frame_spin.setValue(config.motor.steps_per_frame)

        self.film_format_combo.setCurrentText(config.calibration.film_format)
        for label, value in zip(
            ("X inicial", "Y inicial", "X final", "Y final"),
            (
                config.calibration.search_zone_left.x0,
                config.calibration.search_zone_left.y0,
                config.calibration.search_zone_left.x1,
                config.calibration.search_zone_left.y1,
            ),
        ):
            self.left_zone_spins[label].setValue(value)
        for label, value in zip(
            ("X inicial", "Y inicial", "X final", "Y final"),
            (
                config.calibration.search_zone_right.x0,
                config.calibration.search_zone_right.y0,
                config.calibration.search_zone_right.x1,
                config.calibration.search_zone_right.y1,
            ),
        ):
            self.right_zone_spins[label].setValue(value)
        for label, value in zip(
            ("X inicial", "Y inicial", "X final", "Y final"),
            (
                config.calibration.reference_box.x0,
                config.calibration.reference_box.y0,
                config.calibration.reference_box.x1,
                config.calibration.reference_box.y1,
            ),
        ):
            self.reference_box_spins[label].setValue(value)
        self.rotation_spin.setValue(config.calibration.rotation_deg)

        self.projects_root_edit.setText(config.projects_root)

    def _config_from_fields(self) -> AppConfig:
        return AppConfig(
            camera=CameraConfig(
                type=self.camera_type_combo.currentText(),
                simulated_sample_dir=self.sample_dir_edit.text().strip(),
                industrial_cti_path=self.cti_path_edit.text().strip(),
                industrial_device_index=self.device_index_spin.value(),
            ),
            motor=MotorConfig(
                mode=self.motor_mode_combo.currentText(),
                port=self.port_combo.currentText().strip(),
                baudrate=self.baudrate_spin.value(),
                steps_per_frame=self.steps_per_frame_spin.value(),
            ),
            calibration=CalibrationDefaults(
                film_format=self.film_format_combo.currentText(),
                search_zone_left=_zone_from_spins(self.left_zone_spins, SearchZone),
                search_zone_right=_zone_from_spins(self.right_zone_spins, SearchZone),
                reference_box=_zone_from_spins(self.reference_box_spins, ReferenceBox),
                rotation_deg=self.rotation_spin.value(),
            ),
            projects_root=self.projects_root_edit.text().strip() or "~/FILMS/projects",
        )

    def _reload_from_file(self) -> None:
        config = load_app_config()
        self._load_into_fields(config)
        self.status_label.setText("Recargado desde config/hardware_config.json (sin aplicar todavía: tocá 'Guardar y aplicar').")

    def _save_and_apply(self) -> None:
        new_config = self._config_from_fields()
        try:
            save_app_config(new_config)
        except OSError as exc:
            self.status_label.setText(f"Error al escribir el archivo: {exc}")
            return

        try:
            self._ctx.apply_config(new_config)
        except Exception as exc:  # noqa: BLE001 — se muestra al usuario, no se oculta
            QMessageBox.warning(
                self,
                "Se guardó, pero falló al aplicar",
                f"El archivo se guardó correctamente, pero no se pudo aplicar en caliente:\n{exc}\n\n"
                "Revisá el puerto/tipo de cámara, o reiniciá el programa.",
            )
            self.status_label.setText(f"Guardado con errores al aplicar: {exc}")
            return

        self.status_label.setText("Guardado en config/hardware_config.json y aplicado.")
