from pathlib import Path

import cv2
import pytest

from src.vision.perforation_detection import SearchZone, best_perforation_pair, detect_perforations, match_pair_to_reference
from src.vision.stabilization import ReferenceBox, apply_crop, compute_offset

ASSETS = Path(__file__).resolve().parents[2] / "assets" / "sample_frames"
LEFT_ZONE = SearchZone(x0=10, y0=100, x1=110, y1=1200)
RIGHT_ZONE = SearchZone(x0=760, y0=100, x1=860, y1=1200)
REFERENCE_BOX = ReferenceBox(x0=220, y0=120, x1=680, y1=1180)


def _pair_for(path: Path):
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    assert img is not None
    perforations = detect_perforations(img, LEFT_ZONE, RIGHT_ZONE)
    pair = best_perforation_pair(perforations)
    assert pair is not None
    return img, pair


def test_offset_is_near_zero_against_itself():
    _, pair = _pair_for(ASSETS / "frame_reference.png")
    alignment = compute_offset(pair, pair)
    assert abs(alignment.dx) < 1e-3
    assert abs(alignment.dy) < 1e-3
    assert abs(alignment.angle_deg) < 1e-3
    assert alignment.ok


def test_offset_detects_known_jitter():
    # frame_jittered.png fue generado con offset_x=9, offset_y=-14, angle=0.6°
    # (ver proyecto_film/assets/sample_frames) — el detector debe recuperar
    # valores cercanos a esos, con tolerancia por el recorte/ruido de grano.
    # Importante: hay 5 perforaciones por columna, así que hay que matchear
    # contra la MISMA perforación de referencia (match_pair_to_reference),
    # no tomar la de mayor área de forma independiente en cada frame.
    ref_frame, ref_pair = _pair_for(ASSETS / "frame_reference.png")
    cur_frame = cv2.imread(str(ASSETS / "frame_jittered.png"), cv2.IMREAD_COLOR)
    cur_perforations = detect_perforations(cur_frame, LEFT_ZONE, RIGHT_ZONE)
    cur_pair = match_pair_to_reference(cur_perforations, ref_pair)
    assert cur_pair is not None

    alignment = compute_offset(ref_pair, cur_pair)

    # angle_deg es el ángulo de CORRECCIÓN a aplicar en apply_crop (no el
    # ángulo físico aplicado al generar el frame): por eso el signo queda
    # invertido respecto al +0.6° usado en el generador sintético. Es el
    # mismo ángulo que luego cv2.getRotationMatrix2D usa para cancelar la
    # rotación real del fotograma — ver vision/stabilization.apply_crop.
    assert 4 <= alignment.dx <= 14
    assert -19 <= alignment.dy <= -9
    assert -1.0 <= alignment.angle_deg <= -0.2


def test_apply_crop_produces_reference_box_size():
    frame, ref_pair = _pair_for(ASSETS / "frame_reference.png")
    alignment = compute_offset(ref_pair, ref_pair)
    crop = apply_crop(frame, REFERENCE_BOX, alignment)
    assert crop.shape[0] == REFERENCE_BOX.height
    assert crop.shape[1] == REFERENCE_BOX.width


def test_apply_crop_actually_realigns_jittered_frame():
    """Verificación geométrica end-to-end: tras aplicar la corrección, las
    perforaciones del fotograma corregido deben caer cerca de donde están
    en la referencia — no solo confiar en los signos de dx/dy/ángulo."""
    ref_frame, ref_pair = _pair_for(ASSETS / "frame_reference.png")
    cur_frame = cv2.imread(str(ASSETS / "frame_jittered.png"), cv2.IMREAD_COLOR)
    cur_perforations = detect_perforations(cur_frame, LEFT_ZONE, RIGHT_ZONE)
    cur_pair = match_pair_to_reference(cur_perforations, ref_pair)
    alignment = compute_offset(ref_pair, cur_pair)

    full_frame_box = ReferenceBox(x0=0, y0=0, x1=cur_frame.shape[1], y1=cur_frame.shape[0])
    corrected = apply_crop(cur_frame, full_frame_box, alignment)

    corrected_perforations = detect_perforations(corrected, LEFT_ZONE, RIGHT_ZONE)
    corrected_pair = match_pair_to_reference(corrected_perforations, ref_pair)
    assert corrected_pair is not None

    ref_left, ref_right = ref_pair
    corr_left, corr_right = corrected_pair
    # tolerancia generosa por el recorte duro en bordes al rotar/trasladar
    assert abs(corr_left.cx - ref_left.cx) < 3.0
    assert abs(corr_left.cy - ref_left.cy) < 3.0
    assert abs(corr_right.cx - ref_right.cx) < 3.0
    assert abs(corr_right.cy - ref_right.cy) < 3.0
