# -*- coding: utf-8 -*-
"""AI 聊天：短气泡 + 完整聊天窗口"""
import os
import base64
import time
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QWidget, QLabel, QGraphicsOpacityEffect, QScrollArea,
                             QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
                             QFileDialog, QMessageBox)
from ai import trim_history, AIWorker
from agent import AgentWorker


class SpeechBubble(QWidget):
    """AI 回复短气泡：在桌宠上方短暂显示，点击可打开聊天窗口"""

    def __init__(self, text, start_pos, on_click=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._on_click = on_click

        label = QLabel(text, self)
        label.setWordWrap(True)
        label.setMaximumWidth(240)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        label.setStyleSheet('background: #ffb6d5;'
                            'color: black;'
                            'border: 1px solid #ff8fbf; border-radius: 10px; padding: 8px;')
        label.adjustSize()
        margin = 12
        w = min(label.width() + margin * 2, 270)
        label.setFixedWidth(w - margin * 2)
        label.adjustSize()
        self.setFixedSize(w, label.height() + margin * 2)
        label.move(margin, margin)
        self._label = label

        self._base_x = start_pos.x()
        self._base_y = start_pos.y()
        self.move(start_pos)
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)
        self.show()

        self._anim_step = 0
        self._anim_start = 0.0
        self._hold_ms = 6000
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start(30)

    def _tick(self):
        if self._anim_start == 0:
            self._anim_start = time.time()
        elapsed = (time.time() - self._anim_start) * 1000
        if self._anim_step == 0:
            t = min(elapsed / 250, 1)
            eased = 1 - (1 - t) ** 3
            self._opacity_effect.setOpacity(eased)
            self.move(self._base_x, self._base_y - int(10 * eased))
            if t >= 1:
                self._anim_step = 1
                self._anim_start = time.time()
        elif self._anim_step == 1:
            if elapsed >= self._hold_ms:
                self._anim_step = 2
                self._anim_start = time.time()
        elif self._anim_step == 2:
            t = min(elapsed / 400, 1)
            eased = t ** 3
            self._opacity_effect.setOpacity(1 - eased)
            if t >= 1:
                self._anim_timer.stop()
                self.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._on_click:
                self._on_click()
            self.close()
        event.accept()


