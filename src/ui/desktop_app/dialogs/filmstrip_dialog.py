"""Ventana "Ver tira de película": apila varios fotogramas de
`mejorado/` uno debajo del otro para comprobar de un vistazo que calzan
sin saltos, igual a como el cliente mostró el video de referencia."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ....core.filmstrip import build_filmstrip, list_improved_frames
from ....storage.raw_dng_writer import ProjectStorage
from ..image_utils import frame_to_pixmap


class FilmstripDialog(QDialog):
    def __init__(self, storage: ProjectStorage, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tira de película")
        self.resize(500, 800)

        self._storage = storage
        self._frame_paths = list_improved_frames(storage)

        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Desde fotograma"))
        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, max(0, len(self._frame_paths) - 1))
        controls.addWidget(self.start_spin)

        controls.addWidget(QLabel("Cantidad"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(2, 20)
        self.count_spin.setValue(6)
        controls.addWidget(self.count_spin)

        refresh_button = QPushButton("Actualizar")
        refresh_button.clicked.connect(self._refresh)
        controls.addWidget(refresh_button)
        layout.addLayout(controls)

        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.image_label.setStyleSheet("background:#111; color:#888;")
        scroll.setWidget(self.image_label)
        layout.addWidget(scroll)

        close_button = QPushButton("Cerrar")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

        self._refresh()

    def _refresh(self) -> None:
        if not self._frame_paths:
            self.info_label.setText(
                "No hay fotogramas en 'mejorado/' todavía — corré 'Aplicar mejora' primero."
            )
            self.image_label.setText("Sin fotogramas.")
            return

        start = self.start_spin.value()
        count = self.count_spin.value()
        strip = build_filmstrip(self._frame_paths, start=start, count=count)
        if strip is None:
            self.info_label.setText("No se pudo armar la tira con esos parámetros.")
            self.image_label.setText("")
            return

        shown = min(count, len(self._frame_paths) - start)
        self.info_label.setText(
            f"Mostrando {shown} fotogramas consecutivos (desde el #{start}) de {len(self._frame_paths)} disponibles."
        )
        pixmap = frame_to_pixmap(strip)
        self.image_label.setPixmap(pixmap)
        self.image_label.resize(pixmap.size())
