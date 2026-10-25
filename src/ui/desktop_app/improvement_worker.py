"""Envuelve core.post_stabilization.apply_improvement en un QThread, igual
que scan_worker.py envuelve el escaneo en vivo — para no congelar la UI
durante una corrida larga (un rollo entero puede tardar minutos u horas,
sobre todo en una Raspberry Pi) y para poder pedirle que se detenga de
forma cooperativa entre fotogramas."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QThread, Signal

from ...core.post_stabilization import ImprovedFrameResult, apply_improvement
from ...storage.raw_dng_writer import ProjectStorage
from ...vision.perforation_detection import SearchZone
from ...vision.stabilization import ReferenceBox


class ImprovementWorker(QThread):
    frame_processed = Signal(object)  # ImprovedFrameResult
    finished_run = Signal(list)  # List[ImprovedFrameResult] de esta corrida

    def __init__(
        self,
        storage: ProjectStorage,
        left_zone: SearchZone,
        right_zone: SearchZone,
        reference_box: ReferenceBox,
        rotation_deg: int = 0,
        max_frames: Optional[int] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._storage = storage
        self._left_zone = left_zone
        self._right_zone = right_zone
        self._reference_box = reference_box
        self._rotation_deg = rotation_deg
        self._max_frames = max_frames
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        results: List[ImprovedFrameResult] = apply_improvement(
            self._storage,
            self._left_zone,
            self._right_zone,
            self._reference_box,
            rotation_deg=self._rotation_deg,
            max_frames=self._max_frames,
            on_frame_processed=lambda result: self.frame_processed.emit(result),
            should_stop=lambda: self._stop_requested,
        )
        self.finished_run.emit(results)
