"""Punto de entrada de la aplicación de escritorio FILMS.

Uso:
    python main.py

Arranca en modo simulado (sin hardware conectado) — ver src/ui/desktop_app
y el switch de cámara en la pestaña "Entrada" para cambiar a cámara
industrial o DSLR una vez que estén disponibles físicamente.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from src.ui.desktop_app.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
