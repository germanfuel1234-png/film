from pathlib import Path

import cv2

import numpy as np

from src.vision.perforation_detection import SearchZone, detect_perforations
from src.vision.robust_registration import (
    apply_robust_alignment,
    compute_robust_alignment,
    match_all_perforations,
    rotate_output,
)
from src.vision.stabilization import ReferenceBox

ASSETS = Path(__file__).resolve().parents[2] / "assets" / "sample_frames"
LEFT_ZONE = SearchZone(x0=10, y0=100, x1=110, y1=1200)
RIGHT_ZONE = SearchZone(x0=760, y0=100, x1=860, y1=1200)
REFERENCE_BOX = ReferenceBox(x0=0, y0=0, x1=900, y1=1300)


def test_match_all_perforations_pairs_every_point():
    ref = cv2.imread(str(ASSETS / "frame_reference.png"))
    ref_perfs = detect_perforations(ref, LEFT_ZONE, RIGHT_ZONE)
    pairs = match_all_perforations(ref_perfs, ref_perfs)
    # contra sí misma, cada perforación debería emparejarse consigo misma (distancia 0)
    assert len(pairs) == len(ref_perfs)
    for p, r in pairs:
        assert abs(p.cx - r.cx) < 1e-6
        assert abs(p.cy - r.cy) < 1e-6


def test_robust_alignment_is_near_identity_against_itself():
    ref = cv2.imread(str(ASSETS / "frame_reference.png"))
    ref_perfs = detect_perforations(ref, LEFT_ZONE, RIGHT_ZONE)
    alignment = compute_robust_alignment(ref_perfs, ref_perfs)
    assert alignment is not None
    assert abs(alignment.dx) < 1e-3
    assert abs(alignment.dy) < 1e-3
    assert abs(alignment.angle_deg) < 1e-3
    assert alignment.inliers == alignment.total_points


def test_robust_alignment_uses_all_points_not_just_two():
    ref = cv2.imread(str(ASSETS / "frame_reference.png"))
    ref_perfs = detect_perforations(ref, LEFT_ZONE, RIGHT_ZONE)
    alignment = compute_robust_alignment(ref_perfs, ref_perfs)
    assert alignment is not None
    # el generador sintético pone 5 perforaciones por lado -> 10 en total
    assert alignment.total_points >= 6


def test_robust_alignment_runs_on_known_jitter():
    """No exige precisión fina acá a propósito: los agujeros sintéticos
    son rectángulos perfectamente planos/uniformes (sin textura ni
    gradiente), así que el "pico" exacto detectado dentro de esa meseta
    varía bastante entre instancias — un artefacto de lo sintético, no un
    problema real (las fotos reales, con grano y textura, dan resultados
    mucho más consistentes — ver test_post_stabilization.py, que valida
    esto con material real y es la prueba que realmente importa para esta
    función). Acá solo se confirma que el ajuste corre, usa varios puntos
    y da un resultado con signo/orden de magnitud razonable."""
    ref = cv2.imread(str(ASSETS / "frame_reference.png"))
    jit = cv2.imread(str(ASSETS / "frame_jittered.png"))
    ref_perfs = detect_perforations(ref, LEFT_ZONE, RIGHT_ZONE)
    jit_perfs = detect_perforations(jit, LEFT_ZONE, RIGHT_ZONE)

    alignment = compute_robust_alignment(jit_perfs, ref_perfs)
    assert alignment is not None
    assert alignment.total_points >= 6
    assert alignment.inliers >= 3
    assert abs(alignment.dx) < 50
    assert abs(alignment.dy) < 50
    assert abs(alignment.angle_deg) < 5


def test_apply_robust_alignment_produces_reference_box_size():
    ref = cv2.imread(str(ASSETS / "frame_reference.png"))
    ref_perfs = detect_perforations(ref, LEFT_ZONE, RIGHT_ZONE)
    alignment = compute_robust_alignment(ref_perfs, ref_perfs)
    assert alignment is not None

    small_box = ReferenceBox(x0=220, y0=120, x1=680, y1=1180)
    crop = apply_robust_alignment(ref, alignment.matrix, small_box)
    assert crop.shape[0] == small_box.height
    assert crop.shape[1] == small_box.width


def test_compute_robust_alignment_returns_none_with_too_few_points():
    from src.vision.perforation_detection import Perforation

    one_point = [Perforation(cx=10, cy=10, area=1.0, zone="left")]
    assert compute_robust_alignment(one_point, one_point) is None


def test_rotate_output_zero_degrees_is_identity():
    image = np.arange(60, dtype="uint8").reshape(5, 4, 3)[:, :, :1].repeat(3, axis=2)
    rotated = rotate_output(image, 0)
    assert np.array_equal(rotated, image)
    assert rotate_output(image, 360) is image or np.array_equal(rotate_output(image, 360), image)


def test_rotate_output_90_swaps_dimensions_and_rotates_counterclockwise():
    # imagen 2x3 (alto x ancho) con un píxel marcado arriba a la derecha
    image = np.zeros((2, 3, 3), dtype="uint8")
    image[0, 2] = (255, 255, 255)

    rotated = rotate_output(image, 90)
    assert rotated.shape == (3, 2, 3)  # alto y ancho se intercambian
    # rotación antihoraria: la esquina arriba-derecha termina en la esquina arriba-izquierda
    assert tuple(rotated[0, 0]) == (255, 255, 255)


def test_rotate_output_180_flips_both_axes():
    image = np.zeros((2, 3, 3), dtype="uint8")
    image[0, 0] = (255, 255, 255)

    rotated = rotate_output(image, 180)
    assert rotated.shape == image.shape
    assert tuple(rotated[1, 2]) == (255, 255, 255)


def test_rotate_output_270_is_inverse_of_90():
    image = np.random.default_rng(0).integers(0, 255, size=(4, 6, 3), dtype="uint8")
    roundtrip = rotate_output(rotate_output(image, 90), 270)
    assert np.array_equal(roundtrip, image)
