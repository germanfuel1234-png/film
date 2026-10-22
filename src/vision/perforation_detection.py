"""Detección de perforaciones del film dentro de zonas de búsqueda configurables.

Las perforaciones del celuloide son consistentemente más claras (o más
oscuras, según iluminación) que el resto de la imagen y tienen un tamaño y
forma acotados. El algoritmo:

1. Recorta las zonas de búsqueda izquierda/derecha (definidas en la pestaña
   "Configuración" del prototipo).
2. Binariza por umbral (Otsu, se adapta a la exposición de cada toma).
3. Busca contornos cuyo tamaño/forma sea compatible con una perforación.
4. Devuelve el centro de cada perforación encontrada, en coordenadas de la
   imagen completa (no de la zona recortada).
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
    area: float
    zone: str  # "left" | "right"


def _binarize(gray: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Las perforaciones suelen ser la región más clara del borde del film;
    # si Otsu invirtió la polaridad (más píxeles blancos que negros),
    # se corrige para quedarnos con la clase minoritaria "clara".
    if np.count_nonzero(binary) > binary.size / 2:
        binary = cv2.bitwise_not(binary)
    return binary


def _find_perforations_in_zone(
    frame_gray: np.ndarray,
    zone: SearchZone,
    zone_name: str,
    min_area: int = 200,
    max_area: int = 20000,
) -> List[Perforation]:
    crop = zone.crop(frame_gray)
    if crop.size == 0:
        return []

    binary = _binarize(crop)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    results: List[Perforation] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if not (min_area <= area <= max_area):
            continue
        # las perforaciones son aproximadamente rectangulares/cuadradas:
        # se descartan formas muy alargadas (ruido, rayas del film).
        x, y, w, h = cv2.boundingRect(contour)
        aspect = w / h if h else 0
        if not (0.4 <= aspect <= 2.5):
            continue
        M = cv2.moments(contour)
        if M["m00"] == 0:
            continue
        local_cx = M["m10"] / M["m00"]
        local_cy = M["m01"] / M["m00"]
        results.append(
            Perforation(
                cx=zone.x0 + local_cx,
                cy=zone.y0 + local_cy,
                area=area,
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
    """Elige una perforación izquierda y una derecha representativas
    (la de mayor área, como proxy de mejor nitidez/contraste) para usar
    como punto de partida — pensado para el primer marcado de referencia
    en calibración, cuando todavía no hay nada contra qué comparar.

    No usar esto para comparar dos fotogramas distintos: si hay varias
    perforaciones por fotograma (35mm = 4), la de mayor área puede
    corresponder a una fila distinta en cada toma. Para eso usar
    `match_pair_to_reference`.
    """
    left = [p for p in perforations if p.zone == "left"]
    right = [p for p in perforations if p.zone == "right"]
    if not left or not right:
        return None
    best_left = max(left, key=lambda p: p.area)
    best_right = max(right, key=lambda p: p.area)
    return best_left, best_right


def match_pair_to_reference(
    perforations: List[Perforation],
    reference_pair: Tuple[Perforation, Perforation],
) -> Tuple[Perforation, Perforation] | None:
    """Encuentra, en el fotograma actual, la perforación izquierda y
    derecha más cercanas en posición a las de `reference_pair`.

    Es el matching correcto para comparar dos fotogramas: al haber varias
    perforaciones por cuadro (35mm = 4), hace falta trackear la MISMA
    perforación física de un fotograma al siguiente (tolerando el jitter
    mecánico), no simplemente la de mayor área en cada toma por separado.
    """
    ref_left, ref_right = reference_pair
    left = [p for p in perforations if p.zone == "left"]
    right = [p for p in perforations if p.zone == "right"]
    if not left or not right:
        return None

    def _closest(candidates: List[Perforation], reference: Perforation) -> Perforation:
        return min(candidates, key=lambda p: (p.cx - reference.cx) ** 2 + (p.cy - reference.cy) ** 2)

    return _closest(left, ref_left), _closest(right, ref_right)
