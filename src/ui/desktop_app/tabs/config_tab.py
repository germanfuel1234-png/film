"""Pestaña "Configuración": zonas de búsqueda de perforaciones (izquierda/derecha).

Los valores iniciales de los spinbox salen del archivo editable por el
cliente config/hardware_config.json (vía AppContext/Calibrator) — no están
hardcodeados acá. Guardar vuelve a escribir sobre el estado en memoria del
Calibrator (el archivo en disco no se sobreescribe desde la UI).
"""

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QGroupBox, QHBoxLayout, QPushButton, QSpinBox, QWidget

from ....vision.perforation_detection import SearchZone
from ..app_context import AppContext


def _zone_group(title: str, zone: SearchZone) -> tuple[QGroupBox, dict[str, QSpinBox]]:
    box = QGroupBox(title)
    form = QFormLayout(box)
    spins: dict[str, QSpinBox] = {}
    values = {"X inicial": zone.x0, "Y inicial": zone.y0, "X final": zone.x1, "Y final": zone.y1}
    for label, default in values.items():
        spin = QSpinBox()
        spin.setRange(0, 10000)
        spin.setValue(default)
        form.addRow(label, spin)
        spins[label] = spin
    return box, spins


class ConfigTab(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx

        layout = QHBoxLayout(self)

        self.left_box, self.left_spins = _zone_group("Zona de búsqueda · izquierda", ctx.config.calibration.search_zone_left)
        self.right_box, self.right_spins = _zone_group(
            "Zona de búsqueda · derecha", ctx.config.calibration.search_zone_right
        )
        layout.addWidget(self.left_box)
        layout.addWidget(self.right_box)

        save_button = QPushButton("Guardar zonas de búsqueda")
        save_button.clicked.connect(self._save_zones)
        layout.addWidget(save_button)

        ctx.config_changed.connect(self._sync_from_config)

    def _zone_from(self, spins: dict[str, QSpinBox]) -> SearchZone:
        return SearchZone(
            x0=spins["X inicial"].value(),
            y0=spins["Y inicial"].value(),
            x1=spins["X final"].value(),
            y1=spins["Y final"].value(),
        )

    def _save_zones(self) -> None:
        self._ctx.calibrator.set_search_zones(self._zone_from(self.left_spins), self._zone_from(self.right_spins))

    def _sync_from_config(self) -> None:
        for label, value in (
            ("X inicial", self._ctx.config.calibration.search_zone_left.x0),
            ("Y inicial", self._ctx.config.calibration.search_zone_left.y0),
            ("X final", self._ctx.config.calibration.search_zone_left.x1),
            ("Y final", self._ctx.config.calibration.search_zone_left.y1),
        ):
            self.left_spins[label].setValue(value)
        for label, value in (
            ("X inicial", self._ctx.config.calibration.search_zone_right.x0),
            ("Y inicial", self._ctx.config.calibration.search_zone_right.y0),
            ("X final", self._ctx.config.calibration.search_zone_right.x1),
            ("Y final", self._ctx.config.calibration.search_zone_right.y1),
        ):
            self.right_spins[label].setValue(value)
