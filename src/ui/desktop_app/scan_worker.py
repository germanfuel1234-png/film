"""Envuelve ScanController.run_batch en un QThread para no congelar la UI
mientras corre la captura automática por tandas."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ...core.scan_controller import FrameResult, ScanController


class ScanWorker(QThread):
    frame_processed = Signal(object)  # FrameResult
    scan_error = Signal(str)
    finished_batch = Signal()

    def __init__(self, scan_controller: ScanController, frame_count: int, parent=None) -> None:
        super().__init__(parent)
        self._scan_controller = scan_controller
        self._frame_count = frame_count

    def run(self) -> None:
        self._scan_controller.run_batch(
            self._frame_count,
            on_frame_processed=lambda result: self.frame_processed.emit(result),
            on_error=lambda exc: self.scan_error.emit(str(exc)),
        )
        self.finished_batch.emit()

    def request_pause(self) -> None:
        self._scan_controller.request_pause()

    def resume(self) -> None:
        self._scan_controller.resume()

    def request_stop(self) -> None:
        self._scan_controller.request_stop()
