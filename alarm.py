# -*- coding: utf-8 -*-
"""定时提醒：闹钟 + 倒计时（弹窗、管理、设置窗口）"""
import os
import json
import random
import time
from PyQt6.QtCore import Qt, QTimer, QObject
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QPushButton,
                             QLineEdit, QCheckBox, QSpinBox, QTimeEdit,
                             QVBoxLayout, QHBoxLayout, QScrollArea)

try:
    import winsound
except ImportError:
    winsound = None


class AlarmPopup(QWidget):
    """到点提醒弹窗：置顶显示闹钟内容，点击按钮关闭"""

    def __init__(self, title, message, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        w, h = 320, 150
        self.setFixedSize(w, h)
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() // 2 - w // 2, screen.height() // 3 - h // 2)
        self.setStyleSheet('background: #ffe4f1; color: black;'
                           'border: 2px solid #ff8fbf; border-radius: 12px;')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)
        title_label = QLabel(title, self)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet('font-size: 16px; font-weight: bold;'
                                  'color: #ff3d8b; border: none;')
        layout.addWidget(title_label)
        msg_label = QLabel(message, self)
        msg_label.setWordWrap(True)
        msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg_label.setStyleSheet('font-size: 14px; border: none;')
        layout.addWidget(msg_label)
        ok_btn = QPushButton('知道了', self)
        ok_btn.setStyleSheet('color: black;')
        ok_btn.clicked.connect(self.close)
        layout.addWidget(ok_btn)


