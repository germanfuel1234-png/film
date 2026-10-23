"""Pestaña "Entrada": fuente de cámara (con el switch), encuadre de
referencia y rotación."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ....hardware.camera_base import CameraConnectionError
from ....vision.stabilization import ReferenceBox
from ..app_context import AppContext
from ..image_utils import frame_to_pixmap
from ..widgets.camera_switch import CameraSwitch


class InputTab(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx

        root = QVBoxLayout(self)
        root.addWidget(CameraSwitch(ctx))

        body = QHBoxLayout()
        root.addLayout(body)

        # Preview
        preview_box = QGroupBox("Fotos / cámara como entrada")
        preview_layout = QVBoxLayout(preview_box)
        self.preview_label = QLabel("Sin preview. Conectá una cámara y presioná 'Activar preview'.")
        self.preview_label.setMinimumSize(480, 480)
        self.preview_label.setStyleSheet("background:#111; color:#888;")
        preview_layout.addWidget(self.preview_label)

        self.preview_button = QPushButton("Activar preview")
        self.preview_button.setCheckable(True)
        self.preview_button.toggled.connect(self._toggle_preview)
        preview_layout.addWidget(self.preview_button)

        body.addWidget(preview_box, stretch=3)

        # Encuadre de referencia
        ref_box = QGroupBox("Encuadre de referencia")
        form = QFormLayout(ref_box)

        self.rotation_spin = QSpinBox()
        self.rotation_spin.setRange(0, 270)
        self.rotation_spin.setSingleStep(90)
        self.rotation_spin.setValue(ctx.config.calibration.rotation_deg)
        form.addRow("Rotación antihoraria [°]", self.rotation_spin)

        rotation_button = QPushButton("Aplicar rotación")
        rotation_button.setToolTip(
            "La cámara suele capturar el film de costado (perforaciones arriba/abajo); esta\n"
            "rotación se aplica al exportar con 'Aplicar mejora' para que cada fotograma quede\n"
            "en la orientación de lectura normal, como una tira de película real."
        )
        rotation_button.clicked.connect(self._apply_rotation)
        form.addRow(rotation_button)

        ref_defaults = ctx.config.calibration.reference_box
        self.x0_spin = self._make_spin(default=ref_defaults.x0)
        self.y0_spin = self._make_spin(default=ref_defaults.y0)
        self.x1_spin = self._make_spin(default=ref_defaults.x1)
        self.y1_spin = self._make_spin(default=ref_defaults.y1)
        form.addRow("X inicial", self.x0_spin)
        form.addRow("Y inicial", self.y0_spin)
        form.addRow("X final", self.x1_spin)
        form.addRow("Y final", self.y1_spin)

        save_button = QPushButton("Guardar encuadre de referencia")
        save_button.clicked.connect(self._save_reference_box)
        form.addRow(save_button)

        body.addWidget(ref_box, stretch=2)

        self._timer = QTimer(self)
        self._timer.setInterval(500)  # ~2 FPS, como el preview del prototipo
        self._timer.timeout.connect(self._refresh_preview)

        ctx.config_changed.connect(self._sync_from_config)

    def _sync_from_config(self) -> None:
        box = self._ctx.config.calibration.reference_box
        self.x0_spin.setValue(box.x0)
        self.y0_spin.setValue(box.y0)
        self.x1_spin.setValue(box.x1)
        self.y1_spin.setValue(box.y1)
        self.rotation_spin.setValue(self._ctx.config.calibration.rotation_deg)

    def _apply_rotation(self) -> None:
        self._ctx.calibrator.set_output_rotation(self.rotation_spin.value())

    def _make_spin(self, default: int = 0) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(0, 10000)
        spin.setValue(default)
        return spin

    def _toggle_preview(self, checked: bool) -> None:
        if checked:
            self.preview_button.setText("Detener preview")
            self._timer.start()
        else:
            self.preview_button.setText("Activar preview")
            self._timer.stop()

    def _refresh_preview(self) -> None:
        try:
            frame = self._ctx.camera.get_preview_frame()
        except CameraConnectionError as exc:
            self.preview_label.setText(f"Error de cámara: {exc}")
            self.preview_button.setChecked(False)
            return
        pixmap = frame_to_pixmap(frame)
        self.preview_label.setPixmap(pixmap.scaled(self.preview_label.size(), Qt.AspectRatioMode.KeepAspectRatio))

    def _save_reference_box(self) -> None:
        box = ReferenceBox(
            x0=self.x0_spin.value(),
            y0=self.y0_spin.value(),
            x1=self.x1_spin.value(),
            y1=self.y1_spin.value(),
        )
        self._ctx.calibrator.set_reference_box(box)
