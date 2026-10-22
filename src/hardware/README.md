# hardware/

Capa de abstracción de dispositivos físicos. Todo módulo fuera de `hardware/` debe hablar con el hardware **únicamente** a través de las interfaces que expone esta capa — nunca importando un SDK de fabricante directamente.

## Submódulos

- [`motor/`](motor/README.md) — control del motor paso a paso (Arduino).
- [`camera_industrial.py`](camera_industrial.py) — cámara industrial (GenICam/GigE Vision, ej. Huateng), vía `harvesters`.
- [`camera_dslr.py`](camera_dslr.py) — cámara réflex Canon, vía gPhoto2.
- [`camera_simulated.py`](camera_simulated.py) — reproduce `assets/sample_frames/` para desarrollar y probar sin hardware.
- [`camera_factory.py`](camera_factory.py) — **el switch**: `create_camera("industrial" | "dslr" | "simulated")` instancia el driver correcto. Como todavía no está confirmado qué 2 cámaras va a usar el cliente, todo el sistema pasa por acá en vez de importar un driver fijo.

## Contrato común de cámara (`CameraDriver`)

Ambos drivers de cámara deben exponer la misma interfaz lógica:

- `connect()` / `disconnect()`
- `get_preview_frame()` → frame de baja resolución para detección de perforaciones y preview en UI
- `trigger_capture()` → dispara una captura en resolución completa, RAW/DNG
- `get_status()` → conectado/desconectado, último error

Esto permite que `core/scan_controller` sea agnóstico de qué cámara está en uso, tal como lo anticipa la pestaña "Entrada" del prototipo (fuente intercambiable).
