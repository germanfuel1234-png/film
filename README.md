# proyecto_film

Implementación en Python del software de escaneo cinematográfico "FILMS": arquitectura modular (hardware/visión/core/storage/UI) con **el pipeline de visión y orquestación ya funcionando** sobre cámara y motor simulados, un **switch de cámara en runtime** (industrial / DSLR / simulada — todavía no está confirmado qué 2 cámaras va a usar el cliente), y una UI PySide6 con las 7 pestañas del prototipo original. El detalle de requisitos del cliente está en [`../ESPECIFICACIONES_PROYECTO.md`](../ESPECIFICACIONES_PROYECTO.md); el detalle técnico de stack y decisiones de arquitectura está en [`ARQUITECTURA.md`](ARQUITECTURA.md).

## Cómo correr

```bash
cd proyecto_film
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py                    # abre la app en modo simulado (cámara + motor simulados)
.venv/bin/python scripts/demo_simulation.py # demo por consola: corre el ciclo completo sin UI
.venv/bin/python -m pytest tests/           # 12 tests unitarios + integración
```

Guía paso a paso de la UI: [`GUIA_USO.md`](GUIA_USO.md). Parámetros editables para conectar hardware real: [`config/hardware_config.json`](config/README.md).

Por defecto arranca con la cámara **simulada** (reproduce `assets/sample_frames/`, generados sintéticamente con perforaciones en posiciones conocidas) y el motor **simulado**, para poder probar todo el flujo sin hardware. Desde la pestaña "Entrada" se puede cambiar a cámara industrial o DSLR una vez que el SDK correspondiente y el hardware estén disponibles (ver `src/hardware/camera_factory.py`).

Las librerías de hardware real (`harvesters` para GenICam/GigE Vision, `gphoto2` para Canon, `rawpy` para decodificar RAW/DNG) son opcionales y están comentadas en `requirements.txt`: instalarlas cuando el cliente confirme las cámaras definitivas.

## Mapa de módulos

```
proyecto_film/
├── ARQUITECTURA.md          Stack, diagrama de flujo, protocolos, decisiones técnicas
├── main.py                  Punto de entrada de la app de escritorio
├── requirements.txt
├── assets/sample_frames/    Fotogramas sintéticos (perforaciones en posiciones conocidas) para modo simulado y tests
├── src/
│   ├── hardware/             Capa de abstracción de dispositivos físicos
│   │   ├── camera_base.py        Interfaz común CameraDriver
│   │   ├── camera_factory.py     El switch: crea el driver según camera_type
│   │   ├── camera_industrial.py  Cámara industrial (GenICam/GigE Vision — harvesters)
│   │   ├── camera_dslr.py        Cámara réflex Canon (gPhoto2)
│   │   ├── camera_simulated.py   Reproduce assets/sample_frames/
│   │   └── motor/                Control del motor paso a paso (Arduino, pyserial)
│   ├── vision/                Visión por computadora (OpenCV, funcional)
│   │   ├── perforation_detection.py  Detección de perforaciones por zonas de búsqueda
│   │   └── stabilization.py          Offset X/Y/rotación + crop & match
│   ├── core/                  Orquestación y lógica de negocio
│   │   ├── scan_controller.py    Máquina de estados del ciclo de escaneo
│   │   ├── project_manager.py    Alta/apertura/export de proyectos
│   │   ├── calibration.py        Flujo de calibración y zonas de búsqueda
│   │   └── app_config.py         Carga/guarda config/hardware_config.json
│   ├── storage/
│   │   └── raw_dng_writer.py  Escritura RAW/DNG no destructiva, manifiesto SHA-256
│   └── ui/desktop_app/        Interfaz PySide6 (7 pestañas del prototipo + "Ajustes")
│       ├── main_window.py, app_context.py, scan_worker.py, image_utils.py
│       ├── widgets/camera_switch.py   El switch de cámara, visible en la UI
│       └── tabs/                      scan_tab, input_tab, results_tab, calibration_tab,
│                                       perforations_tab, config_tab, help_tab, settings_tab
├── firmware/stepper_controller/stepper_controller.ino   Firmware Arduino (protocolo serie)
├── config/                    Plantillas de configuración
├── tests/
│   ├── unit/                  Tests sobre los assets sintéticos (detección, estabilización)
│   └── integration/           Ciclo de escaneo completo con cámara/motor simulados
└── docs/
```

Cada subcarpeta de `src/` tiene su propio `README.md` con responsabilidad, contrato de entrada/salida y dependencias con otros módulos.
