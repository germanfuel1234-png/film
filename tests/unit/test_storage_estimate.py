from src.core.storage_estimate import estimate_storage, human_size
from src.hardware.camera_base import CapturedFrame
from src.storage.raw_dng_writer import ProjectStorage


def test_human_size_formats_units():
    assert human_size(500) == "500.0 B"
    assert human_size(2048) == "2.0 KB"
    assert human_size(5 * 1024 * 1024) == "5.0 MB"
    assert human_size(3 * 1024**3) == "3.0 GB"


def test_estimate_uses_approx_table_when_no_frames_saved(tmp_path):
    storage = ProjectStorage(tmp_path / "proyecto")
    estimate = estimate_storage(storage, expected_frame_count=1000, camera_type="industrial")

    assert estimate.frames_saved == 0
    assert estimate.is_estimate is True
    assert estimate.average_bytes_per_frame == 1920 * 1200
    assert estimate.estimated_total_bytes == 1920 * 1200 * 1000
    assert estimate.free_disk_bytes > 0


def test_estimate_uses_real_average_once_frames_exist(tmp_path):
    storage = ProjectStorage(tmp_path / "proyecto")
    # dos fotogramas "guardados" de 1000 y 3000 bytes -> promedio real 2000
    storage.save_frame(CapturedFrame(raw_bytes=b"x" * 1000, file_extension=".raw", width=10, height=10, frame_index=0))
    storage.save_frame(CapturedFrame(raw_bytes=b"x" * 3000, file_extension=".raw", width=10, height=10, frame_index=1))

    estimate = estimate_storage(storage, expected_frame_count=10, camera_type="industrial")

    assert estimate.frames_saved == 2
    assert estimate.bytes_used == 4000
    assert estimate.average_bytes_per_frame == 2000
    assert estimate.is_estimate is False
    # usa el máximo entre fotogramas ya guardados y el total esperado
    assert estimate.estimated_total_bytes == 2000 * 10


def test_estimate_total_never_smaller_than_frames_already_saved(tmp_path):
    storage = ProjectStorage(tmp_path / "proyecto")
    storage.save_frame(CapturedFrame(raw_bytes=b"x" * 1000, file_extension=".raw", width=10, height=10, frame_index=0))

    # el operador puso un total esperado menor a lo ya guardado (dato mal cargado)
    estimate = estimate_storage(storage, expected_frame_count=0, camera_type="industrial")

    assert estimate.estimated_total_bytes == 1000 * 1  # usa frames_saved, no expected_frame_count
