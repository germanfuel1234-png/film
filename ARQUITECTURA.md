# Arquitectura técnica — FILMS

> **Decisiones confirmadas con el cliente:** lenguaje **Python**, motor controlado por **Arduino**, y las cámaras definitivas **aún no están cerradas** → el sistema se construye con un selector de cámara en runtime (ver §3). El prototipo del video de referencia **no funciona al 100%**: se usa como especificación de UI/UX, no como código base.

## 1. Stack recomendado

| Capa | Elección | Motivo |
|---|---|---|
| Lenguaje principal | **Python 3.11+** | Ecosistema maduro de visión artificial (OpenCV), SDKs de cámara con bindings, desarrollo rápido. Módulos críticos de latencia pueden reescribirse puntualmente en C++ si el profiling lo justifica. |
| Visión por computadora | **OpenCV** (+ NumPy) | Detección de bordes/contornos de perforaciones, template matching, cálculo de transformación afín (X/Y/rotación) subpíxel. |
| Cámara industrial | **SDK Huateng (GenICam/GigE Vision)**, o wrapper genérico **Harvesters/Aravis** si se prioriza portabilidad entre marcas | Acceso a trigger por hardware, Global Shutter, control de exposición/ganancia. |
| Cámara DSLR | **gPhoto2** (`python-gphoto2`) en Linux; **Canon EDSDK** si se requiere Windows nativo con funciones avanzadas | gPhoto2 es la vía más simple para scripting y multiplataforma; EDSDK da acceso más fino en Windows. |
| Motor paso a paso | **Firmware propio en Arduino/microcontrolador**, comunicación por **Serial/USB** (`pyserial`) con protocolo de comandos simple (ver §4) | Desacopla el timing de movimiento (crítico, de baja latencia) del resto de la app. |
| Captura RAW/DNG | Captura nativa de la cámara en RAW; conversión/empaquetado a **DNG** vía `rawpy`/`dnglab` cuando la cámara no entrega DNG directo | Preserva máxima calidad; evita compresión con pérdida (JPEG prohibido por especificación). |
| Interfaz de escritorio | **PySide6 (Qt)** | Mismo lenguaje que el resto del stack (un solo runtime), widgets suficientes para replicar las 7 pestañas del prototipo, multiplataforma (Windows/Linux). |
| Integridad de archivos | `hashlib.sha256` | Ya validado en el prototipo ("copia verificada SHA-256"). |
| Persistencia de proyecto | Archivos de proyecto en disco (JSON/SQLite) con: configuración de cinta, zonas de búsqueda, encuadre de referencia, estado de fotogramas procesados | Permite "abrir/reanudar" proyecto, tal como expone la demo. |

## 2. Diagrama de flujo (ciclo de escaneo)

```
┌─────────────┐   avanza N pasos   ┌──────────────────┐
│   core/      │ ─────────────────▶│  hardware/motor   │
│ scan_        │                    └──────────────────┘
│ controller   │◀── posición / ack ───────────┘
│ (máquina de  │
│  estados)    │   preview frame    ┌──────────────────────────────┐
│              │ ─────────────────▶│ hardware/camera_industrial    │
│              │                    │ hardware/camera_dslr          │
│              │◀── frame RGB/mono ─└──────────────────────────────┘
│              │
│              │   frame preview    ┌───────────────────────────────┐
│              │ ─────────────────▶│ vision/perforation_detection   │
│              │◀── posición perf. ─└───────────────────────────────┘
│              │
│              │   frame + ref.     ┌───────────────────────────────┐
│              │ ─────────────────▶│ vision/stabilization            │
│              │◀── offset XY/θ ────└───────────────────────────────┘
│              │
│              │   trigger captura  ┌──────────────────────────────┐
│              │ ─────────────────▶│ hardware/camera_* (captura)   │
│              │◀── RAW/DNG buffer ─└──────────────────────────────┘
│              │
│              │   frame + metadata ┌──────────────────────────────┐
│              │ ─────────────────▶│ storage (RAW/DNG + SHA-256)   │
└──────────────┘                    └──────────────────────────────┘
        │
        ▼
   ui/desktop_app (estado en tiempo real, contador, resultados antes/después)
```

El ciclo se repite fotograma a fotograma: **avanzar → detectar perforación → frenar → disparar → estabilizar/recortar → guardar → repetir**.

## 3. Principio de diseño: capa de abstracción de cámara + switch en runtime

