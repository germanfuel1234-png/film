"""Prueba de estrés: corre el pipeline COMPLETO (escaneo en vivo + "Aplicar
mejora" resumible, con una interrupción simulada a mitad de camino) sobre
un rollo sintético de N fotogramas, con cámara y motor simulados — sin
hardware real, pero ejercitando la lógica entera tal como la usaría un
rollo de película real completo.

Qué valida:
  - El ciclo de escaneo (avanzar -> confirmar Arduino -> asentar -> foto ->
    corroborar posición) no se rompe ni se degrada sobre cientos/miles de
    fotogramas seguidos.
  - "Aplicar mejora" fraccionado en tandas + interrumpido a mitad de
    camino (se simula matando el proceso de guardado) se recupera
    correctamente y retoma sin perder ni corromper nada.
  - Tiempo y memoria reales en ESTA máquina (no son los números de una
    Raspberry Pi — ver docs/especificaciones_control_motor_camara.pdf —
    pero sirven para detectar regresiones de rendimiento y fugas de
    memoria en la lógica).

Uso:
    .venv/bin/python scripts/stress_test_full_roll.py --count 500
    .venv/bin/python scripts/stress_test_full_roll.py --count 3000 --keep
"""

from __future__ import annotations

import argparse
import resource
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_synthetic_roll import TOP_BAND, BOTTOM_BAND, WIDTH, HEIGHT, generate_roll  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from src.core.calibration import Calibrator  # noqa: E402
from src.core.post_stabilization import apply_improvement  # noqa: E402
from src.core.scan_controller import ScanController  # noqa: E402
from src.hardware.camera_simulated import SimulatedCamera  # noqa: E402
from src.hardware.motor.stepper_motor import SimulatedStepperMotor  # noqa: E402
from src.storage.raw_dng_writer import ProjectStorage  # noqa: E402
from src.vision.perforation_detection import SearchZone, detect_perforations  # noqa: E402
from src.vision.robust_registration import measure_absolute_tilt, rotate_output  # noqa: E402
from src.vision.stabilization import ReferenceBox  # noqa: E402

TOP_ZONE = SearchZone(x0=380, y0=TOP_BAND[0], x1=1600, y1=TOP_BAND[1])
BOTTOM_ZONE = SearchZone(x0=380, y0=BOTTOM_BAND[0], x1=1600, y1=BOTTOM_BAND[1])
REFERENCE_BOX = ReferenceBox(x0=0, y0=0, x1=WIDTH, y1=HEIGHT)


def peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def run_scan_phase(storage: ProjectStorage, sample_dir: Path, count: int) -> list:
    camera = SimulatedCamera(sample_dir=sample_dir, loop=False)
    camera.connect()
    motor = SimulatedStepperMotor()
    motor.connect()

    calibrator = Calibrator()
    calibrator.set_film_format("35mm")
    calibrator.set_search_zones(TOP_ZONE, BOTTOM_ZONE)
    calibrator.set_reference_box(REFERENCE_BOX)
    frame = camera.get_preview_frame()
    calibrator.mark_reference(1, frame)  # get_preview_frame() no avanza el cursor: sigue en el fotograma 0

    controller = ScanController(
        camera=camera, motor=motor, calibrator=calibrator, storage=storage, steps_per_frame=1000, settle_delay_s=0.0
    )

    out_of_position = 0
    errors = []

    def on_error(exc):
        errors.append(str(exc))

    t0 = time.perf_counter()
    results = []
    controller.run_batch(count, on_frame_processed=results.append, on_error=on_error)
    elapsed = time.perf_counter() - t0

    for r in results:
        if not r.alignment.ok:
            out_of_position += 1

    print(f"Fotogramas escaneados: {len(results)}/{count}  (errores de escaneo: {len(errors)})")
    print(
        f"'Ojo' en vivo: {out_of_position} fotograma(s) marcados fuera de posición durante el escaneo "
        f"({out_of_position / max(len(results), 1) * 100:.0f}%) — esperable: el chequeo en vivo usa un "
        "solo par de perforaciones (tolerancia estricta, 1.5px), bastante más sensible al jitter que el "
        "registro robusto de 'Aplicar mejora'. No es una falla por sí sola; lo que importa es el resultado "
        "FINAL después de 'Aplicar mejora' (ver más abajo)."
    )
    print(f"Tiempo escaneo: {elapsed:.2f}s total, {elapsed / max(len(results), 1) * 1000:.1f} ms/fotograma")
    print(f"RAM pico tras escaneo: {peak_rss_mb():.1f} MB")
    if errors:
        print(f"Primeros errores: {errors[:3]}")
    return results


