# config/

## `hardware_config.json` — para que lo edite el cliente

Este es el único archivo que hay que tocar para conectar el programa al **hardware real** (cámaras, Arduino, zonas de perforación del rollo que estén escaneando). El desarrollador construyó todo el sistema en modo simulado porque no tiene acceso físico a las cámaras ni al motor — este archivo es el puente: ustedes lo completan con los datos de su hardware, sin tocar código.

Se lee al arrancar el programa (`main.py`). Si algún valor falta o el archivo tiene un error de formato, el programa **no se rompe**: usa valores por defecto (modo simulado) y avisa por consola.

**No hace falta editar este archivo a mano**: dentro del programa hay una pestaña **"Ajustes"** que edita y guarda estos mismos campos con una interfaz gráfica (selector de archivo para el `.cti`, detección automática de puertos USB para el Arduino, etc.) — ver `../GUIA_USO.md` §4.0. Esta tabla sigue siendo útil como referencia de qué significa cada campo y quién lo tiene que completar.

```json
{
  "camera": {
    "type": "simulated",
    "industrial_cti_path": "",
    "industrial_device_index": 0
  },
  "motor": {
    "mode": "simulated",
    "port": "",
    "baudrate": 115200,
    "steps_per_frame": 1000
  },
  "calibration": {
    "film_format": "35mm",
    "search_zone_left": { "x0": 10, "y0": 100, "x1": 110, "y1": 1200 },
    "search_zone_right": { "x0": 760, "y0": 100, "x1": 860, "y1": 1200 },
    "reference_box": { "x0": 220, "y0": 120, "x1": 680, "y1": 1180 }
  },
  "projects_root": "~/FILMS/projects"
}
```

### Qué significa cada campo

| Campo | Qué poner | Quién lo sabe |
|---|---|---|
| `camera.type` | `"simulated"` (por defecto, sin hardware), `"industrial"` (cámara GenICam/GigE, ej. Huateng) o `"dslr"` (Canon vía gPhoto2). También se puede cambiar desde la app con el switch de la pestaña "Entrada" — esto es solo el valor inicial al arrancar. | El cliente, una vez que decida/confirme qué cámara usar. |
| `camera.industrial_cti_path` | Ruta al archivo `.cti` (GenTL producer) que entrega el **fabricante de la cámara industrial** junto con su SDK. Sin este archivo la cámara industrial no conecta. | El proveedor/fabricante de la cámara industrial (Huateng u otra). |
| `camera.industrial_device_index` | `0` si solo hay una cámara industrial conectada a la PC; si hay varias, el índice de cuál usar. | Normalmente `0` alcanza. |
| `motor.mode` | `"simulated"` (sin Arduino conectado) o `"serial"` (Arduino real conectado por USB). | Ustedes, cuando tengan el Arduino armado. |
| `motor.port` | El puerto donde el sistema operativo ve el Arduino: en Windows algo como `"COM3"`, en Linux `"/dev/ttyACM0"` o `"/dev/ttyUSB0"`. Se ve en el Administrador de dispositivos (Windows) o con `ls /dev/tty*` (Linux). | Ustedes, al conectar el Arduino. |
| `motor.baudrate` | `115200` — tiene que coincidir con el valor configurado en el firmware (`firmware/stepper_controller/stepper_controller.ino`). No cambiar salvo que también se cambie el firmware. | — |
| `motor.steps_per_frame` | Cuántos pasos del motor avanza por cada fotograma. Depende del motor, el driver y la mecánica del arrastre de película. Hay que calibrarlo probando con el rollo real (pestaña "Calibración" → avance fino). | Se determina probando con el hardware real. |
| `calibration.film_format` | `"35mm"` o `"16mm"`. | El tipo de rollo que van a escanear. |
| `calibration.search_zone_left` / `search_zone_right` | Rectángulo (`x0,y0,x1,y1` en píxeles de la imagen de la cámara) donde el sistema busca las perforaciones, a la izquierda y a la derecha del fotograma. Los valores de ejemplo corresponden a los fotogramas sintéticos de prueba (`assets/sample_frames/`), **no a una cámara real** — hay que recalibrarlos con una imagen real de la cámara definitiva (pestaña "Configuración", viendo el preview en vivo). | Se determina mirando el preview real de la cámara, una vez conectada. |
| `calibration.reference_box` | El recorte final (encuadre) que se guarda por cada fotograma, en píxeles de la imagen de la cámara. También depende de la cámara/lente real. | Igual que las zonas de búsqueda. |
| `projects_root` | Carpeta donde se guardan los proyectos escaneados. `~` se expande a la carpeta del usuario. | Dónde quieran que se guarden los archivos (ojo con el espacio en disco: son RAW/DNG, pesan). |

### Por qué existe este archivo

El desarrollo se hizo sin acceso a las cámaras físicas del cliente (ver `../ESPECIFICACIONES_PROYECTO.md` §6, pregunta 1): todavía no está confirmado qué 2 cámaras se van a usar en definitiva. En vez de hardcodear valores en el código, todo lo que depende del hardware real vive en este único archivo, para que el cliente (o quien tenga el hardware en mano) pueda ajustarlo sin pedirle al desarrollador que toque código cada vez.

Ver también `src/core/app_config.py` (el código que lee este archivo) y `../GUIA_USO.md` (guía de uso paso a paso).