`hardware/camera_industrial`, `hardware/camera_dslr` y `hardware/camera_simulated` implementan una **interfaz común** (`CameraDriver`, en `camera_base.py`) con métodos `connect()`, `trigger_capture()`, `get_preview_frame()`, `disconnect()`, `get_status()`. `core/scan_controller` nunca depende del SDK concreto: solo conoce `CameraDriver`.

Como **todavía no está definido qué 2 cámaras va a usar el cliente en definitiva**, se agrega una pieza explícita de **switch**: `hardware/camera_factory.py` expone `create_camera(camera_type: str) -> CameraDriver`, con `camera_type ∈ {"industrial", "dslr", "simulated"}`. La UI (pestaña "Entrada") expone este selector como un combo/switch visible, y al cambiarlo el `scan_controller` simplemente recibe una nueva instancia de `CameraDriver` — el resto del pipeline (visión, estabilización, storage) no se entera de qué cámara hay detrás. Esto permite seguir desarrollando y probando todo el sistema con `camera_simulated` (fotogramas de ejemplo) mientras se termina de definir/conseguir el hardware real, igual que hacía el prototipo original en modo "SIMULACIÓN".

## 4. Protocolo de comunicación con el motor (firmware ↔ PC)

Comandos mínimos sobre Serial, en texto plano o binario simple, confirmados por `ACK`/`ERR`:

- `MOVE <pasos> <dirección>` — avanzar N pasos (grueso o fino, según los controles "+100/+10/+1" y "avance fino" vistos en la pestaña Calibración).
- `STOP` — frenado inmediato ("DETENER AHORA").
- `STATUS` — posición actual / pasos acumulados desde el último reinicio.
- `RESET_COUNTER` — reinicia el contador de pasos conservando la posición física del motor (tal como describe la demo: "Reiniciar conserva la posición del motor y el ajuste guardado").

## 5. Formato y trazabilidad de salida

- Cada fotograma se guarda en RAW/DNG **no destructivo**: el original se conserva, y el recorte/alineación se guarda como transformación aplicada (offset X/Y, ángulo, referencia usada) en metadata o archivo `.json` asociado — consistente con "originales conservados" visto en el prototipo.
- Al exportar el proyecto, se genera un manifiesto con hash **SHA-256 por archivo** para verificación de integridad.

## 6. Dependencias entre módulos

```
ui/desktop_app
   └─▶ core/scan_controller
          ├─▶ hardware/motor
          ├─▶ hardware/camera_industrial | hardware/camera_dslr
          ├─▶ vision/perforation_detection
          │       └─▶ vision/stabilization
          └─▶ storage
   └─▶ core/project_manager
   └─▶ core/calibration
          ├─▶ hardware/motor
          └─▶ vision/perforation_detection
```

`core/` nunca importa detalles de un SDK específico directamente: siempre pasa por las interfaces definidas en `hardware/` y `vision/`.

## 7. Pendiente de definición (ver preguntas al cliente)

Confirmado: Python, Arduino, PySide6. Sigue abierto: modelo exacto de Arduino/driver del motor, y qué 2 cámaras concretas se van a usar (cubierto por el switch de cámara, §3) — ver sección 6 de [`../ESPECIFICACIONES_PROYECTO.md`](../ESPECIFICACIONES_PROYECTO.md). Esta arquitectura está diseñada para no verse afectada por esas decisiones gracias a las capas de abstracción en `hardware/`.

## 8. Riesgo conocido: preview vs. captura a distinta resolución

`hardware/camera_industrial.py` y `hardware/camera_dslr.py` entregan un `get_preview_frame()` en **menor resolución** que `trigger_capture()` (preview más liviano = más FPS de refresco). Las zonas de búsqueda y el encuadre de referencia se calibran mirando ese preview (pestañas "Configuración"/"Entrada"), pero el recorte final (`apply_crop`) se aplica sobre la imagen guardada a **resolución completa** — si no se corrige, las coordenadas calibradas quedan desfasadas por el factor de escala entre ambas.

Esto se detectó recorriendo el flujo completo por la UI real con cámara simulada (no solo con tests de backend) — `hardware/camera_simulated.py` se corrigió para que preview y captura sean la misma resolución, que es el comportamiento de referencia correcto. **Antes de calibrar con cualquiera de las dos cámaras reales**, hay que resolver esto: o bien sacar el resize del preview (si el FPS de refresco lo banca), o agregar un factor de escala explícito entre coordenadas de preview y de captura al convertir `SearchZone`/`ReferenceBox`. Quedó documentado con comentarios en los dos drivers afectados.
