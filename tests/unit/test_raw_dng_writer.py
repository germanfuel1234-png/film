from src.hardware.camera_base import CapturedFrame
from src.storage.raw_dng_writer import ProjectStorage


def test_next_frame_index_starts_at_zero_for_empty_project(tmp_path):
    storage = ProjectStorage(tmp_path / "proyecto")
    assert storage.next_frame_index() == 0


def test_next_frame_index_continues_after_last_saved_frame(tmp_path):
    storage = ProjectStorage(tmp_path / "proyecto")
    storage.save_frame(CapturedFrame(raw_bytes=b"a", file_extension=".raw", width=1, height=1, frame_index=0))
    storage.save_frame(CapturedFrame(raw_bytes=b"b", file_extension=".raw", width=1, height=1, frame_index=1))
    storage.save_frame(CapturedFrame(raw_bytes=b"c", file_extension=".raw", width=1, height=1, frame_index=2))

    assert storage.next_frame_index() == 3


def test_next_frame_index_handles_gaps_by_using_the_highest_index(tmp_path):
    storage = ProjectStorage(tmp_path / "proyecto")
    storage.save_frame(CapturedFrame(raw_bytes=b"a", file_extension=".raw", width=1, height=1, frame_index=0))
    storage.save_frame(CapturedFrame(raw_bytes=b"c", file_extension=".raw", width=1, height=1, frame_index=7))  # borraron el 1-6

    assert storage.next_frame_index() == 8


def test_next_frame_index_ignores_unrelated_files(tmp_path):
    storage = ProjectStorage(tmp_path / "proyecto")
    storage.save_frame(CapturedFrame(raw_bytes=b"a", file_extension=".raw", width=1, height=1, frame_index=0))
    (storage.raw_dir / "notas.txt").write_text("algo que no es un fotograma")

    assert storage.next_frame_index() == 1
