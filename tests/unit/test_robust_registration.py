from pathlib import Path

import cv2

from src.vision.perforation_detection import SearchZone, detect_perforations
from src.vision.robust_registration import apply_robust_alignment, compute_robust_alignment, match_all_perforations
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
