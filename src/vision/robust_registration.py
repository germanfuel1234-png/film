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


def measure_absolute_tilt(
    perforations: List[Perforation],
    min_points_per_band: int = 3,
) -> float | None:
    """Ángulo ABSOLUTO del film respecto a la horizontal real, ajustando
    una recta por las perforaciones de cada banda.

    Por qué hace falta: alinear todo contra el fotograma 0 deja la
    secuencia consistente entre cuadros, pero si el fotograma 0 está
    torcido, TODA la película hereda esa inclinación — queda estable pero
    chueca para el ojo. Esto define el cero verdadero: las perforaciones
    están troqueladas en línea recta a lo largo del celuloide, así que la
    recta que pasa por ellas ES la horizontal del film.

    Medido sobre las fotos reales del cliente, el fotograma 0 está
    inclinado -0.241°, y la dispersión perpendicular de las perforaciones
    respecto de la recta ajustada es menor a 1 px — o sea que el ángulo
    sale confiable aunque el espaciado entre perforaciones tenga ruido
    (ese ruido es a lo largo de la recta, no perpendicular a ella).

    Devuelve el ángulo en grados (positivo = film rotado antihorario), o
    None si no hay suficientes perforaciones para ajustar una recta.
    """
    angles: List[float] = []
    for zone_name in {p.zone for p in perforations}:
        points = np.array([[p.cx, p.cy] for p in perforations if p.zone == zone_name], dtype=np.float32)
        if len(points) < min_points_per_band:
            continue
        vx, vy, _, _ = cv2.fitLine(points, cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
        # DIST_HUBER pondera a la baja los puntos lejanos: una perforación
        # mal detectada no arrastra el ángulo de toda la recta.
        angles.append(math.degrees(math.atan2(float(vy), float(vx))))

    if not angles:
        return None
    return float(np.mean(angles))


def build_straightening_matrix(tilt_deg: float, image_shape: tuple[int, int]) -> np.ndarray:
    """Matriz 2x3 que rota la imagen `tilt_deg` grados alrededor de su
    centro para dejarla recta (cero absoluto)."""
    height, width = image_shape[:2]
    center = (width / 2.0, height / 2.0)
    return cv2.getRotationMatrix2D(center, tilt_deg, 1.0)


def compose_affine(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    """Compone dos transformaciones afines 2x3: aplica `first` y después
    `second` (equivale al producto de las matrices 3x3 homogéneas)."""
    first_h = np.vstack([first, [0.0, 0.0, 1.0]])
    second_h = np.vstack([second, [0.0, 0.0, 1.0]])
    return (second_h @ first_h)[:2, :]


def refine_alignment_with_ecc(
    frame_gray: np.ndarray,
    reference_gray: np.ndarray,
    mask_zones: List[SearchZone],
    initial_matrix: np.ndarray | None = None,
    max_iterations: int = 50,
    epsilon: float = 1e-7,
    scale: float = 0.5,
) -> np.ndarray | None:
    """Refina la alineación con ECC (Enhanced Correlation Coefficient),
    restringido a `mask_zones` — estructura FÍSICA del celuloide que es
    idéntica cuadro a cuadro (perforaciones), nunca al área de imagen (que
    se mueve por diseño, es una película).

    Por qué esto además del ajuste por centroides de perforación: el
    detector de perforaciones ubica cada agujero con ruido de varios
    píxeles (verificado sobre las fotos reales del cliente: el espaciado
    medido entre perforaciones salía 118/197/181/125/170/191 px cuando
    físicamente es constante — o sea, los centroides individuales no son
    confiables al nivel de precisión que pide el cliente). ECC no depende
    de ubicar puntos: correlaciona la IMAGEN completa de la zona, usando
    toda la estructura (bordes de cada agujero), y converge con precisión
    sub-píxel.

    Medido sobre las 36 fotos reales: el rango de giro entre fotogramas
    baja de 1.39° (solo centroides) a 0.186° con máscara de perforaciones.

    `mask_zones` admite ampliar la máscara más allá de las perforaciones
    (ej. para incluir la banda sonora óptica, que tiene más detalle de
    alta frecuencia) — se probó explícitamente y **empeoró** el resultado
    (rango de giro subió a 0.48°, y en una corrida un fotograma divergió
    por completo a 12.6°): esa zona tiene menos señal confiable (JPEG más
    comprimido, patrón menos rígido respecto de las perforaciones de lo
    esperado) y termina arrastrando el ajuste. Dejar `mask_zones` en solo
    las perforaciones salvo que se vuelva a medir y confirme una mejora.

    Devuelve la matriz 2x3 que mapea `reference_gray` -> `frame_gray`, o
    None si ECC no converge (el llamador debe quedarse con la estimación
    por perforaciones en ese caso).
    """
    # ECC se corre a media resolución por velocidad: medido sobre las 36
    # fotos reales, baja de ~1750 ms a ~274 ms por fotograma perdiendo
    # apenas precisión. Para un rollo de 3000 fotogramas es la diferencia
    # entre ~1.5 h y ~14 min.
    if scale != 1.0:
        reference_small = cv2.resize(reference_gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        frame_small = cv2.resize(frame_gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    else:
        reference_small, frame_small = reference_gray, frame_gray

    mask = np.zeros(reference_small.shape, dtype=np.uint8)
    for zone in mask_zones:
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
    ecc_zones: List[SearchZone] | None = None,
) -> RobustAlignment | None:
    """Alineación en dos etapas: primero una estimación robusta por
    perforaciones (tolera desplazamientos grandes, da un punto de partida
    confiable) y después refinamiento sub-píxel con ECC. Es la que usa el
    botón "Aplicar mejora".

    `ecc_zones` es la máscara que usa ECC para el refinamiento — por
    defecto son las mismas zonas de detección de perforaciones
    (`left_zone`, `right_zone`). Pasar algo distinto NO afecta la
    detección de perforaciones en sí (que sigue usando `left_zone`/
    `right_zone` tal cual, pensadas para encontrar los agujeros). Ver la
    advertencia en `refine_alignment_with_ecc`: ampliar esta máscara para
    incluir la banda sonora óptica se probó explícitamente y empeoró el
    resultado — dejar en default salvo que se vuelva a medir y confirme
    una mejora real.
    """
    coarse = compute_robust_alignment(perforations, reference_perforations)

    frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    reference_gray = cv2.cvtColor(reference_frame, cv2.COLOR_BGR2GRAY) if reference_frame.ndim == 3 else reference_frame

    # ECC estima reference -> frame; para corregir el fotograma necesitamos
    # la inversa (frame -> reference), igual que devuelve la etapa gruesa.
    initial = cv2.invertAffineTransform(coarse.matrix) if coarse is not None else None
    zones = ecc_zones if ecc_zones is not None else [left_zone, right_zone]
    refined = refine_alignment_with_ecc(frame_gray, reference_gray, zones, initial)

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


def rotate_output(image: np.ndarray, degrees: int) -> np.ndarray:
    """Rota el fotograma final en incrementos de 90° (antihorario).

    La cámara suele capturar el film "de costado": en las fotos reales
    del cliente las perforaciones quedan arriba/abajo con varios cuadros
    uno al lado del otro, en vez de a los lados con un cuadro por imagen
    como se ve normalmente una película. Rotar 90° antihorario pone cada
    cuadro en la orientación de lectura normal (confirmado visualmente
    contra el video de referencia que mandó el cliente).
    """
    degrees = degrees % 360
    if degrees == 90:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if degrees == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    if degrees == 270:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    return image
