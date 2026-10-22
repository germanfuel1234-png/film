from pathlib import Path

import cv2
import pytest

from src.vision.perforation_detection import SearchZone, best_perforation_pair, detect_perforations

ASSETS = Path(__file__).resolve().parents[2] / "assets" / "sample_frames"

# Coordenadas usadas por el generador sintético (ver assets/sample_frames):
# columnas de perforaciones en x=60 (izquierda) y x=800 (derecha), ancho ~70px.
LEFT_ZONE = SearchZone(x0=10, y0=100, x1=110, y1=1200)
RIGHT_ZONE = SearchZone(x0=760, y0=100, x1=860, y1=1200)


@pytest.fixture
def reference_frame():
    img = cv2.imread(str(ASSETS / "frame_reference.png"), cv2.IMREAD_COLOR)
    assert img is not None, "No se pudo cargar frame_reference.png: ¿se generaron los assets sintéticos?"
    return img


def test_detects_perforations_in_both_zones(reference_frame):
    perforations = detect_perforations(reference_frame, LEFT_ZONE, RIGHT_ZONE)
    left = [p for p in perforations if p.zone == "left"]
    right = [p for p in perforations if p.zone == "right"]

    assert len(left) >= 4
    assert len(right) >= 4


def test_best_pair_picks_one_per_side(reference_frame):
    perforations = detect_perforations(reference_frame, LEFT_ZONE, RIGHT_ZONE)
    pair = best_perforation_pair(perforations)
    assert pair is not None
    left, right = pair
    assert left.zone == "left"
    assert right.zone == "right"
    assert left.cx < right.cx  # la izquierda debe quedar a la izquierda de la derecha
