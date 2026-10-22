# firmware/stepper_controller

## Responsabilidad

Firmware del microcontrolador (Arduino/equivalente) que mueve físicamente el motor paso a paso y responde a comandos recibidos por Serial/USB desde `src/hardware/motor`.

## Contrato (protocolo serie — ver `ARQUITECTURA.md` §4)

- `MOVE <pasos> <dirección>` → `ACK` al completar el movimiento.
- `STOP` → frenado inmediato.
- `STATUS` → devuelve posición/pasos acumulados.
- `RESET_COUNTER` → reinicia el contador conservando la posición física real del motor.

## Notas técnicas

- Modelo de motor/driver y microcontrolador exactos: pendientes de definición con el cliente (ver pregunta 2 en `../../ESPECIFICACIONES_PROYECTO.md`).
- El firmware debe soportar pasos "finos" y "gruesos" (micropasos) según lo observado en la UI de calibración del prototipo (+100/+10/+1, avance fino).
