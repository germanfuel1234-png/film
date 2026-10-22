"""Pestaña "Calibración": formato de película, avance manual del motor
(grueso/fino) y marcado de referencias 1/2."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ....hardware.camera_base import CameraConnectionError
from ....core.calibration import FILM_FORMATS
from ..app_context import AppContext


class CalibrationTab(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx

        root = QHBoxLayout(self)

        # Formato + avance
        left = QVBoxLayout()
        root.addLayout(left, stretch=1)

        format_box = QGroupBox("Guía de prueba")
        format_form = QFormLayout(format_box)
        self.format_combo = QComboBox()
        self.format_combo.addItems(list(FILM_FORMATS.keys()))
        self.format_combo.setCurrentText(ctx.config.calibration.film_format)
        self.format_combo.currentTextChanged.connect(self._ctx.calibrator.set_film_format)
        format_form.addRow("Formato", self.format_combo)
        left.addWidget(format_box)

        advance_box = QGroupBox("Avance · solo hacia adelante")
        advance_layout = QVBoxLayout(advance_box)

        self.big_step_spin = QSpinBox()
        self.big_step_spin.setRange(1, 100000)
        self.big_step_spin.setValue(ctx.config.motor.steps_per_frame)
        advance_layout.addWidget(QLabel("Avance grande [pulsos]"))
        advance_layout.addWidget(self.big_step_spin)

        big_advance_btn = QPushButton("Avanzar cantidad indicada →")
        big_advance_btn.clicked.connect(lambda: self._advance(self.big_step_spin.value(), fine=False))
        advance_layout.addWidget(big_advance_btn)

        fine_row = QHBoxLayout()
        for steps in (100, 10, 1):
            btn = QPushButton(f"+{steps}")
            btn.clicked.connect(lambda _, s=steps: self._advance(s, fine=True))
            fine_row.addWidget(btn)
        advance_layout.addLayout(fine_row)

        self.position_label = QLabel("Desde reinicio: 0 pulsos")
        advance_layout.addWidget(self.position_label)
        left.addWidget(advance_box)

        # Referencias
        right = QVBoxLayout()
        root.addLayout(right, stretch=1)

        ref_box = QGroupBox("Referencias por perforaciones")
        ref_layout = QVBoxLayout(ref_box)

        mark1_btn = QPushButton("Marcar referencia 1")
        mark1_btn.clicked.connect(lambda: self._mark_reference(1))
        ref_layout.addWidget(mark1_btn)

        mark2_btn = QPushButton("Marcar referencia 2")
        mark2_btn.clicked.connect(lambda: self._mark_reference(2))
        ref_layout.addWidget(mark2_btn)

        self.ref1_label = QLabel("Referencia 1: sin marcar")
        self.ref2_label = QLabel("Referencia 2: sin marcar")
        ref_layout.addWidget(self.ref1_label)
        ref_layout.addWidget(self.ref2_label)

        reset_btn = QPushButton("Reiniciar referencias / contador")
        reset_btn.clicked.connect(self._reset_references)
        ref_layout.addWidget(reset_btn)

        hint = QLabel(
            "Reiniciar conserva la posición real del motor y el ajuste guardado.\n"
            "Alineá el primer fotograma y marcá la referencia 1."
        )
        hint.setWordWrap(True)
        ref_layout.addWidget(hint)

        right.addWidget(ref_box)

        ctx.config_changed.connect(self._sync_from_config)

    def _sync_from_config(self) -> None:
        self.format_combo.setCurrentText(self._ctx.config.calibration.film_format)
        self.big_step_spin.setValue(self._ctx.config.motor.steps_per_frame)

    def _advance(self, steps: int, fine: bool) -> None:
        try:
            self._ctx.motor.move(steps, fine=fine)
        except Exception as exc:  # noqa: BLE001
            self.position_label.setText(f"Error de motor: {exc}")
            return
        self.position_label.setText(f"Desde reinicio: {self._ctx.motor.state.position_steps} pulsos")

    def _mark_reference(self, slot: int) -> None:
        try:
            frame = self._ctx.camera.get_preview_frame()
            pair = self._ctx.calibrator.mark_reference(slot, frame)
        except (CameraConnectionError, RuntimeError) as exc:
            label = self.ref1_label if slot == 1 else self.ref2_label
            label.setText(f"Referencia {slot}: error — {exc}")
            return
        label = self.ref1_label if slot == 1 else self.ref2_label
        left, right = pair
        label.setText(f"Referencia {slot}: izq=({left.cx:.1f},{left.cy:.1f}) der=({right.cx:.1f},{right.cy:.1f})")

    def _reset_references(self) -> None:
        self._ctx.calibrator.reset_references()
        self.ref1_label.setText("Referencia 1: sin marcar")
        self.ref2_label.setText("Referencia 2: sin marcar")
        self.position_label.setText("Desde reinicio: 0 pulsos")
