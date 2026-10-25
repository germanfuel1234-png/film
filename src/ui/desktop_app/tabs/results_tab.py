"""Pestaña "Resultados": comparativa ANTES (recorte sin estabilizar) vs.
DESPUÉS (alineado y recortado), navegando los fotogramas ya guardados del
proyecto activo — replica la vista del prototipo."""

from __future__ import annotations

import json

import cv2

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from ....core.post_stabilization import ImprovedFrameResult
from ....vision.stabilization import AlignmentResult, ReferenceBox, apply_crop
from ..app_context import AppContext
from ..dialogs.filmstrip_dialog import FilmstripDialog
from ..dialogs.improvement_results_dialog import ImprovementResultsDialog
from ..image_utils import frame_to_pixmap
from ..improvement_worker import ImprovementWorker


class ResultsTab(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._frame_indices: list[int] = []
        self._cursor = 0
        self._improvement_worker: ImprovementWorker | None = None
        self._improvement_new_count = 0
        self._improvement_already_done_count = 0
        self._improvement_errors = 0

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
            "Recalibra los fotogramas del proyecto contra el fotograma 0 (fijo), usando todas\n"
            "las perforaciones detectadas con ajuste robusto (RANSAC) en vez de un único par.\n"
            "Guarda el resultado en una carpeta nueva 'mejorado/' dentro del proyecto, sin\n"
            "tocar los originales en 'raw/'. Es RESUMIBLE: si el proyecto ya tiene fotogramas\n"
            "mejorados de una corrida anterior (completa o interrumpida), se saltean sin\n"
            "recalcularlos — tocar este botón de nuevo retoma donde quedó."
        )
        self.improve_button.clicked.connect(self._apply_improvement)
        improve_row.addWidget(self.improve_button)

        self.improve_stop_button = QPushButton("Detener mejora")
        self.improve_stop_button.setEnabled(False)
        self.improve_stop_button.setToolTip(
            "Corta la corrida después del fotograma que esté procesando en este momento (nunca\n"
            "a mitad de uno). Lo ya guardado queda intacto; tocar 'Aplicar mejora' más tarde\n"
            "retoma justo donde se cortó."
        )
        self.improve_stop_button.clicked.connect(self._stop_improvement)
        improve_row.addWidget(self.improve_stop_button)

        improve_row.addWidget(QLabel("Fotogramas nuevos por tanda"))
        self.improve_batch_spin = QSpinBox()
        self.improve_batch_spin.setRange(1, 1_000_000)
        self.improve_batch_spin.setValue(1_000_000)
        self.improve_batch_spin.setToolTip(
            "Para películas enteras (miles de fotogramas), conviene fraccionar en tandas en vez\n"
            "de procesar todo de una sola corrida larga. Dejar en el máximo procesa todo lo\n"
            "pendiente de una vez."
        )
        improve_row.addWidget(self.improve_batch_spin)

        self.filmstrip_button = QPushButton("Ver tira de película")
        self.filmstrip_button.setToolTip(
            "Apila varios fotogramas de 'mejorado/' uno debajo del otro, como una tira de\n"
            "película real, para comprobar de un vistazo que calzan sin saltos entre cuadros."
        )
        self.filmstrip_button.clicked.connect(self._show_filmstrip)
        improve_row.addWidget(self.filmstrip_button)
        root.addLayout(improve_row)

        self.improve_status_label = QLabel("")
        self.improve_status_label.setWordWrap(True)
        root.addWidget(self.improve_status_label)

    def _apply_improvement(self) -> None:
        if self._improvement_worker is not None and self._improvement_worker.isRunning():
            return  # ya hay una corrida en curso
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
        self.improve_stop_button.setEnabled(True)
        self._improvement_new_count = 0
        self._improvement_already_done_count = 0
        self._improvement_errors = 0
        self.improve_status_label.setText("Aplicando mejora, un momento...")

        self._improvement_worker = ImprovementWorker(
            self._ctx.storage,
            calib.left_zone,
            calib.right_zone,
            calib.reference_box,
            rotation_deg=calib.output_rotation_deg,
            max_frames=self.improve_batch_spin.value(),
        )
        self._improvement_worker.frame_processed.connect(self._on_improvement_frame_processed)
        self._improvement_worker.finished_run.connect(self._on_improvement_finished)
        self._improvement_worker.start()

    def _stop_improvement(self) -> None:
        if self._improvement_worker is not None:
            self.improve_status_label.setText("Deteniendo (termina el fotograma que esté procesando)...")
            self._improvement_worker.request_stop()

    def _on_improvement_frame_processed(self, result: ImprovedFrameResult) -> None:
        if result.already_done:
            self._improvement_already_done_count += 1
        elif result.error is not None:
            self._improvement_errors += 1
            self._improvement_new_count += 1
        else:
            self._improvement_new_count += 1
        self.improve_status_label.setText(
            f"Procesando... fotograma {result.frame_index} · "
            f"{self._improvement_new_count} nuevo(s), {self._improvement_already_done_count} ya hechos"
            + (f", {self._improvement_errors} con error" if self._improvement_errors else "")
        )

    def _on_improvement_finished(self, results: list[ImprovedFrameResult]) -> None:
        self.improve_button.setEnabled(True)
        self.improve_stop_button.setEnabled(False)
        self._improvement_worker = None

        if not results:
            self.improve_status_label.setText(
                "No hay fotogramas guardados en este proyecto para mejorar, o ya estaba todo hecho."
            )
            return

        ok = [r for r in results if r.error is None]
        errors = [r for r in results if r.error is not None]
        new_ok = [r for r in ok if not r.already_done]
        already_done = [r for r in ok if r.already_done]
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
            f"Mejora aplicada: {len(new_ok)} fotograma(s) nuevo(s) + {len(already_done)} ya hecho(s) de antes "
            f"= {len(ok)}/{len(results)} en {self._ctx.storage.project_dir / 'mejorado'}{rango_angulo}.{enderezado}"
        )
        if errors:
            texto += f"\n⚠ {len(errors)} fotograma(s) con error: " + ", ".join(
                f"{r.source_path.name} ({r.error})" for r in errors[:5]
            )
        self.improve_status_label.setText(texto)

        dialog = ImprovementResultsDialog(results, parent=self)
        dialog.exec()

    def _show_filmstrip(self) -> None:
        if self._ctx.storage is None:
            self.improve_status_label.setText("No hay proyecto activo.")
            return
        dialog = FilmstripDialog(self._ctx.storage, parent=self)
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
