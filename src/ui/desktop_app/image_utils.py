"""Conversión de frames OpenCV (numpy BGR) a QPixmap para mostrarlos en la UI."""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtGui import QImage, QPixmap


def frame_to_pixmap(frame: np.ndarray) -> QPixmap:
    if frame.ndim == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
    else:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    frame = np.ascontiguousarray(frame)
    h, w, ch = frame.shape
    image = QImage(frame.data, w, h, ch * w, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(image.copy())
