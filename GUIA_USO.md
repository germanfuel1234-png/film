# Guía de uso — FILMS

Guía paso a paso del programa tal como está implementado hoy (no del prototipo del video). Cubre instalación, cómo correrlo en modo simulado, y el flujo completo pestaña por pestaña.

## 1. Instalación

Requiere Python 3.10+ instalado.

```bash
cd proyecto_film
python3 -m venv .venv
```

Windows: `.venv\Scripts\pip install -r requirements.txt`
Linux/Mac: `.venv/bin/pip install -r requirements.txt`

Esto instala lo necesario para correr todo **en modo simulado** (sin hardware). Las librerías de hardware real (`harvesters`, `gphoto2`, `rawpy`) están comentadas en `requirements.txt`: se instalan aparte cuando haya cámaras conectadas.

## 2. Arrancar el programa

```bash
.venv/bin/python main.py
```

Arranca leyendo [`config/hardware_config.json`](config/README.md) (si no existe o está mal editado, usa valores por defecto en modo simulado y lo avisa por consola, no se rompe).

## 3. Probar que todo funciona, sin abrir la interfaz

Si solo querés confirmar que el motor de visión/estabilización/guardado funciona, sin lidiar con la UI:

```bash
.venv/bin/python scripts/demo_simulation.py   # corre 5 fotogramas simulados y muestra un resumen
.venv/bin/python -m pytest tests/              # 12 tests automáticos (detección, estabilización, ciclo completo)
```

Ver también la última pregunta de este documento, más abajo, sobre qué prueba esto exactamente.

## 4. Flujo completo en la interfaz

El orden recomendado la primera vez (después, con un proyecto ya calibrado, se puede ir directo a "Escaneo"):

### 4.0 Pestaña "Ajustes" (para conectar hardware real)
Esta pestaña **no existía en el prototipo original**: se agregó para poder editar `config/hardware_config.json` sin tocar el archivo a mano. Es el primer lugar al que ir cuando llega hardware nuevo:

1. **Cámara**: elegí el tipo por defecto, y si es industrial, cargá el archivo `.cti` (botón **Examinar...**) y el índice de dispositivo.
2. **Motor (Arduino)**: elegí modo `serial`, tocá **Detectar puertos** para que liste los puertos USB disponibles, elegí el correcto, y ajustá baudrate y pasos por fotograma.
3. **Calibración por defecto**: formato de película, zonas de búsqueda y encuadre de referencia — estos son los valores con los que arrancan las demás pestañas (se pueden seguir ajustando ahí para una sesión puntual).
4. **Almacenamiento**: carpeta donde se guardan los proyectos (botón **Examinar carpeta...**).
5. **Guardar y aplicar**: escribe `hardware_config.json` y aplica los cambios al toque — cambia de cámara, reconstruye el motor, actualiza las otras pestañas — sin reiniciar el programa. **Recargar desde archivo** descarta lo que no guardaste y vuelve a leer el archivo del disco.

Las pestañas "Entrada", "Configuración" y "Calibración" siguen permitiendo ajustar valores para la sesión actual sin pasar por acá (por ejemplo, para probar una zona de búsqueda distinta sin perder la que está guardada como default) — lo que se guarda en "Ajustes" es lo que va a usar el programa la próxima vez que arranque.

### 4.1 Pestaña "Entrada"
1. Elegí la cámara con el **switch** (arriba de todo): *Simulada*, *Industrial* o *DSLR*. Mientras no haya hardware conectado, dejá *Simulada*.
2. Tocá **Conectar**. El indicador de estado se pone verde si conectó.
3. Tocá **Activar preview** para ver la imagen en vivo (o los fotogramas de ejemplo, en modo simulado).
4. Ajustá el **encuadre de referencia** (X/Y inicial y final): es el recorte final que se va a guardar de cada fotograma. Los valores iniciales salen de `hardware_config.json`.
5. Guardá con **Guardar encuadre de referencia**.

### 4.2 Pestaña "Configuración"
1. Definí las **zonas de búsqueda** izquierda y derecha: el rectángulo donde el sistema va a buscar las perforaciones del film. También salen de `hardware_config.json` como punto de partida.
2. Guardá con **Guardar zonas de búsqueda**.
3. Tip: andá a la pestaña "Perforaciones" para confirmar visualmente que las zonas están bien puestas antes de seguir.

### 4.3 Pestaña "Perforaciones" (opcional pero recomendado)
1. Tocá **Probar detección**: dibuja las zonas de búsqueda y marca en verde cada perforación que encontró sobre el preview actual.
2. Si no detecta nada o detecta de más, hay que ajustar las zonas en "Configuración" (muy abiertas/cerradas, mal ubicadas).

