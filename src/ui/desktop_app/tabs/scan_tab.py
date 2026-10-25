"""Pestaña "Escaneo": control maestro — proyecto, estimación de espacio y
captura automática por tandas."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ....core.calibration import FILM_FORMATS
from ....core.scan_controller import FrameResult, ScanControllerError
from ....core.storage_estimate import estimate_storage, human_size
from ..app_context import AppContext
from ..scan_worker import ScanWorker


class ScanTab(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._worker: ScanWorker | None = None

        root = QVBoxLayout(self)

        # 01 PROYECTO
        project_box = QGroupBox("01 Proyecto")
        project_layout = QVBoxLayout(project_box)

        name_row = QHBoxLayout()
        self.name_edit = QLineEdit("Primera prueba")
        self.format_combo = QComboBox()
        self.format_combo.addItems(list(FILM_FORMATS.keys()))
        self.format_combo.setCurrentText(ctx.config.calibration.film_format)
        name_row.addWidget(self.name_edit)
        name_row.addWidget(self.format_combo)
        project_layout.addLayout(name_row)

        create_btn = QPushButton("Crear proyecto")
        create_btn.clicked.connect(self._create_project)
        project_layout.addWidget(create_btn)

        self.project_combo = QComboBox()
        project_layout.addWidget(self.project_combo)

        open_btn = QPushButton("Abrir / reanudar seleccionado")
        open_btn.clicked.connect(self._open_selected_project)
        project_layout.addWidget(open_btn)

        self.project_status_label = QLabel("Sin proyecto abierto.")
        project_layout.addWidget(self.project_status_label)

        root.addWidget(project_box)
        self._reload_project_list()

        # 02 ESTIMACIÓN DE ESPACIO
        storage_box = QGroupBox("02 Espacio en disco")
        storage_layout = QVBoxLayout(storage_box)

        frames_row = QHBoxLayout()
        frames_row.addWidget(QLabel("Fotogramas totales del rollo (aprox.)"))
        self.total_frames_spin = QSpinBox()
        self.total_frames_spin.setRange(1, 1_000_000)
        self.total_frames_spin.setValue(3000)  # ~100 pies de 16mm a 24fps, de referencia
        self.total_frames_spin.valueChanged.connect(self._refresh_storage_estimate)
        frames_row.addWidget(self.total_frames_spin)
        storage_layout.addLayout(frames_row)

        self.storage_estimate_label = QLabel("Creá o abrí un proyecto para ver la estimación.")
        self.storage_estimate_label.setWordWrap(True)
        storage_layout.addWidget(self.storage_estimate_label)

        path_row = QHBoxLayout()
        self.output_path_label = QLabel("Carpeta del proyecto: —")
        self.output_path_label.setWordWrap(True)
        open_folder_btn = QPushButton("Abrir carpeta del proyecto")
        open_folder_btn.clicked.connect(self._open_project_folder)
        path_row.addWidget(self.output_path_label, stretch=1)
        path_row.addWidget(open_folder_btn)
        storage_layout.addLayout(path_row)

        root.addWidget(storage_box)

        # 03 CAPTURA AUTOMÁTICA
        capture_box = QGroupBox("03 Captura automática")
        capture_layout = QVBoxLayout(capture_box)

        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 100000)
        self.batch_spin.setValue(100)
        capture_layout.addWidget(QLabel("Fotogramas por tanda"))
        capture_layout.addWidget(self.batch_spin)

        buttons_row = QHBoxLayout()
        self.start_button = QPushButton("Iniciar / reanudar →")
        self.start_button.clicked.connect(self._start_or_resume)
        self.pause_button = QPushButton("Pausar al terminar fotograma")
        self.pause_button.clicked.connect(self._pause)
        self.stop_button = QPushButton("DETENER AHORA")
        self.stop_button.clicked.connect(self._stop)
        buttons_row.addWidget(self.start_button)
        buttons_row.addWidget(self.pause_button)
        buttons_row.addWidget(self.stop_button)
        capture_layout.addLayout(buttons_row)

        single_btn = QPushButton("Captura única · sin avance")
        single_btn.clicked.connect(self._capture_single)
        capture_layout.addWidget(single_btn)

        self.counter_label = QLabel("Guardados / aceptados: 0 / 0")
        capture_layout.addWidget(self.counter_label)

        self.frame_log = QTextEdit()
        self.frame_log.setReadOnly(True)
        self.frame_log.setMaximumHeight(140)
        self.frame_log.setPlaceholderText(
            "Acá va apareciendo, fotograma a fotograma, si la cámara confirma que quedó en la "
            "posición esperada (perforaciones alineadas contra la Referencia 1) o si hay que revisar algo."
        )
        capture_layout.addWidget(self.frame_log)

        root.addWidget(capture_box)

        export_btn = QPushButton("Exportar proyecto · copia verificada SHA-256")
        export_btn.clicked.connect(self._export_project)
        root.addWidget(export_btn)

        self.export_status_label = QLabel("")
        root.addWidget(self.export_status_label)

        ctx.config_changed.connect(self._sync_from_config)

    def _sync_from_config(self) -> None:
        self.format_combo.setCurrentText(self._ctx.config.calibration.film_format)
        # la carpeta de proyectos puede haber cambiado (project_manager se recrea en apply_config)
        self._reload_project_list()

    # --- proyecto ---
    def _reload_project_list(self) -> None:
        self.project_combo.clear()
        for project in self._ctx.project_manager.list_projects():
            self.project_combo.addItem(f"{project.name} · {project.project_id}", userData=project.project_id)

    def _create_project(self) -> None:
        project = self._ctx.project_manager.create_project(
            name=self.name_edit.text().strip() or "Sin nombre",
            film_format=self.format_combo.currentText(),
            camera_type=self._ctx.camera_type,
        )
        self._reload_project_list()
        self._ctx.activate_project(project)
        self.project_status_label.setText(f"Proyecto activo: {project.name} ({project.project_id})")
        # Un proyecto recién creado arranca en 0 — sin este reset, quedaba
        # pegado el contador del proyecto anterior (confuso: parecía que
        # el nuevo proyecto ya tenía fotogramas guardados).
        self.counter_label.setText("Guardados / aceptados: 0 / 0")
        self.frame_log.clear()
        self._refresh_storage_estimate()

    def _open_selected_project(self) -> None:
        project_id = self.project_combo.currentData()
        if not project_id:
            self.project_status_label.setText("No hay proyectos para abrir todavía.")
            return
        project = self._ctx.project_manager.open_project(project_id)
        self._ctx.activate_project(project)
        self.project_status_label.setText(f"Proyecto activo: {project.name} ({project.project_id})")
        self.counter_label.setText(f"Guardados / aceptados: {project.frames_saved} / {project.frames_saved}")
        self._refresh_storage_estimate()

    # --- estimación de espacio ---
    def _refresh_storage_estimate(self) -> None:
        if self._ctx.storage is None:
            self.storage_estimate_label.setText("Creá o abrí un proyecto para ver la estimación.")
            self.output_path_label.setText("Carpeta del proyecto: —")
            return

        self.output_path_label.setText(f"Carpeta del proyecto: {self._ctx.storage.project_dir}")

        estimate = estimate_storage(
            self._ctx.storage,
            expected_frame_count=self.total_frames_spin.value(),
            camera_type=self._ctx.camera_type,
        )

        tipo = "aproximado por tipo de cámara" if estimate.is_estimate else "calculado sobre fotogramas ya guardados"
        texto = (
            f"Tamaño promedio por fotograma: {human_size(estimate.average_bytes_per_frame)} ({tipo}).\n"
            f"Espacio total estimado para {max(estimate.expected_frame_count, estimate.frames_saved)} fotogramas: "
            f"{human_size(estimate.estimated_total_bytes)}.\n"
            f"Ya ocupado: {human_size(estimate.bytes_used)} ({estimate.frames_saved} fotogramas guardados).\n"
            f"Espacio libre en disco: {human_size(estimate.free_disk_bytes)}."
        )
        if not estimate.fits_on_disk():
            texto += "\n⚠ El espacio libre podría no alcanzar para terminar el rollo completo."
            self.storage_estimate_label.setStyleSheet("color: #e74c3c;")
        else:
            self.storage_estimate_label.setStyleSheet("")
        self.storage_estimate_label.setText(texto)

    def _open_project_folder(self) -> None:
        if self._ctx.storage is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._ctx.storage.project_dir)))

    # --- captura ---
    def _capture_single(self) -> None:
        if self._ctx.scan_controller is None:
            self.project_status_label.setText("Abrí o creá un proyecto primero.")
            return
        try:
            result = self._ctx.scan_controller.capture_single()
        except ScanControllerError as exc:
            self.project_status_label.setText(str(exc))
            return
        self._on_frame_processed(result)

    def _start_or_resume(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.resume()
            return
        if self._ctx.scan_controller is None:
            self.project_status_label.setText("Abrí o creá un proyecto primero.")
            return

        self._worker = ScanWorker(self._ctx.scan_controller, self.batch_spin.value())
        self._batch_had_error = False
        self._worker.frame_processed.connect(self._on_frame_processed)
        self._worker.scan_error.connect(self._on_scan_error)
        self._worker.finished_batch.connect(self._on_batch_finished)
        self._worker.start()

    def _on_scan_error(self, msg: str) -> None:
        self._batch_had_error = True
        self.project_status_label.setText(f"Error: {msg}")
        self.frame_log.append(f'<span style="color:#e74c3c;">⛔ {msg}</span>')

    def _on_batch_finished(self) -> None:
        # "Tanda finalizada." NO debe pisar un mensaje de error: antes
        # siempre se mostraba, incluso cuando la tanda falló de entrada
        # (ej. "Calibración incompleta") y se guardaron 0 fotogramas,
        # ocultándole al operador que algo salió mal.
        if not self._batch_had_error:
            self.project_status_label.setText("Tanda finalizada.")

    def _pause(self) -> None:
        if self._worker is not None:
            self._worker.request_pause()

    def _stop(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()

    def _on_frame_processed(self, result: FrameResult) -> None:
        total = self._ctx.scan_controller.frames_saved if self._ctx.scan_controller else 0
        self.counter_label.setText(f"Guardados / aceptados: {total} / {total} · {result.alignment.as_label()}")
        color = "#2ecc71" if result.alignment.ok else "#e67e22"
        self.frame_log.append(f'<span style="color:{color};">{result.status_message}</span>')
        if self._ctx.current_project is not None:
            self._ctx.project_manager.update_frames_saved(self._ctx.current_project.project_id, total)
        self._refresh_storage_estimate()

    def _export_project(self) -> None:
        if self._ctx.current_project is None:
            self.export_status_label.setText("No hay proyecto activo para exportar.")
            return
        manifest = self._ctx.project_manager.export_project(self._ctx.current_project.project_id)
        self.export_status_label.setText(
            f"Exportado: {manifest['frame_count']} archivos verificados con SHA-256 en {manifest['project_dir']}"
        )
