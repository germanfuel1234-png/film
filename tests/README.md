# tests/

- `unit/` — tests por módulo (ej. cálculo de offset en `vision/stabilization`, parsing del protocolo serie en `hardware/motor`), con hardware/cámara mockeados.
- `integration/` — tests del pipeline completo (`core/scan_controller` orquestando `hardware/` + `vision/` + `storage/`) sobre fotogramas de ejemplo fijos, en modo simulación — el mismo enfoque que ya usa el prototipo actual (fotos de ejemplo del rollo "Lowe presenta", sin hardware real conectado).
