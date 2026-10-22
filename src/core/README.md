# core/

Orquestación y lógica de negocio del escáner. Ningún módulo aquí conoce el SDK concreto de hardware ni el detalle de bajo nivel de OpenCV: solo consume las interfaces de `hardware/` y `vision/`.

## Submódulos

- [`scan_controller.py`](scan_controller.py) — máquina de estados del ciclo completo de escaneo (pestaña "Escaneo" del prototipo).
- [`project_manager.py`](project_manager.py) — alta, apertura, reanudación y exportación de proyectos.
- [`calibration.py`](calibration.py) — flujo de calibración, zonas de búsqueda y referencias (pestañas "Calibración" / "Perforaciones" / "Configuración").
