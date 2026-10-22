# hardware/motor

## Responsabilidad

Comunicación con el controlador del motor paso a paso que avanza la película, vía Serial/USB hacia el firmware en `firmware/stepper_controller`.

## Contrato (interfaz esperada)

- `connect(port, baudrate)` / `disconnect()`
- `move(steps: int, direction: str, fine: bool = False)` — avance grueso o fino (ver controles "+100 / +10 / +1" y "avance fino" de la pestaña Calibración de la demo).
- `stop()` — frenado inmediato ("DETENER AHORA").
- `get_position()` — posición/pasos acumulados desde el último reinicio.
- `reset_counter(keep_position: bool = True)` — reinicia el contador conservando la posición física, como describe el prototipo.

## Dependencias

- `firmware/stepper_controller` (protocolo de comandos compartido — ver `ARQUITECTURA.md` §4).

## Notas técnicas

- Latencia de respuesta del motor es crítica para el throughput del escaneo: este módulo debe operar de forma asíncrona respecto al resto del pipeline (no bloquear UI ni vision).
- Debe exponer manejo explícito de error de desconexión/pérdida de pasos para que `core/scan_controller` pueda pausar el ciclo y notificar al operador.
