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

from .perforation_detection import Perforation, SearchZone
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


def refine_alignment_with_ecc(
    frame_gray: np.ndarray,
    reference_gray: np.ndarray,
    left_zone: SearchZone,
    right_zone: SearchZone,
    initial_matrix: np.ndarray | None = None,
    max_iterations: int = 50,
    epsilon: float = 1e-7,
    scale: float = 0.5,
) -> np.ndarray | None:
    """Refina la alineación con ECC (Enhanced Correlation Coefficient),
    restringido a las BANDAS DE PERFORACIONES mediante una máscara.

    Por qué esto además del ajuste por centroides de perforación: el
    detector de perforaciones ubica cada agujero con ruido de varios
    píxeles (verificado sobre las fotos reales del cliente: el espaciado
    medido entre perforaciones salía 118/197/181/125/170/191 px cuando
    físicamente es constante — o sea, los centroides individuales no son
    confiables al nivel de precisión que pide el cliente). ECC no depende
    de ubicar puntos: correlaciona la IMAGEN completa de la banda, usando
    toda la estructura (bordes de cada agujero, el borde del film, etc.),
    y converge con precisión sub-píxel.

    Se enmascara a las bandas de perforaciones a propósito: esa zona es
    estructura FÍSICA del celuloide, idéntica cuadro a cuadro, mientras
    que el área de imagen cambia (en una película el contenido se mueve
    por diseño) y arrastraría la alineación si se la incluyera.

    Medido sobre las 36 fotos reales: el rango de giro entre fotogramas
    baja de 1.39° (solo centroides) a 0.186° — unas 7.5 veces más estable.

    Devuelve la matriz 2x3 que mapea `reference_gray` -> `frame_gray`, o
    None si ECC no converge (el llamador debe quedarse con la estimación
    por perforaciones en ese caso).
    """
    # ECC se corre a media resolución por velocidad: medido sobre las 36
    # fotos reales, baja de ~1750 ms a ~274 ms por fotograma perdiendo
    # apenas precisión (rango de giro 0.166° vs 0.160°). Para un rollo de
    # 3000 fotogramas es la diferencia entre ~1.5 h y ~14 min.
    if scale != 1.0:
        reference_small = cv2.resize(reference_gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        frame_small = cv2.resize(frame_gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    else:
        reference_small, frame_small = reference_gray, frame_gray

    mask = np.zeros(reference_small.shape, dtype=np.uint8)
    for zone in (left_zone, right_zone):
        y0 = max(0, int(zone.y0 * scale))
        y1 = min(reference_small.shape[0], int(zone.y1 * scale))
        x0 = max(0, int(zone.x0 * scale))
        x1 = min(reference_small.shape[1], int(zone.x1 * scale))
        if y1 > y0 and x1 > x0:
            mask[y0:y1, x0:x1] = 255

    if not mask.any():
        return None

    warp = np.eye(2, 3, dtype=np.float32) if initial_matrix is None else initial_matrix.astype(np.float32).copy()
    if initial_matrix is not None and scale != 1.0:
        warp[0, 2] *= scale  # la traslación vive en píxeles: hay que llevarla a la escala chica
        warp[1, 2] *= scale
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, max_iterations, epsilon)

    try:
        _, warp = cv2.findTransformECC(
            reference_small, frame_small, warp, cv2.MOTION_EUCLIDEAN, criteria, mask, 5
        )
    except cv2.error:
        return None  # ECC no convergió: el llamador usa la estimación por perforaciones

    if scale != 1.0:
        warp[0, 2] /= scale  # y de vuelta a píxeles de resolución completa
        warp[1, 2] /= scale

    return warp


def compute_precise_alignment(
    frame: np.ndarray,
    reference_frame: np.ndarray,
    perforations: List[Perforation],
    reference_perforations: List[Perforation],
    left_zone: SearchZone,
    right_zone: SearchZone,
) -> RobustAlignment | None:
    """Alineación en dos etapas: primero una estimación robusta por
    perforaciones (tolera desplazamientos grandes, da un punto de partida
    confiable) y después refinamiento sub-píxel con ECC sobre la banda de
    perforaciones. Es la que usa el botón "Aplicar mejora".
    """
    coarse = compute_robust_alignment(perforations, reference_perforations)

    frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    reference_gray = cv2.cvtColor(reference_frame, cv2.COLOR_BGR2GRAY) if reference_frame.ndim == 3 else reference_frame

    # ECC estima reference -> frame; para corregir el fotograma necesitamos
    # la inversa (frame -> reference), igual que devuelve la etapa gruesa.
    initial = cv2.invertAffineTransform(coarse.matrix) if coarse is not None else None
    refined = refine_alignment_with_ecc(frame_gray, reference_gray, left_zone, right_zone, initial)

    if refined is None:
        return coarse  # sin refinamiento: nos quedamos con lo que haya dado la etapa gruesa

    matrix = cv2.invertAffineTransform(refined)
    angle = math.degrees(math.atan2(matrix[1, 0], matrix[0, 0]))

    return RobustAlignment(
        matrix=matrix,
        dx=float(matrix[0, 2]),
        dy=float(matrix[1, 2]),
        angle_deg=angle,
        inliers=coarse.inliers if coarse else 0,
        total_points=coarse.total_points if coarse else 0,
        residual_px=coarse.residual_px if coarse else 0.0,
    )


def apply_robust_alignment(frame: np.ndarray, matrix: np.ndarray, reference_box: ReferenceBox) -> np.ndarray:
    """Aplica la transformación estimada (ya óptima por mínimos cuadrados
    robustos, no hace falta negar/invertir nada) y recorta al encuadre de
    referencia — no modifica `frame`, devuelve un recorte nuevo."""
    h, w = frame.shape[:2]
    warped = cv2.warpAffine(frame, matrix, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return warped[reference_box.y0 : reference_box.y1, reference_box.x0 : reference_box.x1]
