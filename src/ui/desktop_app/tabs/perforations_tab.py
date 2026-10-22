"""Pestaña "Perforaciones": prueba visual de detección sobre el preview
actual, usando las zonas de búsqueda definidas en "Configuración"."""

from __future__ import annotations

import cv2

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from ....hardware.camera_base import CameraConnectionError
from ....vision.perforation_detection import detect_perforations
from ..app_context import AppContext
from ..image_utils import frame_to_pixmap


class PerforationsTab(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx

        layout = QVBoxLayout(self)

        self.preview_label = QLabel("Presioná 'Probar detección' para ver las perforaciones encontradas.")
        self.preview_label.setMinimumSize(480, 480)
        self.preview_label.setStyleSheet("background:#111; color:#888;")
        layout.addWidget(self.preview_label)

        test_button = QPushButton("Probar detección")
        test_button.clicked.connect(self._test_detection)
        layout.addWidget(test_button)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

    def _test_detection(self) -> None:
        calib = self._ctx.calibrator.state
        if calib.left_zone is None or calib.right_zone is None:
            self.status_label.setText("Definí las zonas de búsqueda en la pestaña 'Configuración' primero.")
            return
        try:
            frame = self._ctx.camera.get_preview_frame()
        except CameraConnectionError as exc:
            self.status_label.setText(f"Error de cámara: {exc}")
            return

        perforations = detect_perforations(frame, calib.left_zone, calib.right_zone)
        overlay = frame.copy()
        for zone, color in ((calib.left_zone, (80, 200, 255)), (calib.right_zone, (80, 200, 255))):
            cv2.rectangle(overlay, (zone.x0, zone.y0), (zone.x1, zone.y1), color, 2)
        for perforation in perforations:
            cv2.circle(overlay, (int(perforation.cx), int(perforation.cy)), 10, (60, 220, 90), 3)

        pixmap = frame_to_pixmap(overlay)
        self.preview_label.setPixmap(pixmap.scaled(self.preview_label.size(), Qt.AspectRatioMode.KeepAspectRatio))
        self.status_label.setText(f"{len(perforations)} perforaciones detectadas.")
