"""Pestaña "Resultados": comparativa ANTES (recorte sin estabilizar) vs.
DESPUÉS (alineado y recortado), navegando los fotogramas ya guardados del
proyecto activo — replica la vista del prototipo."""

from __future__ import annotations

import json

import cv2

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ....core.post_stabilization import apply_improvement
from ....vision.stabilization import AlignmentResult, ReferenceBox, apply_crop
from ..app_context import AppContext
from ..dialogs.improvement_results_dialog import ImprovementResultsDialog
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

        improve_row = QHBoxLayout()
        self.improve_button = QPushButton("Aplicar mejora")
        self.improve_button.setToolTip(
            "Recalibra TODOS los fotogramas del proyecto contra el fotograma 0 (fijo), usando\n"
            "todas las perforaciones detectadas con ajuste robusto (RANSAC) en vez de un único\n"
            "par. Guarda el resultado en una carpeta nueva 'mejorado/' dentro del proyecto,\n"
            "sin tocar los originales en 'raw/'."
        )
        self.improve_button.clicked.connect(self._apply_improvement)
        improve_row.addWidget(self.improve_button)
        root.addLayout(improve_row)

        self.improve_status_label = QLabel("")
        self.improve_status_label.setWordWrap(True)
        root.addWidget(self.improve_status_label)

    def _apply_improvement(self) -> None:
        if self._ctx.storage is None:
            self.improve_status_label.setText("No hay proyecto activo.")
            return
        calib = self._ctx.calibrator.state
        if calib.left_zone is None or calib.right_zone is None or calib.reference_box is None:
            self.improve_status_label.setText(
                "Faltan zonas de búsqueda o encuadre de referencia (pestañas 'Configuración'/'Entrada')."
            )
            return

        self.improve_button.setEnabled(False)
        self.improve_status_label.setText("Aplicando mejora, un momento...")
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()  # que se vea el mensaje antes de bloquear con el procesamiento

        try:
            results = apply_improvement(
                self._ctx.storage,
                calib.left_zone,
                calib.right_zone,
                calib.reference_box,
                rotation_deg=calib.output_rotation_deg,
            )
        finally:
            self.improve_button.setEnabled(True)

        if not results:
            self.improve_status_label.setText("No hay fotogramas guardados en este proyecto para mejorar.")
            return

        ok = [r for r in results if r.error is None]
        errors = [r for r in results if r.error is not None]
        angles = [r.alignment.angle_deg for r in ok if r.alignment is not None]
        rango_angulo = f" · giro entre {min(angles):+.2f}° y {max(angles):+.2f}°" if angles else ""

        tilt = next((r.reference_tilt_corrected_deg for r in results if r.reference_tilt_corrected_deg is not None), None)
        enderezado = (
            f"\nCero absoluto: el fotograma 0 venía inclinado {tilt:+.3f}° y se enderezó, "
            "así que toda la secuencia queda recta para el ojo (no solo consistente entre cuadros)."
            if tilt is not None
            else ""
        )

        texto = (
            f"Mejora aplicada: {len(ok)}/{len(results)} fotogramas guardados en "
            f"{self._ctx.storage.project_dir / 'mejorado'}{rango_angulo}.{enderezado}"
        )
        if errors:
            texto += f"\n⚠ {len(errors)} fotograma(s) con error: " + ", ".join(
                f"{r.source_path.name} ({r.error})" for r in errors[:5]
            )
        self.improve_status_label.setText(texto)

        dialog = ImprovementResultsDialog(results, parent=self)
        dialog.exec()

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
