# ui/desktop_app

## Responsabilidad

Interfaz de escritorio que replica las 7 pestañas ya prototipadas y validadas visualmente:

1. **Escaneo** — control maestro (proyecto, preparación, captura automática) → consume `core/scan_controller` + `core/project_manager`.
2. **Entrada** — fuente de cámara/fotos, encuadre de referencia, rotación → consume `hardware/camera_*` + `core/calibration`.
3. **Resultados** — comparativa antes/después, offsets y giro → consume `vision/stabilization` (resultados ya calculados y persistidos).
4. **Calibración** — guía de prueba, avance manual, marcado de referencias → consume `core/calibration`.
5. **Perforaciones** — marcado/ajuste fino de detección de perforaciones → consume `vision/perforation_detection` + `core/calibration`.
6. **Configuración** — zonas de búsqueda izquierda/derecha → consume `core/calibration`.
7. **Prueba y ayuda** — instructivo estático, sin dependencias de runtime.

## Dependencias

- Toda la capa `core/` (nunca accede a `hardware/` o `vision/` directamente — mantiene la separación UI/lógica).

## Notas técnicas

- Framework recomendado: PySide6 (ver `ARQUITECTURA.md` §1).
- La UI debe reflejar estado en tiempo real (contador "guardados/aceptados", FPS de tanda, próximo avance) vía el callback/evento que expone `core/scan_controller`.
