# storage/

## Responsabilidad

Escritura de los fotogramas capturados en **RAW/DNG** (nunca JPEG), de forma no destructiva, junto con la generación de hashes **SHA-256** para verificación de integridad al exportar.

## Contrato (interfaz esperada)

- `save_frame(raw_buffer, frame_number, metadata) → file_path` — guarda el original RAW/DNG tal como llega de la cámara.
- `save_correction(frame_number, dx, dy, theta, crop_box)` — guarda la transformación de alineación aplicada (no destructiva: el original no se sobrescribe).
- `verify_project(project_id) → manifest_with_hashes` — genera/valida el manifiesto SHA-256 por archivo para la exportación ("copia verificada SHA-256").

## Dependencias

- Ninguna hacia otros módulos de `src/` (es la capa más baja del pipeline); lo consumen `core/scan_controller` y `core/project_manager`.

## Notas técnicas

- El volumen de datos es alto (RAW/DNG por fotograma, miles de fotogramas por rollo): considerar escritura asíncrona/en cola para no bloquear el ciclo de captura.
- El status bar del prototipo ya expone espacio libre en disco ("57.2 GB libres") — este módulo debería poder reportar esa métrica a la UI.
