"""El switch de cámara pedido por el cliente: combo + conectar/desconectar.

No sabemos todavía qué 2 cámaras va a usar en definitiva, así que este
widget no asume ningún modelo concreto: lista los tipos que expone
hardware/camera_factory.available_camera_types() ("industrial", "dslr",
"simulated") y delega el cambio real a AppContext.set_camera().
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget

from ....hardware.camera_base import CameraConnectionError
from ....hardware.camera_factory import available_camera_types
from ..app_context import AppContext

CAMERA_LABELS = {
    "industrial": "Cámara industrial (GenICam/GigE)",
    "dslr": "Cámara réflex Canon (gPhoto2)",
    "simulated": "Simulada (fotogramas de ejemplo)",
}


class CameraSwitch(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("Cámara:"))

        self.combo = QComboBox()
        for camera_type in available_camera_types():
            self.combo.addItem(CAMERA_LABELS.get(camera_type, camera_type), userData=camera_type)
        self.combo.setCurrentIndex(self.combo.findData(ctx.camera_type))
        layout.addWidget(self.combo)

        self.connect_button = QPushButton("Conectar")
        self.connect_button.clicked.connect(self._on_connect_clicked)
        layout.addWidget(self.connect_button)

        self.status_label = QLabel("● desconectada")
        layout.addWidget(self.status_label)
        layout.addStretch(1)

        self.combo.currentIndexChanged.connect(self._on_camera_type_selected)

    def _on_camera_type_selected(self) -> None:
        camera_type = self.combo.currentData()
        self._ctx.set_camera(camera_type)
        self._set_status("desconectada", ok=False)

    def _on_connect_clicked(self) -> None:
        try:
            self._ctx.camera.connect()
            self._set_status("conectada", ok=True)
        except CameraConnectionError as exc:
            self._set_status(f"error: {exc}", ok=False)

    def _set_status(self, text: str, ok: bool) -> None:
        color = "#2ecc71" if ok else "#e74c3c"
        self.status_label.setText(f"● {text}")
        self.status_label.setStyleSheet(f"color: {color};")