def run_improvement_phase_with_simulated_interruption(storage: ProjectStorage, rotation_deg: int) -> None:
    section("Fase 2: 'Aplicar mejora' fraccionada + interrupción simulada a mitad de camino")

    total_raw = len(list(storage.raw_dir.iterdir()))
    first_batch = max(1, total_raw // 3)

    t0 = time.perf_counter()
    first_results = apply_improvement(
        storage, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX, rotation_deg=rotation_deg, max_frames=first_batch
    )
    elapsed_first = time.perf_counter() - t0
    new_first = [r for r in first_results if not r.already_done]
    print(f"Tanda 1: {len(new_first)} fotograma(s) nuevos en {elapsed_first:.2f}s")

    # Simula una interrupción "sucia": se corta a mitad de la escritura
    # de UN fotograma (igual que un corte de luz real), dejando un
    # temporal huérfano en mejorado/.
    output_dir = storage.project_dir / "mejorado"
    orphan = output_dir / ".tmp_frame_99999_mejorado.png"
    orphan.write_bytes(b"esto no es un PNG valido, simula un corte a mitad de escritura")
    print(f"Interrupción simulada: se dejó un temporal huérfano ({orphan.name})")

    stop_requested = {"flag": False}
    stopped_after = max(1, total_raw // 6)
    new_count = {"n": 0}

    def should_stop():
        return stop_requested["flag"]

    def on_frame(result):
        if not result.already_done:
            new_count["n"] += 1
            if new_count["n"] >= stopped_after:
                stop_requested["flag"] = True

    second_results = apply_improvement(
        storage,
        TOP_ZONE,
        BOTTOM_ZONE,
        REFERENCE_BOX,
        rotation_deg=rotation_deg,
        should_stop=should_stop,
        on_frame_processed=on_frame,
    )
    new_second = [r for r in second_results if not r.already_done]
    print(f"Tanda 2 (detenida manualmente tras {stopped_after} nuevos): {len(new_second)} fotograma(s) nuevos")

    assert not orphan.exists(), "el temporal huérfano debería haberse limpiado al arrancar la corrida"
    print("Temporal huérfano de la interrupción simulada: limpiado correctamente ✓")

    t0 = time.perf_counter()
    final_results = apply_improvement(storage, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX, rotation_deg=rotation_deg)
    elapsed_final = time.perf_counter() - t0
    new_final = [r for r in final_results if not r.already_done]
    already_done_final = [r for r in final_results if r.already_done]
    print(f"Tanda 3 (retoma el resto): {len(new_final)} nuevo(s) + {len(already_done_final)} ya hechos en {elapsed_final:.2f}s")

    mejorado_files = sorted(output_dir.glob("frame_*_mejorado.png"))
    stray_tmp = list(output_dir.glob(".tmp_frame_*_mejorado.png"))
    print(f"\nTotal en mejorado/: {len(mejorado_files)}/{total_raw} fotogramas, {len(stray_tmp)} temporal(es) huérfano(s)")

    # Medición real sobre TODOS los fotogramas finales (no solo los
    # recalculados en la última tanda): deshace la rotación de salida
    # para volver a medir con las mismas zonas de búsqueda originales.
    inverse_rotation = (360 - rotation_deg) % 360
    tilts = []
    for path in mejorado_files:
        img = cv2.imread(str(path))
        if img is None:
            continue
        if inverse_rotation:
            img = rotate_output(img, inverse_rotation)
        tilt = measure_absolute_tilt(detect_perforations(img, TOP_ZONE, BOTTOM_ZONE))
        if tilt is not None:
            tilts.append(tilt)

    if tilts:
        print(
            f"Inclinación final sobre los {len(tilts)} fotogramas del rollo completo: "
            f"{min(tilts):+.3f}° a {max(tilts):+.3f}° (promedio {np.mean(tilts):+.3f}°)"
        )
    print(f"RAM pico tras 'Aplicar mejora' completa: {peak_rss_mb():.1f} MB")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=500, help="Cantidad de fotogramas del rollo sintético")
    parser.add_argument("--seed", type=int, default=0, help="Semilla del generador (reproducible)")
    parser.add_argument("--rotation", type=int, default=90, choices=[0, 90, 180, 270])
    parser.add_argument("--keep", action="store_true", help="No borrar la carpeta temporal del rollo/proyecto al terminar")
    args = parser.parse_args()

    work_dir = Path(tempfile.mkdtemp(prefix="films_stress_"))
    sample_dir = work_dir / "rollo_sintetico"
    project_dir = work_dir / "proyecto"

    try:
        section(f"Fase 0: generando rollo sintético de {args.count} fotogramas")
        t0 = time.perf_counter()
        generate_roll(sample_dir, args.count, seed=args.seed)
        print(f"Generado en {time.perf_counter() - t0:.1f}s -> {sample_dir}")

        section(f"Fase 1: escaneo en vivo completo ({args.count} fotogramas, cámara + motor simulados)")
        storage = ProjectStorage(project_dir)
        run_scan_phase(storage, sample_dir, args.count)

        run_improvement_phase_with_simulated_interruption(storage, args.rotation)

        section("Resumen")
        print(f"RAM pico de todo el proceso: {peak_rss_mb():.1f} MB (para {args.count} fotogramas)")
        print("Si esto se mantiene prácticamente constante al subir --count, confirma que el")
        print("pipeline procesa un fotograma a la vez y no acumula memoria con rollos largos.")
        return 0
    finally:
        if args.keep:
            print(f"\n(no se borró: {work_dir})")
        else:
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
