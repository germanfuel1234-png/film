"""Cálculo de desplazamiento X/Y, rotación y recorte alineado ("crop & match").

Reproduce la métrica que ya muestra el prototipo en la pestaña
"Resultados" (ej. "XY: -16.00 px · giro: -0.002° · residuo 0.49 px"):
dado un par de perforaciones de referencia (fijadas en calibración) y el
par detectado en el fotograma actual, se calcula la transformación rígida
(traslación + rotación) que lleva una sobre la otra, y se aplica al
encuadre de referencia para producir el recorte final estabilizado.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from .perforation_detection import Perforation


@dataclass
class ReferenceBox:
    """Encuadre de referencia (pestaña "Entrada": X/Y inicial/final)."""

    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0


@dataclass
class AlignmentResult:
    dx: float  # px
    dy: float  # px
    angle_deg: float
    residual_px: float  # confianza del ajuste: cuanto menor, mejor
    ok: bool  # True si residual_px está dentro de tolerancia

    def as_label(self) -> str:
        return f"desplazamiento X/Y {self.dx:+.2f} / {self.dy:+.2f} px · giro {self.angle_deg:+.3f}° · residuo {self.residual_px:.2f} px"


def _pair_to_points(pair: tuple[Perforation, Perforation]) -> np.ndarray:
    left, right = pair
    return np.array([[left.cx, left.cy], [right.cx, right.cy]], dtype=np.float32)


def compute_offset(
    reference_pair: tuple[Perforation, Perforation],
    current_pair: tuple[Perforation, Perforation],
    residual_tolerance_px: float = 1.5,
) -> AlignmentResult:
    """Calcula la transformación rígida (dx, dy, θ) entre dos pares de
    perforaciones (izquierda, derecha) usando la línea que las une como
    referencia de orientación — exactamente el método descripto en
    analisis.txt: "calcula el desplazamiento en X/Y y la rotación de cada
    fotograma usando las perforaciones como referencia estática".
    """
    ref_pts = _pair_to_points(reference_pair)
    cur_pts = _pair_to_points(current_pair)

    ref_center = ref_pts.mean(axis=0)
    cur_center = cur_pts.mean(axis=0)
    dx, dy = (cur_center - ref_center).tolist()

    ref_vec = ref_pts[1] - ref_pts[0]
    cur_vec = cur_pts[1] - cur_pts[0]
    ref_angle = math.degrees(math.atan2(ref_vec[1], ref_vec[0]))
    cur_angle = math.degrees(math.atan2(cur_vec[1], cur_vec[0]))
    angle_deg = cur_angle - ref_angle

    # Residuo: cuánto difiere la distancia entre perforaciones respecto a
    # la referencia, como proxy de la calidad/confianza de la detección.
    ref_dist = float(np.linalg.norm(ref_vec))
    cur_dist = float(np.linalg.norm(cur_vec))
    residual_px = abs(cur_dist - ref_dist)

    return AlignmentResult(
        dx=float(dx),
        dy=float(dy),
        angle_deg=float(angle_deg),
        residual_px=residual_px,
        ok=residual_px <= residual_tolerance_px,
    )


def apply_crop(frame: np.ndarray, reference_box: ReferenceBox, alignment: AlignmentResult) -> np.ndarray:
    """Aplica la corrección (traslación + rotación) y recorta al encuadre
    de referencia — la "corrección automática X/Y y giro" del prototipo,
    con "referencia fija" y "originales conservados" (esta función no
    modifica `frame`, devuelve un recorte nuevo).
    """
    h, w = frame.shape[:2]
    center = (w / 2.0, h / 2.0)

    # Se compensa el giro y el desplazamiento detectado para que el
    # contenido vuelva a caer exactamente sobre el encuadre de referencia.
    rotation_matrix = cv2.getRotationMatrix2D(center, alignment.angle_deg, 1.0)
    rotation_matrix[0, 2] -= alignment.dx
    rotation_matrix[1, 2] -= alignment.dy

    corrected = cv2.warpAffine(frame, rotation_matrix, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    crop = corrected[reference_box.y0 : reference_box.y1, reference_box.x0 : reference_box.x1]
    return crop
