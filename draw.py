# -*- coding: utf-8 -*-
"""画画结果弹出窗口：淡入淡出 + 向上弹出"""
import time
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QWidget, QGraphicsOpacityEffect
from PyQt6.QtGui import QPixmap, QPainter


class DrawResultPopup(QWidget):
    """画画结果弹出窗口：淡入淡出 + 向上弹出"""

    def __init__(self, image_path, start_pos, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        pixmap = QPixmap(image_path)
        if pixmap.width() > 200:
            pixmap = pixmap.scaledToWidth(200, Qt.TransformationMode.SmoothTransformation)
        self.setFixedSize(pixmap.width(), pixmap.height())
        self._pixmap = pixmap
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.01)
        self.setGraphicsEffect(self._opacity_effect)
        self._base_x = start_pos.x()
        self._base_y = start_pos.y()
        self.move(start_pos)
        self.show()
        self._anim_step = 0
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._update_animation)
        self._anim_timer.start(30)
        self._anim_start_time = 0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._pixmap)

    def _update_animation(self):
        if self._anim_start_time == 0:
            self._anim_start_time = time.time()
        elapsed = (time.time() - self._anim_start_time) * 1000
        if self._anim_step == 0:
            t = min(elapsed / 500, 1)
            eased = 1 - (1 - t) ** 3
            self._opacity_effect.setOpacity(eased)
            self.move(self._base_x, int(self._base_y - 30 * eased))
            if t >= 1:
                self._anim_step = 1
                self._anim_start_time = time.time()
        elif self._anim_step == 1:
            if elapsed >= 1000:
                self._anim_step = 2
                self._anim_start_time = time.time()
        elif self._anim_step == 2:
            t = min(elapsed / 800, 1)
            eased = t ** 3
            self._opacity_effect.setOpacity(1 - eased)
            self.move(self._base_x, int(self._base_y - 30 - 50 * eased))
            if t >= 1:
                self._anim_timer.stop()
                self.close()
