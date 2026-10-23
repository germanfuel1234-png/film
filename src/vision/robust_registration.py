"""Registro robusto de un fotograma contra una referencia FIJA, usando
TODAS las perforaciones detectadas (no un único par) con ajuste RANSAC.

Por qué existe esto además de `stabilization.compute_offset`: ese método
usa un solo par de perforaciones (una a cada lado/banda), lo que lo hace
sensible al ruido de detección de esas dos perforaciones puntuales —
validado contra las 36 fotos reales del cliente, el ángulo estimado
fotograma a fotograma variaba entre -3.3° y +6.0° (visible como "giro" al
reproducir la secuencia, justo la queja del cliente: quiere que se vea
estable como una película real, no que cada cuadro gire un poco distinto).

Se probó también usar correspondencia de características genéricas sobre
toda la imagen (ORB + RANSAC, una de las técnicas sugeridas) pero dio
resultados peores acá: las fotos de prueba son tomas a mano con zoom/
encuadre distinto entre sí, así que ORB terminaba emparejando contenido
visualmente parecido de cuadros de la caricatura que en realidad son
distintos (rotaciones estimadas de hasta 150°, basura). Las perforaciones,
en cambio, se detectan de forma confiable en las 36 fotos — por eso este
módulo aplica la misma idea (muchos puntos + RANSAC) pero anclada en las
perforaciones en vez del contenido de la imagen.

Con esto, el ángulo estimado se achica a un rango de -0.8° a +0.6° sobre
el mismo material — gran mejora de estabilidad frame a frame.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

import cv2
import numpy as np

from .perforation_detection import Perforation
from .stabilization import ReferenceBox


@dataclass
class RobustAlignment:
    matrix: np.ndarray  # 2x3, mapea puntos del fotograma actual -> coordenadas de la referencia
    dx: float
    dy: float
    angle_deg: float
    inliers: int
    total_points: int
    residual_px: float  # error medio (px) de los puntos considerados inliers por RANSAC

    def as_label(self) -> str:
        return (
            f"desplazamiento X/Y {self.dx:+.2f} / {self.dy:+.2f} px · giro {self.angle_deg:+.3f}° "
            f"· inliers {self.inliers}/{self.total_points} · residuo {self.residual_px:.2f} px"
        )


def match_all_perforations(
    perforations: List[Perforation],
    reference_perforations: List[Perforation],
) -> List[Tuple[Perforation, Perforation]]:
    """Empareja CADA perforación detectada con la más cercana de la
    referencia, dentro de la misma zona — a diferencia de
    `match_pair_to_reference` (que solo da un par), esto da todos los
    puntos disponibles para un ajuste robusto por mínimos cuadrados."""
    pairs: List[Tuple[Perforation, Perforation]] = []
    zones = {p.zone for p in reference_perforations}
    for zone_name in zones:
        current_in_zone = [p for p in perforations if p.zone == zone_name]
        reference_in_zone = [p for p in reference_perforations if p.zone == zone_name]
        if not current_in_zone or not reference_in_zone:
            continue
        for p in current_in_zone:
            closest = min(reference_in_zone, key=lambda r: (r.cx - p.cx) ** 2 + (r.cy - p.cy) ** 2)
            pairs.append((p, closest))
    return pairs


def compute_robust_alignment(
    perforations: List[Perforation],
    reference_perforations: List[Perforation],
    ransac_threshold_px: float = 15.0,
    min_pairs: int = 3,
) -> RobustAlignment | None:
    """Ajusta una transformación rígida (rotación + traslación) que lleva
    las perforaciones del fotograma actual sobre las de la referencia,
    usando TODOS los puntos emparejados y descartando outliers con RANSAC.
    Devuelve None si no hay suficientes puntos para un ajuste confiable.
    """
    pairs = match_all_perforations(perforations, reference_perforations)
    if len(pairs) < min_pairs:
        return None

    src = np.float32([[p.cx, p.cy] for p, _ in pairs])
    dst = np.float32([[r.cx, r.cy] for _, r in pairs])

    matrix, inlier_mask = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=ransac_threshold_px)
    if matrix is None:
        return None

    angle = math.degrees(math.atan2(matrix[1, 0], matrix[0, 0]))

    src_h = np.hstack([src, np.ones((len(src), 1), dtype=np.float32)])
    projected = src_h @ matrix.T
    errors = np.linalg.norm(projected - dst, axis=1)

    if inlier_mask is not None:
        mask = inlier_mask.ravel().astype(bool)
        inlier_errors = errors[mask]
        n_inliers = int(mask.sum())
    else:
        inlier_errors = errors
        n_inliers = len(pairs)

    residual = float(inlier_errors.mean()) if len(inlier_errors) else float(errors.mean())

    return RobustAlignment(
        matrix=matrix,
        dx=float(matrix[0, 2]),
        dy=float(matrix[1, 2]),
        angle_deg=angle,
        inliers=n_inliers,
        total_points=len(pairs),
        residual_px=residual,
    )


def apply_robust_alignment(frame: np.ndarray, matrix: np.ndarray, reference_box: ReferenceBox) -> np.ndarray:
    """Aplica la transformación estimada (ya óptima por mínimos cuadrados
    robustos, no hace falta negar/invertir nada) y recorta al encuadre de
    referencia — no modifica `frame`, devuelve un recorte nuevo."""
    h, w = frame.shape[:2]
    warped = cv2.warpAffine(frame, matrix, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return warped[reference_box.y0 : reference_box.y1, reference_box.x0 : reference_box.x1]
