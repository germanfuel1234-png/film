# Análisis del Gugusse Roller (referencia del cliente)

> **Este documento es un análisis escrito con nuestras propias palabras — no contiene código copiado del proyecto original.** El Gugusse Roller (`github.com/meantux/GugusseRoller`, autor Denis-Carl Robidoux) está licenciado bajo **GNU GPLv3**. Copiar su código fuente dentro de este proyecto obligaría a licenciar TODO nuestro software como GPL también (efecto "copyleft": si se entrega/distribuye código que incorpora GPL, hay que entregar el código fuente completo bajo los mismos términos). Por eso este documento se limita a describir la arquitectura y las técnicas que usa, para que nuestra propia implementación (en `proyecto_film/src/`) se pueda inspirar en las ideas sin heredar la licencia. Ver `../../ESPECIFICACIONES_PROYECTO.md` para la decisión pendiente con el cliente sobre esto.
>
> Fuente analizada: `~/Descargas/GugusseRoller-master.zip`, 15 archivos Python + 1 sketch Arduino, ~2600 líneas.

## 1. Qué es

Un escáner de película DIY (hazlo-tú-mismo) para 8mm hasta 35mm, full hardware + software open source, publicado por el autor con planos 3D e instrucciones completas en deniscarl.com. El cliente lo mencionó como referencia de cómo debería verse el resultado final (video "The Gugusse Roller in action").

## 2. Hardware

| Componente | Detalle |
|---|---|
| Compute | **Raspberry Pi 4B (4GB)**, Raspbian Bullseye |
| Cámara | **Raspberry Pi HQ Camera** (sensor CSI nativo, no USB) |
| Microcontrolador auxiliar | Adafruit Metro Mini (un Arduino chico) |
| Motores | **3 motores paso a paso NEMA 17** bipolares, 12V — no 1 solo |
| Mecánica de avance | Una rueda de skate (longboard wheel) como capstan/sprocket de arrastre |
| Iluminación | Tiras LED (RGB, se ve en `Lights.py`: canales red/green/blue por separado) |
| Sensores | Detector de perforación (óptico, analógico) + 2 sensores de posición de brazo tensor |

**Diferencia clave con nuestra arquitectura:** nosotros diseñamos para **1 motor** (el avance de película) controlado por Arduino, con el software haciendo estabilización puramente por visión sobre fotos ya capturadas. Gugusse Roller usa **3 motores**: uno para el arrastre principal (`filmdrive`) y uno para cada rollo (`feeder` = alimentador, `pickup` = receptor), porque en una bobina real el motor de arrastre solo mueve la película, pero alguien tiene que tensar/recoger los rollos en los dos extremos sin que la película quede floja ni se tense de más. Esto es relevante si el cliente tiene bobinas (no solo tiras cortas) — **vale la pena preguntarle si su mecánica contempla alimentador/receptor motorizados o si eso lo hace a mano**.

## 3. Cómo detecta la posición del fotograma (esto es lo más importante)

**No usa visión por computadora para esto.** Usa un **sensor óptico analógico dedicado** (fototransistor + LED, ver `attic/holedetect.ino`) colocado físicamente en el punto exacto donde debería estar la perforación. El Arduino:

1. Lee continuamente el valor analógico del sensor (`analogRead`).
2. Tiene un modo de "aprendizaje" (`learning`): durante una ventana de tiempo sincronizada con el movimiento del motor (ver más abajo), registra el mínimo y máximo de luz detectados, y calcula un umbral a 1/3 del rango — esto es **auto-calibración de exposición/contraste del sensor**, no un valor fijo.
3. Cuando el valor cruza el umbral, levanta una señal digital (un pin HIGH) que la Raspberry Pi lee directamente por GPIO.

El motor de avance (`filmdrive`) en `TrinamicSilentMotor.py` no se mueve "N pasos y listo" como el nuestro: se mueve **a pasos continuos con rampa de aceleración, leyendo el pin del sensor en cada paso, y se detiene en el instante exacto en que el sensor se dispara** (lazo cerrado). Recién ahí dispara la cámara.

**Esto es mecánicamente mucho más preciso que nuestro enfoque** (que es: avanzar una cantidad fija de pasos, y corregir después por software analizando la foto). El Gugusse Roller prácticamente no necesita la corrección por software que nosotros construimos, porque el error mecánico ya es mínimo al detenerse justo en la perforación.