class AlarmManager(QObject):
    """闹钟/倒计时管理器：每秒检查一次，到点弹窗提醒并播放提示音"""

    def __init__(self, pet, parent=None):
        super().__init__(parent)
        self._pet = pet
        self._sound_enabled = True
        self.file = os.path.join(pet._data_dir, '闹钟配置.json')
        self.alarms = self.load()
        self._popups = []
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(1000)

    def load(self):
        if os.path.exists(self.file):
            try:
                with open(self.file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data if isinstance(data, list) else []
            except Exception:
                return []
        return []

    def save(self):
        active = [a for a in self.alarms if not a.get('done')]
        try:
            with open(self.file, 'w', encoding='utf-8') as f:
                json.dump(active, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _new_id(self):
        return int(time.time() * 1000) + random.randint(0, 999)

    def add_clock(self, name, hour, minute, repeat):
        self.alarms.append({'id': self._new_id(), 'type': 'clock',
                            'name': name, 'hour': hour, 'minute': minute,
                            'repeat': bool(repeat), 'done': False, 'last_day': None})
        self.save()

    def add_countdown(self, name, minutes):
        self.alarms.append({'id': self._new_id(), 'type': 'count',
                            'name': name, 'seconds': int(minutes) * 60,
                            'done': False})
        self.save()

    def remove(self, alarm_id):
        self.alarms = [a for a in self.alarms if a['id'] != alarm_id]
        self.save()

    def _tick(self):
        now = time.localtime()
        today = time.strftime('%Y-%m-%d', now)
        changed = False
        for a in self.alarms:
            if a.get('done'):
                continue
            if a['type'] == 'clock':
                if a['hour'] == now.tm_hour and a['minute'] == now.tm_min:
                    if a.get('last_day') == today:
                        continue
                    # 先标记完成再触发，避免触发失败导致每秒重试
                    if a.get('repeat'):
                        a['last_day'] = today
                    else:
                        a['done'] = True
                    changed = True
                    self._fire(a, '⏰ 闹钟时间到！')
            else:
                a['seconds'] = max(0, a['seconds'] - 1)
                if a['seconds'] <= 0:
                    a['done'] = True
                    self._fire(a, '⏳ 倒计时结束！')
                    changed = True
        if changed:
            self.save()

    def _fire(self, alarm, title):
        name = (alarm.get('name') or '').strip()
        if alarm['type'] == 'clock':
            msg = name or '到点啦，快看看时间！'
        else:
            msg = name or '时间到，休息一下吧！'
        self.show_popup(title, msg)
        self.play_sound()

    def play_sound(self):
        if not self._sound_enabled:
            return
        try:
            if winsound is not None:
                winsound.PlaySound('SystemExclamation',
                                   winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            pass

    def show_popup(self, title, msg):
        popup = AlarmPopup(title, msg)
        popup.show()
        self._popups.append(popup)
        # 弹窗关闭后（WA_DeleteOnClose）C++ 对象已被销毁，逐个安全清理
        keep = []
        for p in self._popups:
            try:
                if not p.isHidden():
                    keep.append(p)
            except RuntimeError:
                pass  # 已被销毁的弹窗，直接忽略
        self._popups = keep


class AlarmWindow(QWidget):
    """定时提醒窗口：支持多个闹钟和倒计时"""

    def __init__(self, pet, parent=None):
        super().__init__(parent)
        self._pet = pet
        self._mgr = pet.alarm_manager
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle('⏰ 定时提醒')
        self.setFixedSize(420, 520)
        self.setStyleSheet('font-size: 13px; background: #ffe4f1; color: black;')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        clock_title = QLabel('闹钟（指定时刻提醒）', self)
        clock_title.setStyleSheet('color: #ff3d8b; font-weight: bold; border: none;')
        layout.addWidget(clock_title)
        clock_row = QHBoxLayout()
        self._time_edit = QTimeEdit(self)
        self._time_edit.setDisplayFormat('HH:mm')
        self._time_edit.setStyleSheet('color: black;')
        self._alarm_name = QLineEdit(self)
        self._alarm_name.setPlaceholderText('提醒内容（可选）')
        self._alarm_name.setStyleSheet('color: black;')
        self._repeat_cb = QCheckBox('每天重复', self)
        self._repeat_cb.setStyleSheet('color: black;')
        add_clock_btn = QPushButton('添加闹钟', self)
        add_clock_btn.setStyleSheet('color: black;')
        add_clock_btn.clicked.connect(self.add_clock)
        clock_row.addWidget(self._time_edit)
        clock_row.addWidget(self._alarm_name, 1)
        clock_row.addWidget(self._repeat_cb)
        clock_row.addWidget(add_clock_btn)
        layout.addLayout(clock_row)

        count_title = QLabel('倒计时（定时提醒）', self)
        count_title.setStyleSheet('color: #ff3d8b; font-weight: bold; border: none;')
        layout.addWidget(count_title)
        count_row = QHBoxLayout()
        self._count_min = QSpinBox(self)
        self._count_min.setRange(1, 999)
        self._count_min.setSuffix(' 分钟')
        self._count_min.setStyleSheet('color: black;')
        self._count_name = QLineEdit(self)
        self._count_name.setPlaceholderText('名称（可选）')
        self._count_name.setStyleSheet('color: black;')
        add_count_btn = QPushButton('添加倒计时', self)
        add_count_btn.setStyleSheet('color: black;')
        add_count_btn.clicked.connect(self.add_countdown)
        count_row.addWidget(self._count_min)
        count_row.addWidget(self._count_name, 1)
        count_row.addWidget(add_count_btn)
        layout.addLayout(count_row)

        list_title = QLabel('进行中的提醒', self)
        list_title.setStyleSheet('color: #ff3d8b; font-weight: bold; border: none;')
        layout.addWidget(list_title)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet('background: transparent; border: none;')
        self._list_host = QWidget()
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        scroll.setWidget(self._list_host)
        layout.addWidget(scroll, 1)

        self._row_labels = {}
        self.refresh()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.update_countdowns)
        self._refresh_timer.start(1000)

    def add_clock(self):
        t = self._time_edit.time()
        self._mgr.add_clock(self._alarm_name.text(),
                            t.hour(), t.minute(), self._repeat_cb.isChecked())
        self._alarm_name.clear()
        self.refresh()

    def add_countdown(self):
        self._mgr.add_countdown(self._count_name.text(), self._count_min.value())
        self._count_name.clear()
        self.refresh()

    def remove(self, alarm_id):
        self._mgr.remove(alarm_id)
        self.refresh()

    def _clock_text(self, a):
        tag = '每天' if a.get('repeat') else '今天'
        if a.get('done'):
            tag = '已响铃'
        return '⏰ %02d:%02d  %s（%s）' % (a['hour'], a['minute'], a['name'], tag)

    def _count_text(self, a):
        if a.get('done'):
            return '⏳ %s（已结束）' % a['name']
        mm, ss = divmod(a['seconds'], 60)
        return '⏳ %s  剩余 %02d:%02d' % (a['name'], mm, ss)

    def refresh(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._row_labels = {}
        for a in self._mgr.alarms:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 4, 8, 4)
            row_layout.setSpacing(6)
            label = QLabel(a['type'] == 'clock' and self._clock_text(a)
                           or self._count_text(a), row)
            label.setStyleSheet('color: black; background: #fff0f6;'
                                'border: 1px solid #ff8fbf; border-radius: 8px;'
                                'padding: 4px 8px;')
            del_btn = QPushButton('删除', row)
            del_btn.setStyleSheet('color: black;')
            del_btn.clicked.connect(lambda _=False, aid=a['id']: self.remove(aid))
            row_layout.addWidget(label, 1)
            row_layout.addWidget(del_btn)
            self._list_layout.addWidget(row)
            if a['type'] == 'count' and not a.get('done'):
                self._row_labels[a['id']] = label
        self._list_layout.addStretch(1)

    def update_countdowns(self):
        for a in self._mgr.alarms:
            if a['type'] == 'count' and not a.get('done') and a['id'] in self._row_labels:
                mm, ss = divmod(a['seconds'], 60)
                self._row_labels[a['id']].setText('⏳ %s  剩余 %02d:%02d' % (a['name'], mm, ss))

    def closeEvent(self, event):
        self._pet.alarm_window = None
        event.accept()