class AIChatWindow(QWidget):
    """AI 聊天窗口：消息列表 + 输入框（调用 OpenAI 兼容接口）"""

    def __init__(self, pet, config, parent=None):
        super().__init__(parent)
        self._pet = pet
        self._config = config
        self._history = [{'role': 'system', 'content': config.get('system_prompt', '')}]
        self._busy = False
        self._worker = None

        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle('✨ 和小蕾米聊天')
        self.setFixedSize(360, 480)
        self.setStyleSheet('font-size: 13px; background: #ffe4f1; color: black;')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet('QScrollArea { background: transparent; border: none; }')
        self._messages_host = QWidget()
        self._messages_layout = QVBoxLayout(self._messages_host)
        self._messages_layout.setContentsMargins(4, 4, 4, 4)
        self._messages_layout.setSpacing(6)
        self._messages_layout.addStretch()
        self._scroll.setWidget(self._messages_host)
        layout.addWidget(self._scroll, 1)

        self._status_label = QLabel('', self)
        self._status_label.setStyleSheet('color: #ff3d8b; border: none; font-size: 12px;')
        self._status_label.hide()
        layout.addWidget(self._status_label)

        input_row = QWidget(self)
        input_layout = QHBoxLayout(input_row)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(6)
        self._attach_btn = QPushButton('图片', input_row)
        self._attach_btn.setStyleSheet('color: black;')
        self._attach_btn.clicked.connect(self.attach_image)
        input_layout.addWidget(self._attach_btn)
        self._input = QLineEdit(input_row)
        self._input.setPlaceholderText('输入问题，回车发送…')
        self._input.setStyleSheet('placeholder-text-color: black; color: black;')
        self._input.returnPressed.connect(self.send)
        input_layout.addWidget(self._input, 1)
        self._send_btn = QPushButton('发送', input_row)
        self._send_btn.setStyleSheet('color: black;')
        self._send_btn.clicked.connect(self.send)
        input_layout.addWidget(self._send_btn)
        layout.addWidget(input_row)

        self._pending_image = None
        self._add_message('assistant', '你好呀～我是小蕾米，学习、工作、生活的问题都可以问我！')

    def attach_image(self):
        """选择一张题目图片附加到下次发送"""
        path, _ = QFileDialog.getOpenFileName(self, '选择题目图片', '',
                                              '图片文件 (*.png *.jpg *.jpeg *.bmp *.gif)')
        if not path:
            return
        ext = os.path.splitext(path)[1].lstrip('.').lower()
        mime = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                'bmp': 'image/bmp', 'gif': 'image/gif'}.get(ext, 'image/png')
        self._pending_image = (path, mime)
        self._input.setPlaceholderText('已附加图片，可输入问题后发送')
        self._input.setFocus()

    def _build_image_content(self, image, text):
        """把图片转成 OpenAI 兼容的 content 列表"""
        path, mime = image
        with open(path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('ascii')
        content = [{'type': 'image_url',
                    'image_url': {'url': 'data:{};base64,{}'.format(mime, b64)}}]
        content.append({'type': 'text',
                        'text': text or '请仔细解答这张图片中的题目，并给出过程。'})
        return content

    def _add_message(self, role, text):
        label = QLabel(text, self._messages_host)
        label.setWordWrap(True)
        label.setMaximumWidth(320)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if role == 'user':
            label.setStyleSheet('background: #ffc6de; color: black;'
                                'border-radius: 10px; padding: 8px;')
        else:
            label.setStyleSheet('background: #fff0f6; color: black;'
                                'border-radius: 10px; padding: 8px;')
        self._messages_layout.insertWidget(self._messages_layout.count() - 1, label)
        self._scroll.ensureWidgetVisible(label)

    def send(self):
        text = self._input.text().strip()
        if not text and not self._pending_image:
            return
        if self._busy:
            return
        if not self._config.get('api_key'):
            QMessageBox.warning(self, '未配置 API',
                                '请先在程序目录的 AI配置.json 中填写 api_key 后重试。')
            return
        model = self._config.get('model', '')
        if self._pending_image:
            image = self._pending_image
            self._pending_image = None
            self._input.setPlaceholderText('输入问题，回车发送…')
            self._add_message('user', ('[图片] ' + text) if text else '[图片]')
            self._history.append({'role': 'user',
                                  'content': self._build_image_content(image, text)})
            model = self._config.get('vision_model', '') or model
        else:
            self._add_message('user', text)
            self._history.append({'role': 'user', 'content': text})
        self._input.clear()
        self._history = trim_history(self._history, int(self._config.get('max_history', 10)))
        self._busy = True
        self._send_btn.setEnabled(False)
        self._input.setEnabled(False)
        # Agent 模式：普通文本走工具循环（能操作引擎/设提醒/做表情）；
        # 图片题目走纯视觉问答；配置里 agent=false 可关掉 agent
        if self._pending_image is None and bool(self._config.get('agent', True)):
            self._worker = AgentWorker(self._config, list(self._history), self._pet)
            self._worker.activity.connect(self._on_activity)
        else:
            self._worker = AIWorker(self._config.get('base_url', ''),
                                    self._config.get('api_key', ''),
                                    model,
                                    list(self._history), self)
        self._worker.finished.connect(self._on_reply)
        self._pet.set_thinking(True)
        self._worker.start()

    def _on_activity(self, text):
        self._status_label.setText('⚙ ' + text)
        self._status_label.show()

    def _on_reply(self, text, error):
        self._busy = False
        self._send_btn.setEnabled(True)
        self._input.setEnabled(True)
        self._status_label.hide()
        self._pet.set_thinking(False)
        if error:
            self._add_message('assistant', '[出错了] ' + error)
            self._pet.show_bubble('唔，刚才出错了…')
            return
        self._history.append({'role': 'assistant', 'content': text})
        self._add_message('assistant', text)
        self._pet.show_bubble(text)

    def closeEvent(self, event):
        self._pet.chat_window = None
        event.accept()
