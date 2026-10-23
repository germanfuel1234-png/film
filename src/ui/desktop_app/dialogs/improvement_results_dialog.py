"""Ventana que se abre automáticamente al terminar "Aplicar mejora", para
navegar los fotogramas ya corregidos (carpeta `mejorado/`) sin tener que
ir a buscarlos a mano en el disco."""

from __future__ import annotations

from typing import List

import cv2

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ....core.post_stabilization import ImprovedFrameResult
from ..image_utils import frame_to_pixmap


class ImprovementResultsDialog(QDialog):
    def __init__(self, results: List[ImprovedFrameResult], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Resultados de la mejora")
        self.resize(900, 750)

        self._ok_results = [r for r in results if r.output_path is not None]
        self._errors = [r for r in results if r.error is not None]
        self._cursor = 0

        layout = QVBoxLayout(self)

        summary = QLabel(
            f"{len(self._ok_results)}/{len(results)} fotogramas mejorados"
            + (f" · {len(self._errors)} con error" if self._errors else "")
        )
        summary.setStyleSheet("font-weight: bold;")
        layout.addWidget(summary)

        nav = QHBoxLayout()
        self.prev_button = QPushButton("← Anterior")
        self.prev_button.clicked.connect(self._go_prev)
        self.next_button = QPushButton("Siguiente →")
        self.next_button.clicked.connect(self._go_next)
        nav.addWidget(self.prev_button)
        nav.addWidget(self.next_button)
        layout.addLayout(nav)

        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.image_label = QLabel()
        self.image_label.setMinimumSize(700, 550)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background:#111; color:#888;")
        layout.addWidget(self.image_label)

        close_button = QPushButton("Cerrar")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

        self._show_current()

    def _go_prev(self) -> None:
        self._cursor = max(0, self._cursor - 1)
        self._show_current()

    def _go_next(self) -> None:
        self._cursor = min(len(self._ok_results) - 1, self._cursor + 1)
        self._show_current()

    def _show_current(self) -> None:
        if not self._ok_results:
            self.info_label.setText("No hay fotogramas mejorados para mostrar.")
            self.image_label.setText("Sin resultados.")
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)
            return

        result = self._ok_results[self._cursor]
        img = cv2.imread(str(result.output_path))
        if img is not None:
            pixmap = frame_to_pixmap(img)
            self.image_label.setPixmap(pixmap.scaled(self.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio))
        else:
            self.image_label.setText(f"No se pudo leer {result.output_path.name}")

        alignment_label = result.alignment.as_label() if result.alignment is not None else ""
        self.info_label.setText(
            f"{self._cursor + 1}/{len(self._ok_results)} · {result.output_path.name} · {alignment_label}"
        )

        self.prev_button.setEnabled(self._cursor > 0)
        self.next_button.setEnabled(self._cursor < len(self._ok_results) - 1)
