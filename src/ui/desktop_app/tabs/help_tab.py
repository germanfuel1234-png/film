"""Pestaña "Prueba y ayuda": instructivo rápido, sin dependencias de runtime."""

from __future__ import annotations

from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget

HELP_TEXT = """
<h2>Primeros pasos</h2>
<ol>
<li>En <b>Entrada</b>, elegí el tipo de cámara con el switch (industrial, DSLR o simulada) y conectala.
    Mientras no esté confirmado el hardware definitivo, usá "simulada" para probar todo el flujo.</li>
<li>En <b>Configuración</b>, definí las zonas de búsqueda de perforaciones (izquierda/derecha).</li>
<li>En <b>Calibración</b>, elegí el formato de película, alineá el primer fotograma y marcá la Referencia 1.</li>
<li>En <b>Entrada</b>, definí el encuadre de referencia (X/Y inicial y final).</li>
<li>En <b>Escaneo</b>, creá un proyecto y arrancá la captura automática por tandas.</li>
<li>En <b>Resultados</b>, revisá la comparativa antes/después de cada fotograma.</li>
<li>Exportá el proyecto: genera una copia con verificación <b>SHA-256</b> por archivo.</li>
</ol>

<h3>Notas importantes</h3>
<ul>
<li>La captura final siempre se guarda en <b>RAW/DNG</b>, nunca en JPEG.</li>
<li>Los originales nunca se sobrescriben: la corrección de alineación se guarda aparte y es reaplicable.</li>
<li>Todavía no está confirmado qué 2 cámaras se van a usar en definitiva — por eso existe el switch de cámara.</li>
</ul>
"""


class HelpTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setHtml(HELP_TEXT)
        layout.addWidget(browser)
