"""Pruebas de la vista "tira de película" (core/filmstrip.py): apilar
varios fotogramas de 'mejorado/' para verificar visualmente que calzan
sin saltos, el pedido del cliente de ver la secuencia como una tira de
película real."""

import shutil
from pathlib import Path

import cv2
import pytest

from src.core.filmstrip import build_filmstrip, list_improved_frames
from src.core.post_stabilization import apply_improvement
from src.storage.raw_dng_writer import ProjectStorage
from src.vision.perforation_detection import SearchZone
from src.vision.stabilization import ReferenceBox

REAL_FRAMES = Path(__file__).resolve().parents[2] / "assets" / "real_frames"
TOP_ZONE = SearchZone(x0=380, y0=0, x1=1600, y1=150)
BOTTOM_ZONE = SearchZone(x0=380, y0=1015, x1=1600, y1=1080)
REFERENCE_BOX = ReferenceBox(x0=700, y0=0, x1=1360, y1=1020)


@pytest.fixture
def project_with_improved_frames(tmp_path):
    storage = ProjectStorage(tmp_path / "proyecto")
    files = sorted(REAL_FRAMES.glob("*.JPG"))[:8]
    assert files, "Faltan las fotos reales en assets/real_frames/"
    for f in files:
        shutil.copy(f, storage.raw_dir / f.name.replace("_MG_", "frame_"))
    apply_improvement(storage, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX)
    return storage


def test_list_improved_frames_returns_sorted_paths(project_with_improved_frames):
    frames = list_improved_frames(project_with_improved_frames)
    assert len(frames) == 8
    assert frames == sorted(frames)


def test_list_improved_frames_empty_before_apply_improvement(tmp_path):
    storage = ProjectStorage(tmp_path / "proyecto_sin_mejora")
    assert list_improved_frames(storage) == []


def test_build_filmstrip_stacks_requested_count_vertically(project_with_improved_frames):
    frames = list_improved_frames(project_with_improved_frames)
    one_frame = cv2.imread(str(frames[0]))

    strip = build_filmstrip(frames, start=0, count=4)
    assert strip is not None
    assert strip.shape[1] == one_frame.shape[1]  # mismo ancho
    assert strip.shape[0] == one_frame.shape[0] * 4  # 4 fotogramas apilados


def test_build_filmstrip_respects_start_offset(project_with_improved_frames):
    frames = list_improved_frames(project_with_improved_frames)
    strip_from_zero = build_filmstrip(frames, start=0, count=2)
    strip_from_two = build_filmstrip(frames, start=2, count=2)
    assert strip_from_zero is not None and strip_from_two is not None
    assert strip_from_zero.shape == strip_from_two.shape
    assert (strip_from_zero != strip_from_two).any()


def test_build_filmstrip_truncates_near_end_of_list(project_with_improved_frames):
    frames = list_improved_frames(project_with_improved_frames)
    one_frame = cv2.imread(str(frames[0]))

    strip = build_filmstrip(frames, start=len(frames) - 2, count=10)
    assert strip is not None
    assert strip.shape[0] == one_frame.shape[0] * 2


def test_build_filmstrip_with_empty_list_returns_none():
    assert build_filmstrip([], start=0, count=5) is None


def test_build_filmstrip_with_start_past_end_returns_none(project_with_improved_frames):
    frames = list_improved_frames(project_with_improved_frames)
    assert build_filmstrip(frames, start=len(frames) + 5, count=3) is None
