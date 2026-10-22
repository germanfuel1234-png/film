"""Detección de perforaciones del film dentro de zonas de búsqueda configurables.

Las perforaciones se detectan por **proyección de brillo + picos periódicos**,
no por segmentación de blobs/contornos. Motivo: se probó primero un enfoque
de umbral (Otsu) + contornos, y funcionaba bien sobre imágenes sintéticas,
pero **falló con fotos reales de película retroiluminada**: el borde del
film entre dos perforaciones adyacentes no es opaco, deja pasar algo de luz
de fondo (la base del film es translúcida), así que el contraste entre
"agujero" y "borde entre agujeros" resultó menor que entre "borde" y
"fondo negro" — un único umbral global terminaba fusionando varias
perforaciones en un solo blob gigante en vez de separarlas.

La proyección es mucho más robusta a esto: como las perforaciones tienen un
espaciado regular y conocido, basta con promediar el brillo a lo largo del
eje de la zona (columnas si la zona es horizontal, filas si es vertical) y
buscar los picos periódicos — cada pico es el centro de una perforación,
sin necesidad de que el valle entre dos picos llegue a negro puro. Validado
contra fotogramas reales de 35mm (retroiluminados, cámara Canon de prueba):
8/8 perforaciones correctamente ubicadas donde el enfoque por contornos
encontraba 0-4 fusionadas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import cv2
import numpy as np


@dataclass
class SearchZone:
    """Rectángulo (en coordenadas de imagen) donde buscar perforaciones."""

    x0: int
    y0: int
    x1: int
    y1: int

    def crop(self, frame: np.ndarray) -> np.ndarray:
        return frame[self.y0 : self.y1, self.x0 : self.x1]


@dataclass
class Perforation:
    cx: float  # centro en coordenadas de la imagen completa
    cy: float
    area: float  # proxy de confianza (prominencia del pico), no área en px²
    zone: str  # "left" | "right"


def _find_local_maxima(signal: np.ndarray, min_distance: int, min_height: float) -> List[int]:
    """Picos de `signal` por supresión de no-máximos: toma el punto más
    alto, descarta todo lo que esté a menos de `min_distance`, repite con
    el siguiente más alto restante.

    Necesario porque el techo de una perforación es una MESETA ancha (el
    agujero es un rectángulo redondeado, no una espiga), no un pico
    afilado: una comparación ingenua "más alto que el vecino inmediato"
    cuenta varios puntos de la misma meseta como perforaciones distintas.
    """
    candidates = [i for i in range(len(signal)) if signal[i] > min_height]
    candidates.sort(key=lambda i: signal[i], reverse=True)

    accepted: List[int] = []
    for i in candidates:
        if all(abs(i - a) >= min_distance for a in accepted):
            accepted.append(i)
    return sorted(accepted)


def _parabolic_refine(signal: np.ndarray, i: int) -> float:
    """Ajusta una parábola a signal[i-1], signal[i], signal[i+1] y devuelve
    la posición (sub-píxel) de su vértice — mucho más preciso que quedarse
    con el índice entero del máximo discreto."""
    if i <= 0 or i >= len(signal) - 1:
        return float(i)
    left, center, right = signal[i - 1], signal[i], signal[i + 1]
    denom = left - 2 * center + right
    if denom == 0:
        return float(i)
    offset = 0.5 * (left - right) / denom
    return i + float(np.clip(offset, -1.0, 1.0))


def _weighted_centroid(profile: np.ndarray) -> float:
    """Centro de masa de `profile` (ya recortado a una ventana angosta
    alrededor del pico), restando el piso para no arrastrar el centro
    hacia el fondo. Da precisión sub-píxel; un argmax entero no."""
    baseline = profile.min()
    weights = profile - baseline
    total = weights.sum()
    if total <= 0:
        return (len(profile) - 1) / 2.0
    indices = np.arange(len(profile))
    return float((indices * weights).sum() / total)


def _find_perforations_in_zone(
    frame_gray: np.ndarray,
    zone: SearchZone,
    zone_name: str,
    min_spacing_px: int = 100,
    min_relative_height: float = 0.5,
) -> List[Perforation]:
    crop = zone.crop(frame_gray)
    if crop.size == 0:
        return []

    # Zona más ancha que alta -> perforaciones alineadas horizontalmente
    # (tira de film apaisada, ej. fotos de prueba reales); más alta que
    # ancha -> alineadas verticalmente (tira de film en orientación vertical,
    # ej. los fotogramas sintéticos de assets/sample_frames).
    horizontal = crop.shape[1] >= crop.shape[0]
    axis = 0 if horizontal else 1
    profile = crop.mean(axis=axis).astype(np.float64)

    smoothing_kernel = np.ones(9) / 9
    smooth = np.convolve(profile, smoothing_kernel, mode="same")

    if smooth.max() == smooth.min():
        return []  # zona sin variación de brillo: no hay nada que detectar

    threshold = smooth.min() + (smooth.max() - smooth.min()) * min_relative_height
    peaks = _find_local_maxima(smooth, min_distance=min_spacing_px, min_height=threshold)

    results: List[Perforation] = []
    for peak in peaks:
        refined_peak = _parabolic_refine(smooth, peak)

        if horizontal:
            local_cx = refined_peak
            strip = crop[:, max(0, peak - 10) : peak + 10]
            # El perfil ortogonal (strip.mean(axis=1)) recorre TODA la
            # altura del crop sin recortar, así que su centroide ya está
            # en coordenadas del crop — no hay que sumarle ningún offset
            # de ventana (eso fue un bug: se sumaba un offset del eje X
            # a una coordenada del eje Y).
            local_cy = _weighted_centroid(strip.mean(axis=1)) if strip.size else crop.shape[0] / 2
        else:
            local_cy = refined_peak
            strip = crop[max(0, peak - 10) : peak + 10, :]
            local_cx = _weighted_centroid(strip.mean(axis=0)) if strip.size else crop.shape[1] / 2

        results.append(
            Perforation(
                cx=zone.x0 + local_cx,
                cy=zone.y0 + local_cy,
                area=float(smooth[peak]),  # prominencia del pico, usado como proxy de confianza
                zone=zone_name,
            )
        )
    return results


def detect_perforations(
    frame: np.ndarray,
    left_zone: SearchZone,
    right_zone: SearchZone,
) -> List[Perforation]:
    """Punto de entrada principal: detecta perforaciones en ambas zonas."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    left = _find_perforations_in_zone(gray, left_zone, "left")
    right = _find_perforations_in_zone(gray, right_zone, "right")
    return left + right


