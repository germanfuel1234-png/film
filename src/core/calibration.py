"""Estado de calibración: formato de película, zonas de búsqueda y
referencias de alineación — cubre las pestañas "Calibración",
"Perforaciones" y "Configuración" del prototipo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..vision.perforation_detection import Perforation, SearchZone, detect_perforations, best_perforation_pair
from ..vision.stabilization import ReferenceBox

FILM_FORMATS = {
    "35mm": {"perforations_per_frame": 4},
    "16mm": {"perforations_per_frame": 1},
}


@dataclass
class CalibrationState:
    film_format: str = "35mm"
    left_zone: Optional[SearchZone] = None
    right_zone: Optional[SearchZone] = None
    reference_box: Optional[ReferenceBox] = None
    reference_pair: Optional[tuple[Perforation, Perforation]] = None  # "Referencia 1"
    reference_pair_2: Optional[tuple[Perforation, Perforation]] = None  # "Referencia 2"
    motor_steps_since_reset: int = 0
    # Rotación antihoraria aplicada al fotograma final (0/90/180/270): la
    # cámara suele capturar el film "de costado" (perforaciones
    # arriba/abajo en vez de a los lados), así que hace falta rotar para
    # presentarlo en la orientación de lectura normal — ya estaba previsto
    # en la UI ("Rotación antihoraria" en la pestaña Entrada) pero no se
    # aplicaba a nada.
    output_rotation_deg: int = 0


class Calibrator:
    """Flujo de calibración previo al escaneo automático."""

    def __init__(self) -> None:
        self.state = CalibrationState()

    def set_film_format(self, film_format: str) -> None:
        if film_format not in FILM_FORMATS:
            raise ValueError(f"Formato de película desconocido: {film_format} (válidos: {list(FILM_FORMATS)})")
        self.state.film_format = film_format

    def set_search_zones(self, left: SearchZone, right: SearchZone) -> None:
        self.state.left_zone = left
        self.state.right_zone = right

    def set_reference_box(self, box: ReferenceBox) -> None:
        self.state.reference_box = box

    def set_output_rotation(self, degrees: int) -> None:
        if degrees % 90 != 0:
            raise ValueError(f"La rotación tiene que ser múltiplo de 90° (recibido: {degrees})")
        self.state.output_rotation_deg = degrees % 360

    def mark_reference(self, slot: int, frame) -> tuple[Perforation, Perforation]:
        """Detecta perforaciones en el fotograma actual y las guarda como
        Referencia 1 (slot=1) o Referencia 2 (slot=2), tal como el botón
        "Marcar referencia 1" del prototipo."""
        if self.state.left_zone is None or self.state.right_zone is None:
            raise RuntimeError("Hay que definir las zonas de búsqueda (set_search_zones) antes de calibrar.")

        perforations = detect_perforations(frame, self.state.left_zone, self.state.right_zone)
        pair = best_perforation_pair(perforations)
        if pair is None:
            raise RuntimeError("No se detectaron perforaciones en ambas zonas sobre el fotograma de referencia.")

        if slot == 1:
            self.state.reference_pair = pair
        elif slot == 2:
            self.state.reference_pair_2 = pair
        else:
            raise ValueError("slot debe ser 1 o 2")
        return pair

    def reset_references(self, keep_motor_position: bool = True) -> None:
        """"Reiniciar referencias/contador": conserva la posición física del
        motor (el motor no se mueve), solo limpia las referencias marcadas
        y el contador de pasos lógico desde el último reinicio."""
        self.state.reference_pair = None
        self.state.reference_pair_2 = None
        self.state.motor_steps_since_reset = 0
        # keep_motor_position se deja explícito en la firma para dejar
        # constancia de que el motor físico NO se reposiciona acá; eso lo
        # hace hardware/motor por separado si el operador lo pide.

    def is_ready_for_scan(self) -> bool:
        return (
            self.state.left_zone is not None
            and self.state.right_zone is not None
            and self.state.reference_box is not None
            and self.state.reference_pair is not None
        )
