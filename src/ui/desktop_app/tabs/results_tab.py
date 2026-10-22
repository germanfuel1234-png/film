"""Pestaña "Resultados": comparativa ANTES (recorte sin estabilizar) vs.
DESPUÉS (alineado y recortado), navegando los fotogramas ya guardados del
proyecto activo — replica la vista del prototipo."""

from __future__ import annotations

import json

import cv2

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ....vision.stabilization import AlignmentResult, ReferenceBox, apply_crop
from ..app_context import AppContext
from ..image_utils import frame_to_pixmap


class ResultsTab(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._frame_indices: list[int] = []
        self._cursor = 0

        root = QVBoxLayout(self)

        nav = QHBoxLayout()
        self.prev_button = QPushButton("← Anterior")
        self.prev_button.clicked.connect(self._go_prev)
        self.next_button = QPushButton("Siguiente →")
        self.next_button.clicked.connect(self._go_next)
        self.refresh_button = QPushButton("Actualizar lista")
        self.refresh_button.clicked.connect(self._reload_index)
        nav.addWidget(self.prev_button)
        nav.addWidget(self.next_button)
        nav.addWidget(self.refresh_button)
        root.addLayout(nav)

        self.info_label = QLabel("Sin resultados todavía.")
        root.addWidget(self.info_label)

        images_row = QHBoxLayout()
        self.before_label = QLabel("ANTES · recorte sin estabilizar")
        self.before_label.setMinimumSize(360, 360)
        self.before_label.setStyleSheet("background:#111; color:#888;")
        self.after_label = QLabel("DESPUÉS · alineado y recortado")
        self.after_label.setMinimumSize(360, 360)
        self.after_label.setStyleSheet("background:#111; color:#888;")
        images_row.addWidget(self.before_label)
        images_row.addWidget(self.after_label)
        root.addLayout(images_row)

    def _reload_index(self) -> None:
        if self._ctx.storage is None:
            self.info_label.setText("No hay un proyecto activo.")
            return
        self._frame_indices = sorted(
            int(p.stem.split("_")[1]) for p in self._ctx.storage.corrections_dir.glob("frame_*.json")
        )
        self._cursor = max(0, len(self._frame_indices) - 1)
        self._show_current()

    def _go_prev(self) -> None:
        self._cursor = max(0, self._cursor - 1)
        self._show_current()

    def _go_next(self) -> None:
        self._cursor = min(len(self._frame_indices) - 1, self._cursor + 1)
        self._show_current()

    def _show_current(self) -> None:
        if not self._frame_indices or self._ctx.storage is None:
            self.info_label.setText("Sin resultados todavía.")
            return

        idx = self._frame_indices[self._cursor]
        correction_path = self._ctx.storage.corrections_dir / f"frame_{idx:05d}.json"
        payload = json.loads(correction_path.read_text(encoding="utf-8"))
        alignment = AlignmentResult(**payload["alignment"])
        reference_box = ReferenceBox(**payload["reference_box"])

        raw_candidates = list(self._ctx.storage.raw_dir.glob(f"frame_{idx:05d}.*"))
        if not raw_candidates:
            self.info_label.setText(f"{idx + 1}/{len(self._frame_indices)} · falta el archivo RAW en disco.")
            return
        raw_path = raw_candidates[0]

        frame = cv2.imread(str(raw_path), cv2.IMREAD_COLOR)
        if frame is None:
            self.info_label.setText(
                f"{idx + 1}/{len(self._frame_indices)} · {raw_path.name} es RAW/DNG real: "
                "para previsualizarlo acá hace falta decodificarlo con rawpy (no incluido en este esqueleto)."
            )
            return

        before_crop = frame[reference_box.y0 : reference_box.y1, reference_box.x0 : reference_box.x1]
        after_crop = apply_crop(frame, reference_box, alignment)

        self.before_label.setPixmap(
            frame_to_pixmap(before_crop).scaled(self.before_label.size(), Qt.AspectRatioMode.KeepAspectRatio)
        )
        self.after_label.setPixmap(
            frame_to_pixmap(after_crop).scaled(self.after_label.size(), Qt.AspectRatioMode.KeepAspectRatio)
        )

        status = "OK" if alignment.ok else "revisar"
        self.info_label.setText(
            f"{idx + 1}/{len(self._frame_indices)} · {raw_path.name} · {alignment.as_label()} · {status}"
        )
