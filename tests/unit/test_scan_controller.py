"""Pruebas de los tres pedidos del cliente sobre el ciclo de escaneo
(core/scan_controller.py):
  1. Esperar a que asiente la vibración entre que el motor termina de
     moverse y se dispara la cámara (settle_delay_s).
  2. Chequear que el Arduino confirmó haber movido lo que se le pidió
     (no solo recibir el ACK y descartarlo).
  3. Mensaje de estado por fotograma (OK / fuera de posición) usando la
     cámara como "ojo" que corrobora contra la Referencia 1.
"""

import time
from pathlib import Path

import pytest

from src.core.calibration import Calibrator
from src.core.scan_controller import ScanController, ScanControllerError
from src.hardware.camera_simulated import SimulatedCamera
from src.hardware.motor.stepper_motor import SimulatedStepperMotor
from src.storage.raw_dng_writer import ProjectStorage
from src.vision.perforation_detection import SearchZone
from src.vision.stabilization import ReferenceBox

ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets" / "sample_frames"
LEFT_ZONE = SearchZone(x0=10, y0=100, x1=110, y1=1200)
RIGHT_ZONE = SearchZone(x0=760, y0=100, x1=860, y1=1200)


class _PartialMoveMotor(SimulatedStepperMotor):
    """Simula un Arduino que no pudo completar el avance pedido (ej. un
    atasco o un STOP a mitad de camino) — confirma menos pasos de los
    solicitados en el ACK."""

    def __init__(self, confirmed_steps: int) -> None:
        super().__init__()
        self._confirmed_steps = confirmed_steps

    def move(self, steps: int, fine: bool = False) -> int:
        super().move(steps, fine=fine)
        return self._confirmed_steps


class _SlowMotor(SimulatedStepperMotor):
    """Registra cuándo terminó de "moverse", para verificar que la cámara
    no dispara antes de que pase el settle_delay_s."""

    def __init__(self) -> None:
        super().__init__()
        self.last_move_finished_at: float = 0.0

    def move(self, steps: int, fine: bool = False) -> int:
        moved = super().move(steps, fine=fine)
        self.last_move_finished_at = time.monotonic()
        return moved


def _build_calibrator(camera: SimulatedCamera) -> Calibrator:
    calibrator = Calibrator()
    calibrator.set_film_format("35mm")
    calibrator.set_search_zones(LEFT_ZONE, RIGHT_ZONE)
    calibrator.set_reference_box(ReferenceBox(x0=220, y0=120, x1=680, y1=1180))
    frame = camera.get_preview_frame()
    calibrator.mark_reference(1, frame)
    return calibrator


def test_frame_confirmed_ok_has_status_message(tmp_path):
    camera = SimulatedCamera(sample_dir=ASSETS_DIR)
    camera.connect()
    motor = SimulatedStepperMotor()
    motor.connect()
    calibrator = _build_calibrator(camera)
    storage = ProjectStorage(tmp_path / "proyecto")

    controller = ScanController(
        camera=camera, motor=motor, calibrator=calibrator, storage=storage, steps_per_frame=1000, settle_delay_s=0.0
    )
    result = controller.capture_single()

    assert result.alignment.ok
    assert "OK" in result.status_message
    assert "0" in result.status_message or str(result.frame_index) in result.status_message


def test_settle_delay_elapses_before_capture(tmp_path):
    camera = SimulatedCamera(sample_dir=ASSETS_DIR)
    camera.connect()
    motor = _SlowMotor()
    motor.connect()
    calibrator = _build_calibrator(camera)
    storage = ProjectStorage(tmp_path / "proyecto")

    controller = ScanController(
        camera=camera, motor=motor, calibrator=calibrator, storage=storage, steps_per_frame=1000, settle_delay_s=0.2
    )

    before = time.monotonic()
    controller.run_batch(1)
    elapsed = time.monotonic() - before

    assert elapsed >= 0.2
    assert motor.last_move_finished_at > 0.0


def test_capture_single_skips_settle_delay_without_movement(tmp_path):
    """Sin avance (captura única) no tiene sentido esperar: no hubo
    vibración mecánica que asentar."""
    camera = SimulatedCamera(sample_dir=ASSETS_DIR)
    camera.connect()
    motor = SimulatedStepperMotor()
    motor.connect()
    calibrator = _build_calibrator(camera)
    storage = ProjectStorage(tmp_path / "proyecto")

    controller = ScanController(
        camera=camera, motor=motor, calibrator=calibrator, storage=storage, steps_per_frame=1000, settle_delay_s=5.0
    )

    before = time.monotonic()
    controller.capture_single()
    elapsed = time.monotonic() - before

    assert elapsed < 1.0


def test_partial_motor_confirmation_raises_clear_error(tmp_path):
    """El pedido del cliente: que el Arduino confirme lo que movió, y que
    el sistema se dé cuenta si no coincide con lo pedido en vez de
    seguir como si nada."""
    camera = SimulatedCamera(sample_dir=ASSETS_DIR)
    camera.connect()
    motor = _PartialMoveMotor(confirmed_steps=400)  # pidió 1000, confirmó 400
    motor.connect()
    calibrator = _build_calibrator(camera)
    storage = ProjectStorage(tmp_path / "proyecto")

    controller = ScanController(
        camera=camera, motor=motor, calibrator=calibrator, storage=storage, steps_per_frame=1000, settle_delay_s=0.0
    )

    with pytest.raises(ScanControllerError, match="400"):
        controller._process_one_frame(advance_motor=True)


def test_partial_motor_confirmation_is_reported_via_on_error_in_batch(tmp_path):
    camera = SimulatedCamera(sample_dir=ASSETS_DIR)
    camera.connect()
    motor = _PartialMoveMotor(confirmed_steps=400)
    motor.connect()
    calibrator = _build_calibrator(camera)
    storage = ProjectStorage(tmp_path / "proyecto")

    controller = ScanController(
        camera=camera, motor=motor, calibrator=calibrator, storage=storage, steps_per_frame=1000, settle_delay_s=0.0
    )

    errors = []
    processed = []
    controller.run_batch(3, on_frame_processed=processed.append, on_error=errors.append)

    assert not processed  # no se guardó ningún fotograma: cortó en el primero
    assert len(errors) == 1
    assert "400" in str(errors[0]) and "1000" in str(errors[0])
