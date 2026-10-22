"""Prueba de regresión contra fotos reales del cliente (no sintéticas).

Las fotos vienen de "fotogramas y especificaciones" que mandó el cliente:
35mm retroiluminado, resolución 1920x1080, con la cámara de prueba Canon
(no la industrial Huateng definitiva — ver ESPECIFICACIONES_PROYECTO.md).
Las perforaciones están arriba y abajo de cada fotograma (orientación
horizontal), a diferencia de los assets sintéticos (orientación vertical,
izquierda/derecha) — por eso estas zonas son top/bottom en vez de left/right,
aunque el código las llama "left"/"right" internamente (son solo etiquetas).

Esta prueba detectó originalmente el bug del umbral de Otsu fusionando
perforaciones adyacentes (reemplazado por detección por proyección+picos)
y el bug de alineación de fila en best_perforation_pair — ver historial.
"""

from pathlib import Path

import cv2
import pytest

from src.vision.perforation_detection import SearchZone, best_perforation_pair, detect_perforations, match_pair_to_reference
from src.vision.stabilization import compute_offset

REAL_FRAMES = Path(__file__).resolve().parents[2] / "assets" / "real_frames"

# Banda de perforaciones arriba/abajo, excluyendo el vignette negro de los
# bordes izquierdo/derecho de la foto (ver notas de calibración).
TOP_ZONE = SearchZone(x0=380, y0=0, x1=1600, y1=150)
BOTTOM_ZONE = SearchZone(x0=380, y0=1015, x1=1600, y1=1080)


@pytest.fixture
def photo_2250():
    img = cv2.imread(str(REAL_FRAMES / "_MG_2250.JPG"))
    assert img is not None, "Faltan las fotos reales en assets/real_frames/"
    return img


@pytest.fixture
def photo_2260():
    img = cv2.imread(str(REAL_FRAMES / "_MG_2260.JPG"))
    assert img is not None
    return img


def test_detects_most_perforations_in_real_photo(photo_2250):
    perfs = detect_perforations(photo_2250, TOP_ZONE, BOTTOM_ZONE)
    top = [p for p in perfs if p.zone == "left"]
    bottom = [p for p in perfs if p.zone == "right"]
    # hay 7-8 perforaciones visibles en cada banda; toleramos alguna perdida
    # por recorte en el borde de la foto
    assert len(top) >= 6
    assert len(bottom) >= 6


def test_reference_pair_is_column_aligned(photo_2250):
    """El par elegido como referencia tiene que corresponder a la misma
    columna física arriba y abajo (no una perforación cualquiera de cada
    banda) — esto fue el bug de best_perforation_pair."""
    perfs = detect_perforations(photo_2250, TOP_ZONE, BOTTOM_ZONE)
    pair = best_perforation_pair(perfs)
    assert pair is not None
    top, bottom = pair
    assert abs(top.cx - bottom.cx) < 10.0  # misma columna, tolerancia por ruido de detección


def test_cross_frame_alignment_is_bounded(photo_2250, photo_2260):
    """Comparando dos fotos reales distintas del mismo setup, el offset
    calculado tiene que ser un número razonable (no un disparate de cientos
    de píxeles ni NaN), confirmando que el pipeline completo funciona
    sobre material real, no solo sobre los fotogramas sintéticos de prueba."""
    ref_perfs = detect_perforations(photo_2250, TOP_ZONE, BOTTOM_ZONE)
    ref_pair = best_perforation_pair(ref_perfs)
    assert ref_pair is not None

    cur_perfs = detect_perforations(photo_2260, TOP_ZONE, BOTTOM_ZONE)
    cur_pair = match_pair_to_reference(cur_perfs, ref_pair)
    assert cur_pair is not None

    alignment = compute_offset(ref_pair, cur_pair)
    assert abs(alignment.dx) < 100
    assert abs(alignment.dy) < 100
    assert abs(alignment.angle_deg) < 5
