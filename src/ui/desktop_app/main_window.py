"""Ventana principal: las 7 pestañas del prototipo + "Ajustes" (nueva, no
estaba en el prototipo) para editar config/hardware_config.json desde la UI."""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QMainWindow, QStatusBar, QTabWidget, QVBoxLayout, QWidget

from .app_context import AppContext
from .tabs.calibration_tab import CalibrationTab
from .tabs.config_tab import ConfigTab
from .tabs.help_tab import HelpTab
from .tabs.input_tab import InputTab
from .tabs.perforations_tab import PerforationsTab
from .tabs.results_tab import ResultsTab
from .tabs.scan_tab import ScanTab
from .tabs.settings_tab import SettingsTab

APP_VERSION = "0.1.0"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FILMS · Escáner cinematográfico")
        self.resize(1200, 860)

        self.ctx = AppContext()

        header = QLabel("FILMS — ESCÁNER CINEMATOGRÁFICO / 35 + 16 mm")
        header.setStyleSheet("font-size: 16px; font-weight: bold; padding: 8px;")

        tabs = QTabWidget()
        self.scan_tab = ScanTab(self.ctx)
        self.input_tab = InputTab(self.ctx)
        self.results_tab = ResultsTab(self.ctx)
        self.calibration_tab = CalibrationTab(self.ctx)
        self.perforations_tab = PerforationsTab(self.ctx)
        self.config_tab = ConfigTab(self.ctx)
        self.help_tab = HelpTab()
        self.settings_tab = SettingsTab(self.ctx)

        tabs.addTab(self.scan_tab, "Escaneo")
        tabs.addTab(self.input_tab, "Entrada")
        tabs.addTab(self.results_tab, "Resultados")
        tabs.addTab(self.calibration_tab, "Calibración")
        tabs.addTab(self.perforations_tab, "Perforaciones")
        tabs.addTab(self.config_tab, "Configuración")
        tabs.addTab(self.help_tab, "Prueba y ayuda")
        tabs.addTab(self.settings_tab, "Ajustes")

        tabs.currentChanged.connect(self._on_tab_changed)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(header)
        layout.addWidget(tabs)
        self.setCentralWidget(central)

        status = QStatusBar()
        self.setStatusBar(status)
        status.showMessage(f"Listo · v{APP_VERSION}")

        # Marca de agua tipo "insignia" (pedido del cliente, basado en un
        # diseño HTML/CSS que mandó) — recreada con QSS porque esto es una
        # app de escritorio Qt, no una página web: no hay box-shadow ni
        # transiciones CSS, así que la sombra se arma con
        # QGraphicsDropShadowEffect y el "levantarse" al pasar el mouse se
        # deja de lado (Qt no anima propiedades de QSS), pero el resto del
        # look (insignia oscura, ícono </>, borde dorado que resalta en
        # hover, "GR" en blanco con la G dorada) sí se reproduce.
        credit_label = QLabel(
            '<span style="color:#f59e0b; font-weight:700;">&lt;/&gt;</span>'
            '&nbsp;&nbsp;'
            '<span style="color:#94a3b8;">Design &amp; Code by '
            '<a href="https://germanrodriguez.ar/" style="color:#ffffff; text-decoration:none; font-weight:700;">'
            '<span style="color:#f59e0b;">G</span>R</a></span>'
        )
        credit_label.setOpenExternalLinks(True)
        credit_label.setStyleSheet(
            """
            QLabel {
                background-color: #0f172a;
                padding: 6px 16px;
                border-radius: 13px;
                font-size: 11px;
                font-family: 'Segoe UI', Arial, sans-serif;
                border: 1px solid rgba(217, 119, 6, 0.35);
            }
            QLabel:hover {
                border: 1px solid rgba(217, 119, 6, 0.85);
            }
            """
        )
        shadow = QGraphicsDropShadowEffect(credit_label)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 140))
        credit_label.setGraphicsEffect(shadow)
        status.addPermanentWidget(credit_label)

    def _on_tab_changed(self, index: int) -> None:
        # La pestaña "Resultados" lee del disco cada vez que se vuelve a
        # mostrar, para reflejar fotogramas procesados en la pestaña "Escaneo".
        if self.centralWidget() is None:
            return
        if self.results_tab.isVisible():
            self.results_tab._reload_index()
