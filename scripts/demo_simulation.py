"""Demo por consola: corre el ciclo completo de escaneo en modo 100%
simulado (cámara y motor simulados, sin ningún hardware conectado) y
muestra un resumen legible.

Es la forma más rápida de comprobar que el sistema funciona end-to-end
(avanzar -> detectar perforaciones -> estabilizar -> guardar RAW ->
exportar con verificación SHA-256) sin depender de que haya cámaras
físicas disponibles. No usa config/hardware_config.json a propósito: usa
siempre los fotogramas sintéticos de assets/sample_frames/, así el
resultado es reproducible sin importar lo que el cliente haya editado en
ese archivo.

Uso:
    .venv/bin/python scripts/demo_simulation.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.calibration import Calibrator
from src.core.scan_controller import ScanController
from src.hardware.camera_simulated import SimulatedCamera
from src.hardware.motor.stepper_motor import SimulatedStepperMotor
from src.storage.raw_dng_writer import ProjectStorage
from src.vision.perforation_detection import SearchZone
from src.vision.stabilization import ReferenceBox

ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets" / "sample_frames"
LEFT_ZONE = SearchZone(x0=10, y0=100, x1=110, y1=1200)
RIGHT_ZONE = SearchZone(x0=760, y0=100, x1=860, y1=1200)
REFERENCE_BOX = ReferenceBox(x0=220, y0=120, x1=680, y1=1180)


def main() -> int:
    print("=== FILMS · demo de simulación (sin hardware real) ===\n")

    print("1) Conectando cámara simulada y motor simulado...")
    camera = SimulatedCamera(sample_dir=ASSETS_DIR)
    camera.connect()
    motor = SimulatedStepperMotor()
    motor.connect()
    print(f"   cámara: {camera.state.status.value} ({camera.state.extra})")
    print(f"   motor:  {motor.state.status.value}\n")

    print("2) Calibrando (zonas de búsqueda, encuadre de referencia, Referencia 1)...")
    calibrator = Calibrator()
    calibrator.set_film_format("35mm")
    calibrator.set_search_zones(LEFT_ZONE, RIGHT_ZONE)
    calibrator.set_reference_box(REFERENCE_BOX)
    frame = camera.get_preview_frame()
    pair = calibrator.mark_reference(1, frame)
    print(f"   Referencia 1: izquierda={pair[0].cx:.1f},{pair[0].cy:.1f}  derecha={pair[1].cx:.1f},{pair[1].cy:.1f}\n")

    output_dir = Path(tempfile.mkdtemp(prefix="films_demo_"))
    storage = ProjectStorage(output_dir)
    controller = ScanController(camera=camera, motor=motor, calibrator=calibrator, storage=storage, steps_per_frame=1000)

    print("3) Corriendo una tanda de 5 fotogramas automática...")
    errors = []
    processed = []

    def on_frame(result):
        processed.append(result)
        print(f"   fotograma {result.frame_index}: {result.alignment.as_label()}")

    def on_error(exc):
        errors.append(exc)
        print(f"   ERROR: {exc}")

    controller.run_batch(5, on_frame_processed=on_frame, on_error=on_error)

    print(f"\n4) Exportando proyecto (manifiesto SHA-256)...")
    manifest = storage.export_manifest()
    mismatches = storage.verify_manifest()

    print(f"\n=== Resumen ===")
    print(f"Fotogramas procesados: {len(processed)} / 5")
    print(f"Errores: {len(errors)}")
    print(f"Archivos en el manifiesto: {manifest['frame_count']}")
    print(f"Integridad SHA-256: {'OK, todo coincide' if not mismatches else f'FALLÓ en {mismatches}'}")
    print(f"Carpeta de salida: {output_dir}")

    ok = len(errors) == 0 and len(processed) == 5 and not mismatches
    print(f"\n{'✅ SIMULACIÓN EXITOSA' if ok else '❌ SIMULACIÓN CON PROBLEMAS'}")

    shutil.rmtree(output_dir, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