def best_perforation_pair(perforations: List[Perforation]) -> Tuple[Perforation, Perforation] | None:
    """Elige una perforación izquierda y una derecha que correspondan a la
    MISMA fila/columna física — pensado para el primer marcado de
    referencia en calibración, cuando todavía no hay nada contra qué comparar.

    Si hay varias perforaciones por fotograma (35mm = 4), no alcanza con
    tomar la de mayor confianza en cada zona por separado: con la
    confianza casi idéntica entre agujeros (ver detect_perforations), eso
    termina emparejando filas distintas (ej. fila 1 a la izquierda con
    fila 3 a la derecha), lo que arruina el ángulo de referencia. En vez
    de eso, se elige la combinación izquierda/derecha más ALINEADA: zonas
    verticales (izq/der separadas en X) se alinean por Y; zonas
    horizontales (arriba/abajo separadas en Y) se alinean por X. No hace
    falta saber la orientación de antemano — el eje de separación entre
    zonas siempre va a tener una diferencia mucho mayor que el eje
    alineado, así que `min(dy, dx)` identifica el eje correcto solo.
    """
    left = [p for p in perforations if p.zone == "left"]
    right = [p for p in perforations if p.zone == "right"]
    if not left or not right:
        return None

    best_pair = None
    best_score = None
    for l in left:
        for r in right:
            score = min(abs(l.cy - r.cy), abs(l.cx - r.cx))
            if best_score is None or score < best_score:
                best_score = score
                best_pair = (l, r)
    return best_pair


def match_pair_to_reference(
    perforations: List[Perforation],
    reference_pair: Tuple[Perforation, Perforation],
) -> Tuple[Perforation, Perforation] | None:
    """Encuentra, en el fotograma actual, la perforación izquierda y
    derecha más cercanas en posición a las de `reference_pair`.

    Es el matching correcto para comparar dos fotogramas: al haber varias
    perforaciones por cuadro (35mm = 4), hace falta trackear la MISMA
    perforación física de un fotograma al siguiente (tolerando el jitter
    mecánico), no simplemente la de mayor confianza en cada toma por separado.
    """
    ref_left, ref_right = reference_pair
    left = [p for p in perforations if p.zone == "left"]
    right = [p for p in perforations if p.zone == "right"]
    if not left or not right:
        return None

    def _closest(candidates: List[Perforation], reference: Perforation) -> Perforation:
        return min(candidates, key=lambda p: (p.cx - reference.cx) ** 2 + (p.cy - reference.cy) ** 2)

    return _closest(left, ref_left), _closest(right, ref_right)
