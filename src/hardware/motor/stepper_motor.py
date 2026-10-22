"""Driver del motor paso a paso controlado por Arduino, vía Serial/USB.

Protocolo de comandos de texto plano (ver proyecto_film/ARQUITECTURA.md §4
y firmware/stepper_controller/stepper_controller.ino, que implementa el
mismo protocolo del lado del microcontrolador):

    MOVE <pasos> <dir:1|-1>   -> ACK <pasos_reales>   | ERR <motivo>
    STOP                      -> ACK
    STATUS                    -> POS <pasos_acumulados>
    RESET_COUNTER             -> ACK

Cada línea enviada y recibida termina en '\n'.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT_S = 2.0


class MotorStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    ERROR = "error"


class MotorConnectionError(RuntimeError):
    """Error al conectar o comunicarse con el controlador del motor."""


@dataclass
class MotorState:
    status: MotorStatus = MotorStatus.DISCONNECTED
    position_steps: int = 0
    last_error: Optional[str] = None


class StepperMotor:
    """Cliente serie para el firmware Arduino en firmware/stepper_controller."""

    def __init__(self, port: str, baudrate: int = DEFAULT_BAUDRATE, timeout: float = DEFAULT_TIMEOUT_S) -> None:
        self._port = port
        self._baudrate = baudrate
        self._timeout = timeout
        self._serial = None
        self._state = MotorState()

    @property
    def state(self) -> MotorState:
        return self._state

    def connect(self) -> None:
        try:
            import serial
        except ImportError as exc:
            self._state = MotorState(status=MotorStatus.ERROR, last_error="Falta 'pyserial' (pip install pyserial).")
            raise MotorConnectionError(self._state.last_error) from exc

        try:
            self._serial = serial.Serial(self._port, self._baudrate, timeout=self._timeout)
        except serial.SerialException as exc:
            self._state = MotorState(status=MotorStatus.ERROR, last_error=f"No se pudo abrir {self._port}: {exc}")
            raise MotorConnectionError(self._state.last_error) from exc

        self._state = MotorState(status=MotorStatus.CONNECTED)
        # El Arduino suele resetearse al abrir el puerto serie; se le da
        # un respiro antes del primer comando (consistente con el firmware).
        self.get_position()

    def disconnect(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None
        self._state = MotorState(status=MotorStatus.DISCONNECTED)

    def _send_command(self, command: str) -> str:
        if self._serial is None:
            raise MotorConnectionError("StepperMotor no está conectado: llamá a connect() primero.")
        self._serial.write((command.strip() + "\n").encode("ascii"))
        self._serial.flush()
        response = self._serial.readline().decode("ascii", errors="replace").strip()
        if not response:
            self._state.last_error = f"Sin respuesta del Arduino para el comando: {command}"
            raise MotorConnectionError(self._state.last_error)
        if response.startswith("ERR"):
            self._state.last_error = response
            raise MotorConnectionError(f"El controlador del motor devolvió un error: {response}")
        return response

    def move(self, steps: int, fine: bool = False) -> int:
        """Avanza `steps` pasos (positivo=adelante, negativo=atrás).

        `fine` solo se usa para que capas superiores (UI/calibración)
        distingan avance grueso vs. fino; el firmware siempre mueve la
        cantidad exacta de pasos pedida.
        """
        direction = 1 if steps >= 0 else -1
        response = self._send_command(f"MOVE {abs(steps)} {direction}")
        # respuesta esperada: "ACK <pasos_reales_movidos>"
        parts = response.split()
        moved = int(parts[1]) if len(parts) > 1 and parts[1].lstrip("-").isdigit() else abs(steps)
        self._state.position_steps += moved * direction
        return moved

    def stop(self) -> None:
        self._send_command("STOP")

    def get_position(self) -> int:
        response = self._send_command("STATUS")
        # respuesta esperada: "POS <pasos_acumulados>"
        parts = response.split()
        position = int(parts[1]) if len(parts) > 1 else self._state.position_steps
        self._state.position_steps = position
        return position

    def reset_counter(self) -> None:
        """Reinicia el contador de pasos conservando la posición física del motor."""
        self._send_command("RESET_COUNTER")
        self._state.position_steps = 0


class SimulatedStepperMotor(StepperMotor):
    """Variante sin hardware: útil para desarrollar/probar scan_controller
    y la UI mientras no hay un Arduino conectado."""

    def __init__(self) -> None:  # noqa: super().__init__ intencionalmente no llamado (no usa serial real)
        self._state = MotorState()

    def connect(self) -> None:
        self._state = MotorState(status=MotorStatus.CONNECTED)

    def disconnect(self) -> None:
        self._state = MotorState(status=MotorStatus.DISCONNECTED)

    def move(self, steps: int, fine: bool = False) -> int:
        direction = 1 if steps >= 0 else -1
        self._state.position_steps += abs(steps) * direction
        return abs(steps)

    def stop(self) -> None:
        return None

    def get_position(self) -> int:
        return self._state.position_steps

    def reset_counter(self) -> None:
        self._state.position_steps = 0