**Para nuestro proyecto esto implica una pregunta clave para el cliente**: ¿el hardware que están armando tiene (o va a tener) un sensor óptico de perforación como este, o solo va a tener la cámara? Si tiene un sensor dedicado, deberíamos agregar soporte en nuestro firmware/protocolo para un comando tipo `MOVE_UNTIL_SENSOR` (mover hasta que un pin se dispare, en vez de `MOVE <pasos fijos>`) — sería una mejora real de precisión mecánica, complementaria (no sustituta) a nuestra estabilización por software, que seguiría sirviendo como red de seguridad para el residuo que quede.

## 4. Cómo controla los motores

Diferencia arquitectónica grande con nuestro diseño:

- **Nosotros**: la Raspberry Pi/PC le manda un comando serie (`MOVE <pasos> <dirección>`) a un Arduino, y el Arduino genera los pulsos STEP/DIR en su firmware (temporización precisa, dedicada).
- **Gugusse Roller**: la Raspberry Pi genera los pulsos STEP **directamente por GPIO desde Python** (`RPi.GPIO`), con la rampa de aceleración y el lazo de sensor calculados también en Python (`TrinamicSilentMotor.py`).

Controlar motores con temporización precisa desde Python en un SO de propósito general (aunque sea una Raspberry Pi) es más sensible a jitter del sistema operativo que delegarlo a un microcontrolador dedicado — **nuestra arquitectura actual (Arduino con el firmware en C++) es más robusta en este aspecto** y no cambiaría esa decisión por default. Lo rescatable de su enfoque no es "mover la temporización a Python", sino:

- **Velocidad adaptativa**: miden cuánto tardó cada movimiento (6 últimas muestras) y ajustan la velocidad objetivo automáticamente para converger a un tiempo de ciclo constante — compensan fricción/desgaste mecánico variable sin intervención manual. Esto lo podríamos implementar en nuestro firmware Arduino igual (el Arduino ya puede medir tiempos y ajustar el delay entre pasos).
- **Detección de fallas en dos sentidos**: si el sensor se dispara demasiado pronto repetidamente ("shortsInARow") → falla (ruido/sensor mal calibrado); si nunca se dispara dentro de un máximo de pasos ("faultTreshold") → falla (película rota/trabada/sin más rollo). Esto es un patrón de manejo de errores que sí vale la pena adoptar tal cual en nuestro `firmware/stepper_controller/stepper_controller.ino` y en `hardware/motor/stepper_motor.py`.
- **Presets de velocidad por formato de película** (8mm, Super8, 16mm, 16mm bobina grande, 35mm, 35mm bobina grande, 35mm con pista de sonido, Pathé): cada uno con su propia velocidad, rampa y cantidad de pasos esperados entre perforaciones. Nuestro `core/calibration.py` ya tiene el concepto de `FILM_FORMATS`, pero solo con `perforations_per_frame` — podríamos ampliarlo con esta misma idea de perfiles de velocidad por formato, configurables desde la pestaña Ajustes.

## 5. Cómo captura y guarda

- Usa **Picamera2** (la librería oficial de Raspberry Pi para la cámara CSI, basada en `libcamera`) — específica de Raspberry Pi, no sirve para la cámara industrial Huateng que ya tenemos (esa sigue necesitando GenICam/`harvesters`, ver `src/hardware/camera_industrial.py`).
- **Tiene soporte nativo para DNG real** vía `Picamera2.helpers.save_dng(...)` — la propia librería arma el DNG con metadata de la captura RAW del sensor. Esto es relevante: **si en algún momento el cliente quiere usar la cámara propia de Raspberry Pi (HQ Camera) en vez de (o además de) la Huateng, el guardado DNG "viene gratis" con esa librería**, a diferencia de nuestra industrial/DSLR donde documentamos que hace falta `rawpy` para decodificar.
- Antes de capturar, **descarta unos pocos frames del buffer** (`skipBuffers`) para dejar que el sensor termine de asentar exposición/auto-ajustes después del movimiento del motor — un detalle de calidad que no estábamos contemplando explícitamente en nuestro ciclo de captura.
- Tiene un modo "bracketing" (3 exposiciones por fotograma: media, baja, alta) para HDR en post — útil si hay rollos con rango de exposición difícil (muy oscuros/quemados).
- Guarda primero en `/dev/shm` (RAM disk de Linux, no toca la tarjeta SD) y recién después mueve el archivo de forma atómica a una carpeta de "completados" para que un hilo aparte lo transfiera (FTP o copia local) sin bloquear el ciclo de captura. Patrón útil para Raspberry Pi real, donde la tarjeta SD es lenta: evita que la escritura a disco frene el siguiente disparo.

## 6. Qué NO tiene (y nosotros sí)

