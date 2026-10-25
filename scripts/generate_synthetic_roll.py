"""Genera un "rollo" sintético de N fotogramas para poder probar el
pipeline completo (detección de perforaciones, estabilización robusta,
"Aplicar mejora" resumible, vista de tira de película) a la escala de una
película entera, sin necesitar miles de fotos reales del cliente.

Reproduce la misma geometría que las fotos reales de `assets/real_frames/`
(1920x1080, perforaciones en bandas horizontales arriba/abajo — ver
`core/calibration.py` y `config/hardware_config.json`), con:

  - Perforaciones parejas, espaciadas de forma regular (como un rollo real).
  - Un patrón de "contenido" en el medio (gradiente + formas) para que la
    estabilización tenga algo con qué medir nitidez/alineación.
  - Un leve bamboleo mecánico ALEATORIO por fotograma (rotación +
    traslación pequeñas, con semilla fija para que sea reproducible) —
    simula el error de avance que el sistema tiene que corregir.

Uso:
    .venv/bin/python scripts/generate_synthetic_roll.py --count 500 --out /tmp/rollo_sintetico
    .venv/bin/python scripts/generate_synthetic_roll.py --count 3000 --out /tmp/rollo_grande --seed 7
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

WIDTH, HEIGHT = 1920, 1080
# Misma franja que TOP_ZONE/BOTTOM_ZONE de assets/real_frames (ver
# core/calibration.py FILM_FORMATS y config/hardware_config.json).
TOP_BAND = (0, 150)
BOTTOM_BAND = (1015, 1080)
PERF_SPACING_PX = 170  # > min_spacing_px=100 de perforation_detection.py
PERF_WIDTH, PERF_HEIGHT = 70, 90


def _draw_perforations(img: np.ndarray, y0: int, y1: int, rng: np.random.Generator) -> None:
    band_h = y1 - y0
    cy = y0 + band_h / 2
    x = 480
    while x < WIDTH - 400:
        top_left = (int(x - PERF_WIDTH / 2), int(cy - PERF_HEIGHT / 2))
        bottom_right = (int(x + PERF_WIDTH / 2), int(cy + PERF_HEIGHT / 2))
        cv2.rectangle(img, top_left, bottom_right, (235, 235, 235), thickness=-1)
        x += PERF_SPACING_PX


def _draw_content(img: np.ndarray, frame_number: int, rng: np.random.Generator) -> None:
    """Patrón de "contenido" simple pero no trivial: un degradé de fondo
    + un par de formas que se desplazan lentamente cuadro a cuadro, para
    que de verdad haya algo que comparar al medir nitidez/alineación
    (equivalente sintético al personaje/nubes de las fotos reales)."""
    content_y0, content_y1 = TOP_BAND[1], BOTTOM_BAND[0]
    gradient = np.linspace(40, 90, content_y1 - content_y0, dtype=np.uint8)
    img[content_y0:content_y1, :, :] = gradient[:, None, None]

    t = frame_number * 0.03
    cx = 700 + int(300 * np.sin(t))
    cy = content_y0 + (content_y1 - content_y0) // 2
    cv2.circle(img, (cx, cy), 120, (200, 160, 60), thickness=-1)
    cv2.rectangle(
        img,
        (1300, content_y0 + 80),
        (1500, content_y1 - 80),
        (60, 120, 180),
        thickness=-1,
    )


def generate_frame(frame_number: int, rng: np.random.Generator, jitter_px: float, jitter_deg: float) -> np.ndarray:
    img = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    _draw_content(img, frame_number, rng)
    _draw_perforations(img, *TOP_BAND, rng)
    _draw_perforations(img, *BOTTOM_BAND, rng)

    if jitter_px > 0 or jitter_deg > 0:
        dx = float(rng.normal(0, jitter_px))
        dy = float(rng.normal(0, jitter_px))
        angle = float(rng.normal(0, jitter_deg))
        center = (WIDTH / 2.0, HEIGHT / 2.0)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        matrix[0, 2] += dx
        matrix[1, 2] += dy
        img = cv2.warpAffine(img, matrix, (WIDTH, HEIGHT), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    return img


def generate_roll(
    output_dir: Path,
    count: int,
    seed: int = 0,
    jitter_px: float = 2.5,
    jitter_deg: float = 0.3,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    paths = []
    for i in range(count):
        frame = generate_frame(i, rng, jitter_px, jitter_deg)
        path = output_dir / f"roll_{i:05d}.png"
        cv2.imwrite(str(path), frame)
        paths.append(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=500, help="Cantidad de fotogramas a generar (default: 500)")
    parser.add_argument("--out", type=Path, required=True, help="Carpeta de salida")
    parser.add_argument("--seed", type=int, default=0, help="Semilla aleatoria (reproducible)")
    parser.add_argument("--jitter-px", type=float, default=2.5, help="Desvío estándar del bamboleo en píxeles")
    parser.add_argument("--jitter-deg", type=float, default=0.3, help="Desvío estándar del bamboleo en grados")
    args = parser.parse_args()

    print(f"Generando {args.count} fotogramas sintéticos en {args.out} (semilla={args.seed})...")
    paths = generate_roll(args.out, args.count, seed=args.seed, jitter_px=args.jitter_px, jitter_deg=args.jitter_deg)
    print(f"Listo: {len(paths)} fotogramas, {sum(p.stat().st_size for p in paths) / 1024**2:.1f} MB en disco.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