### 4.4 Pestaña "Calibración"
1. Elegí el **formato** de película (35mm / 16mm).
2. Con la película en la posición inicial, tocá **Marcar referencia 1**: el sistema detecta las perforaciones del fotograma actual y las guarda como punto de referencia contra el que se va a comparar cada fotograma siguiente.
3. Los botones **+100 / +10 / +1** y **avance fino** mueven el motor manualmente para ajustar la posición antes de marcar la referencia.
4. **Reiniciar referencias / contador** borra la Referencia 1/2 y el contador de pasos lógico — no mueve el motor físicamente.

### 4.5 Pestaña "Escaneo" (control maestro)
1. **01 Proyecto**: ponele un nombre, elegí el formato, tocá **Crear proyecto** (o elegí uno existente de la lista y **Abrir / reanudar seleccionado**).
2. **02 Espacio en disco**: poné cuántos **fotogramas totales tiene el rollo** (aproximado — se puede corregir después). El programa muestra el tamaño estimado total, cuánto ya se ocupó, y el espacio libre en el disco. Antes de guardar el primer fotograma usa un tamaño aproximado según el tipo de cámara (son valores de referencia, no exactos); apenas se guarda el primer fotograma real, empieza a usar el tamaño **promedio real** de los archivos ya guardados, mucho más preciso. Si avisa que el espacio libre no alcanza, se ve en rojo. También muestra la **carpeta exacta** donde se está guardando el proyecto, con un botón para abrirla directamente.
3. **03 Captura automática**: definí cuántos **fotogramas por tanda** y tocá **Iniciar / reanudar**. El programa va a avanzar el motor, detectar la perforación, estabilizar y guardar, fotograma a fotograma, automáticamente.
4. **Pausar al terminar fotograma** frena después del fotograma en curso (no corta de golpe). **DETENER AHORA** corta la tanda.
5. **Captura única · sin avance** saca una sola foto sin mover el motor (útil para pruebas).
6. Cuando termine el rollo, tocá **Exportar proyecto · copia verificada SHA-256**: genera el manifiesto con el hash de cada archivo, para poder confirmar después que no se corrompió nada.

### 4.6 Pestaña "Resultados"
1. Tocá **Actualizar lista** para cargar los fotogramas ya guardados del proyecto activo.
2. Navegá con **← Anterior / Siguiente →**: se ve el recorte **ANTES** (sin estabilizar) y **DESPUÉS** (alineado), con el desplazamiento X/Y, el giro y el residuo (cuanto más bajo, mejor el ajuste).
3. Nota: si la cámara real guarda RAW/DNG de verdad (no los `.sim.png` del modo simulado), hace falta instalar `rawpy` para poder previsualizarlo acá — sin eso, la pestaña avisa que no puede decodificar el archivo, pero el archivo RAW queda guardado igual.
4. **Aplicar mejora** (botón al final de la pestaña): recalcula la alineación de **todos** los fotogramas del proyecto contra el fotograma 0 (fijo), usando **todas** las perforaciones detectadas con ajuste robusto (RANSAC) en vez de un único par — pedido explícito del cliente, porque el método normal (un par de perforaciones por fotograma) daba algo de "giro" entre cuadros al reproducir la secuencia completa. Guarda el resultado en una carpeta nueva `mejorado/` **dentro del proyecto** (ej. `frame_00005_mejorado.png`), sin tocar los originales en `raw/`. Validado contra las 36 fotos reales del cliente: el rango de giro entre fotogramas bajó de -3.3°/+6.0° a -0.84°/+0.55°.

### 4.7 Pestaña "Prueba y ayuda"
Resumen rápido de estos mismos pasos, dentro del programa.

## 5. Cambiar de cámara en cualquier momento

El switch de la pestaña "Entrada" se puede usar en cualquier momento: desconecta la cámara actual y conecta la nueva, sin reiniciar el programa ni perder el proyecto activo. Es la pieza pensada específicamente para el hecho de que todavía no está confirmado qué 2 cámaras va a usar el cliente — ver `ARQUITECTURA.md` §3.

## 6. Qué prueba realmente el modo simulado

El modo simulado (`camera.type: "simulated"` en la config, o el switch en la UI) **no es una maqueta visual**: corre exactamente el mismo código de detección de perforaciones, cálculo de offset/rotación, guardado y verificación SHA-256 que correría con una cámara real — lo único que cambia es de dónde viene la imagen (de `assets/sample_frames/` en vez de un sensor) y que el motor no mueve nada físico. Por eso sirve como prueba real de que la lógica funciona, aunque el desarrollador no tenga acceso a las cámaras del cliente: lo único que falta probar con hardware real es la integración de cada SDK concreto (`camera_industrial.py`, `camera_dslr.py`) y la calibración de `steps_per_frame`/zonas con el film real.
