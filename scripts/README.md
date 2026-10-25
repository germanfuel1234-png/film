# scripts/

Herramientas de línea de comandos, todas pensadas para correr sin hardware real (cámara/motor/Raspberry Pi simulados en software).

## `demo_simulation.py`

Demo rápida: corre el ciclo completo de escaneo (avanzar → detectar → estabilizar → guardar → exportar con SHA-256) sobre los 5 fotogramas de ejemplo de `assets/sample_frames/`. Pensado para verificar en segundos que el sistema arranca y funciona de punta a punta.

```bash
.venv/bin/python scripts/demo_simulation.py
```

## `generate_synthetic_roll.py`

Genera un "rollo" sintético de N fotogramas (misma geometría 1920×1080 que las fotos reales del cliente, perforaciones arriba/abajo) con un leve bamboleo mecánico aleatorio por fotograma (semilla fija, reproducible). Sirve para tener un rollo largo de prueba sin necesitar miles de fotos reales.

```bash
.venv/bin/python scripts/generate_synthetic_roll.py --count 3000 --out /tmp/rollo_grande
```

## `stress_test_full_roll.py`

**Responde la pregunta "¿esto aguanta una película entera?" sin hardware real.** Genera un rollo sintético y corre el pipeline COMPLETO sobre él: escaneo en vivo (cámara + motor simulados, con la verificación de posición "ojo" en vivo) y después "Aplicar mejora" fraccionado en tandas, incluyendo una **interrupción simulada a mitad de camino** (deja un archivo a medio escribir, como un corte de luz real) para confirmar que el sistema se recupera y retoma sin perder ni corromper nada. Al final mide la inclinación real sobre el rollo completo terminado (no solo la última tanda) y reporta tiempo y memoria pico.

```bash
.venv/bin/python scripts/stress_test_full_roll.py --count 500
.venv/bin/python scripts/stress_test_full_roll.py --count 3000 --keep   # --keep conserva la carpeta temporal para inspeccionar
```

**Qué SÍ valida:** la lógica completa (detección de perforaciones, registro robusto, cero absoluto, resumibilidad, escritura atómica) a la escala de una película entera, con cientos o miles de fotogramas distintos, no solo las 36 fotos reales de prueba.

**Qué NO valida:** el rendimiento real en una Raspberry Pi. Los tiempos y la memoria que reporta son de la PC donde se corre, no de la Raspberry Pi — ver `docs/especificaciones_control_motor_camara.pdf` para la estimación (no medición) de cuánto tardaría ahí. Tampoco valida si el SDK de la cámara industrial Huateng tiene soporte ARM, ni nada que dependa de hardware físico real. Para eso hace falta una Raspberry Pi física o una instancia cloud ARM — ver conversación/decisión pendiente al respecto.
