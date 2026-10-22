"""Prueba el ciclo completo (avanzar -> detectar -> estabilizar -> guardar)
con cámara y motor simulados, igual que corría el prototipo original en
modo 'SIMULACIÓN' sin hardware conectado.
"""

from pathlib import Path

from src.core.calibration import Calibrator
from src.core.scan_controller import ScanController
from src.hardware.camera_simulated import SimulatedCamera
from src.hardware.motor.stepper_motor import SimulatedStepperMotor
from src.storage.raw_dng_writer import ProjectStorage
from src.vision.perforation_detection import SearchZone
from src.vision.stabilization import ReferenceBox

ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets" / "sample_frames"
# Mismas coordenadas que assets/sample_frames (ver generador de assets) y que
# tests/unit/test_perforation_detection.py: SimulatedCamera.get_preview_frame()
# devuelve la imagen a resolución completa (igual que trigger_capture()), así
# que zonas y encuadre se calibran una sola vez, sin reescalar.
LEFT_ZONE = SearchZone(x0=10, y0=100, x1=110, y1=1200)
RIGHT_ZONE = SearchZone(x0=760, y0=100, x1=860, y1=1200)


def _build_calibrator(camera: SimulatedCamera) -> Calibrator:
    calibrator = Calibrator()
    calibrator.set_film_format("35mm")
    calibrator.set_search_zones(LEFT_ZONE, RIGHT_ZONE)
    calibrator.set_reference_box(ReferenceBox(x0=220, y0=120, x1=680, y1=1180))
    frame = camera.get_preview_frame()
    calibrator.mark_reference(1, frame)
    return calibrator


def test_run_batch_saves_frames_and_corrections(tmp_path):
    camera = SimulatedCamera(sample_dir=ASSETS_DIR)
    camera.connect()
    motor = SimulatedStepperMotor()
    motor.connect()
    calibrator = _build_calibrator(camera)
    storage = ProjectStorage(tmp_path / "proyecto_test")

    controller = ScanController(camera=camera, motor=motor, calibrator=calibrator, storage=storage, steps_per_frame=1000)

    processed = []
    errors = []
    controller.run_batch(3, on_frame_processed=processed.append, on_error=errors.append)

    assert not errors
    assert len(processed) == 3
    assert controller.frames_saved == 3
    assert motor.state.position_steps == 3000

    raw_files = list(storage.raw_dir.iterdir())
    correction_files = list(storage.corrections_dir.iterdir())
    assert len(raw_files) == 3
    assert len(correction_files) == 3


def test_resuming_project_does_not_overwrite_existing_frames(tmp_path):
    """Regresión: "Abrir / reanudar" un proyecto con fotogramas ya guardados
    no debe volver a numerar desde 0 (eso pisaría frame_00000, etc.)."""
    camera = SimulatedCamera(sample_dir=ASSETS_DIR)
    camera.connect()
    motor = SimulatedStepperMotor()
    motor.connect()
    calibrator = _build_calibrator(camera)
    storage = ProjectStorage(tmp_path / "proyecto_test")

    # sesión 1: se escanean 3 fotogramas y se cierra el programa
    controller_1 = ScanController(camera=camera, motor=motor, calibrator=calibrator, storage=storage)
    controller_1.run_batch(3)
    assert controller_1.frames_saved == 3
    original_frame_0_bytes = (storage.raw_dir / "frame_00000.sim.png").read_bytes()

    # sesión 2: se "abre / reanuda" el mismo proyecto (storage apunta a la
    # misma carpeta) con un ScanController nuevo, como hace AppContext al
    # reabrir un proyecto existente
    controller_2 = ScanController(camera=camera, motor=motor, calibrator=calibrator, storage=storage)
    assert controller_2.frames_saved == 3  # no vuelve a arrancar en 0

    controller_2.run_batch(2)
    assert controller_2.frames_saved == 5

    raw_files = sorted(p.name for p in storage.raw_dir.iterdir())
    assert raw_files == [f"frame_{i:05d}.sim.png" for i in range(5)]
    # el primer fotograma de la sesión 1 sigue intacto, no se pisó
    assert (storage.raw_dir / "frame_00000.sim.png").read_bytes() == original_frame_0_bytes


def test_export_manifest_has_matching_hashes(tmp_path):
    camera = SimulatedCamera(sample_dir=ASSETS_DIR)
    camera.connect()
    motor = SimulatedStepperMotor()
    motor.connect()
    calibrator = _build_calibrator(camera)
    storage = ProjectStorage(tmp_path / "proyecto_test")
    controller = ScanController(camera=camera, motor=motor, calibrator=calibrator, storage=storage)

    controller.run_batch(2)
    manifest = storage.export_manifest()

    assert manifest["frame_count"] == 2
    assert storage.verify_manifest() == []