- Nada de visión por computadora para perforaciones ni estabilización — como ya se explicó, lo resuelven 100% con el sensor físico. No hay equivalente a nuestro `vision/perforation_detection.py`, `vision/robust_registration.py`, ni al botón "Aplicar mejora".
- No hay switch de cámara en runtime — está atado a Picamera2/RPi HQ Camera específicamente.
- No hay verificación de integridad tipo SHA-256 al exportar.
- No hay gestión de "proyectos" con reanudar/abrir como la nuestra — el nombre de proyecto es solo un prefijo de carpeta en el FTP/disco.

## 7. Resumen para la pregunta del cliente ("que lo entreguemos para su Raspberry Pi")

"Raspberry Pi" puede significar dos cosas distintas, y conviene confirmar cuál:

1. **Correr nuestro software actual en una Raspberry Pi como compute**, controlando la cámara industrial Huateng (USB3) tal como ya está diseñado. Nuestra arquitectura (Python + OpenCV + PySide6 + el driver GenICam) debería poder correr en una Raspberry Pi 4/5 sin cambios grandes, siempre que el fabricante (Huateng) provea un SDK/`.cti` con soporte ARM/Linux — **esto hay que confirmarlo con el proveedor de la cámara**, no es algo que podamos asegurar sin esa info.
2. **Reemplazar la cámara industrial por una Raspberry Pi HQ Camera** (como hace el Gugusse Roller), usando Picamera2 en vez de GenICam. Esto es un cambio de hardware (no solo de software): necesitaríamos escribir un nuevo driver `hardware/camera_picamera2.py` (nuevo, no existe hoy) que implemente nuestra interfaz `CameraDriver` — el mismo patrón que ya usamos para `camera_industrial.py`/`camera_dslr.py`, así que el resto del pipeline (visión, estabilización, storage, UI) no cambiaría.

Ver preguntas 1 y pendientes en `../../../ESPECIFICACIONES_PROYECTO.md` §6 — esto se suma como una pregunta más a confirmar con el cliente antes de implementar cualquiera de las dos opciones.

## 8. Resultado de probarlo en esta PC (2026-10-23)

Se intentó correr `GugusseRoller-source/GugusseGUI.py` tal cual, sin modificar ningún archivo del código original, para ver qué funciona realmente fuera de una Raspberry Pi:

- **Módulos puros (sin dependencias de hardware)**: `ConfigFiles.py`, `CaptureSettings.py`, `FtpThread.py`, `LocalThread.py`, `CaptureLoop.py` — **importan y corren sin problema** en esta PC con solo PyQt5 instalado. Esta es la lógica reutilizable sin cambios de concepto: manejo de settings en JSON, cola de captura, transferencia FTP/local.
- **`TrinamicSilentMotor.py`, `SensorReport.py`, `Lights.py`**: fallan al importar porque hacen `import RPi.GPIO` a nivel de módulo, y esa librería literalmente revisa `/proc/cpuinfo` al cargarse y tira `RuntimeError: This module can only be run on a Raspberry Pi!` si no detecta el hardware — no hay forma de evitarlo sin mockear el módulo.
- **`GCamera.py`, `CameraSettings.py` (parte cámara)**: dependen de `picamera2`/`libcamera`, que ni siquiera compilan en una PC genérica (faltan headers de `libcap`, y aunque compilaran, no hay sensor CSI ni stack de `libcamera` configurado).
- **`GugusseGUI.py` (el punto de entrada real)** importa los tres módulos de hardware a nivel de archivo, así que **falla inmediatamente, antes de crear ninguna ventana**, exactamente como se predijo en la sección 6.

**Experimento adicional**: se armaron módulos *stub* (falsos, viven solo en `/tmp`, nunca se copiaron al proyecto ni se tocó un solo archivo del Gugusse Roller) que simulan `RPi.GPIO`, `picamera2` y `libcamera` con valores de ejemplo. Con eso puesto por delante en el `PYTHONPATH`, **la ventana principal completa de `GugusseGUI.py` abrió y corrió normalmente** (loop de eventos de Qt activo, sin errores fatales — solo un warning menor de layout de Qt). Esto confirma que el diseño de la UI (sliders de exposición/balance de blancos/ganancia, selector de modo de captura, control de luces, reporte de sensores) es autocontenido y no tiene acoplamientos raros más allá del hardware esperado.

**Conclusión práctica**: no se puede "hacer funcionar de verdad" el Gugusse Roller en esta PC (su propósito entero es manejar hardware de Raspberry Pi que no existe aquí), pero sí se pudo verificar que (a) la lógica no-hardware es simple y portable, y (b) la estructura de la GUI es coherente y se puede usar como referencia visual/UX real (no solo leyendo el código) para decidir qué vale la pena reimplementar en `src/` — por ejemplo el layout de controles de cámara en fila, o el patrón de reporte de sensores en vivo.
