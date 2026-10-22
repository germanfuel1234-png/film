"""Máquina de estados del ciclo de escaneo automatizado — el módulo detrás
de la pestaña "Escaneo" del prototipo.

Ciclo por fotograma (ver ESPECIFICACIONES_PROYECTO.md §3.B):
    avanzar película -> detectar perforación -> frenar -> disparar cámara
    -> estabilizar/recortar -> guardar -> repetir

Esta clase es agnóstica de framework (no depende de PySide6): expone
callbacks simples (`on_frame_processed`, `on_error`) para que la capa de
UI la envuelva en un QThread sin acoplar la lógica de negocio a Qt.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

from ..hardware.camera_base import CameraDriver
from ..hardware.motor.stepper_motor import StepperMotor
from ..vision.perforation_detection import detect_perforations, match_pair_to_reference
from ..vision.stabilization import AlignmentResult, compute_offset
from .calibration import Calibrator
from ..storage.raw_dng_writer import ProjectStorage


class ScanControllerError(RuntimeError):
    pass


@dataclass
class FrameResult:
    frame_index: int
    alignment: AlignmentResult
    raw_path: Path


class ScanController:
    def __init__(
        self,
        camera: CameraDriver,
        motor: StepperMotor,
        calibrator: Calibrator,
        storage: ProjectStorage,
        steps_per_frame: int = 1000,
    ) -> None:
        self._camera = camera
        self._motor = motor
        self._calibrator = calibrator
        self._storage = storage
        self.steps_per_frame = steps_per_frame
        # Continúa después del último fotograma ya guardado en disco (si lo
        # hay): así "Abrir / reanudar" un proyecto existente no vuelve a
        # numerar desde 0 y sobrescribe los archivos ya guardados.
        self.frames_saved = storage.next_frame_index()

        self._stop_requested = False
        self._pause_requested = False

    # --- control del ciclo (botones "Iniciar/reanudar", "Pausar al
    # terminar fotograma", "DETENER AHORA" del prototipo) ---
    def request_stop(self) -> None:
        self._stop_requested = True

    def request_pause(self) -> None:
        self._pause_requested = True

    def resume(self) -> None:
        self._pause_requested = False

    # --- captura manual, sin avance ("Captura única · sin avance") ---
    def capture_single(self) -> FrameResult:
        return self._process_one_frame(advance_motor=False)

    # --- ciclo automático por tandas ("Fotogramas por tanda") ---
    def run_batch(
        self,
        frame_count: int,
        on_frame_processed: Optional[Callable[[FrameResult], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        poll_interval_s: float = 0.05,
    ) -> None:
        if not self._calibrator.is_ready_for_scan():
            error = ScanControllerError(
                "Calibración incompleta: hacen falta zonas de búsqueda, encuadre de referencia y Referencia 1 "
                "antes de iniciar el escaneo automático."
            )
            if on_error:
                on_error(error)
                return
            raise error

        self._stop_requested = False
        for _ in range(frame_count):
            if self._stop_requested:
                break
            while self._pause_requested and not self._stop_requested:
                time.sleep(poll_interval_s)
            if self._stop_requested:
                break
            try:
                result = self._process_one_frame(advance_motor=True)
            except Exception as exc:  # noqa: BLE001 — se reporta vía callback, no se oculta
                if on_error:
                    on_error(exc)
                break
            if on_frame_processed:
                on_frame_processed(result)

    def _process_one_frame(self, advance_motor: bool) -> FrameResult:
        if advance_motor:
            self._motor.move(self.steps_per_frame)

        preview = self._camera.get_preview_frame()
        calib = self._calibrator.state
        perforations = detect_perforations(preview, calib.left_zone, calib.right_zone)
        pair = match_pair_to_reference(perforations, calib.reference_pair)
        if pair is None:
            raise ScanControllerError(f"No se detectaron perforaciones en el fotograma {self.frames_saved}.")

        alignment = compute_offset(calib.reference_pair, pair)

        captured = self._camera.trigger_capture(self.frames_saved)
        raw_path = self._storage.save_frame(captured)
        self._storage.save_correction(self.frames_saved, alignment, asdict(calib.reference_box))

        self.frames_saved += 1
        return FrameResult(frame_index=self.frames_saved - 1, alignment=alignment, raw_path=raw_path)
