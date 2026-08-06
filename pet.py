# -*- coding: utf-8 -*-
"""
小蕾米桌宠（PyQt6）
============================
从 ZanyZebra 的 Little-Remielle 打包版反编译还原的开源实现。

注意：原版使用 PyQt5（Qt 5.15.2），在较新的 Windows 11 上会出现
"无法初始化 Qt 平台插件" 而无法启动；本版改用 PyQt6（Qt 6），兼容新系统。

运行方式：
    pip install PyQt6
    python pet.py

交互：
    左键拖拽  = 移动位置
    左键单击  = 随机表情互动（2 秒后恢复）
    左键双击  = 切换下一个表情
    鼠标滚轮  = 缩放（0.5x ~ 2x）
    右键菜单  = 和小蕾米聊天 / 画画 / 定时提醒 / 重置位置和大小 / 作者信息 / 退出

AI 聊天：
    在程序目录的 AI配置.json 中填入任意 OpenAI 兼容接口的 api_key，
    右键菜单点"和小蕾米聊天"即可开聊；收到回复时桌宠上方会弹出短气泡，
    点气泡可打开完整聊天窗口。

模块结构：
    constants.py  常量配置（GIF 列表、画画序列、AI 配置模板）
    ai.py         AI 后台请求线程 + 消息历史裁剪
    chat.py       AI 聊天（短气泡 + 聊天窗口）
    games.py      小游戏（猜数字 / 石头剪刀布 / 打地鼠）
    alarm.py      定时提醒（闹钟 + 倒计时）
    draw.py       画画结果弹窗
    pet.py        桌宠主窗口（本文件）
"""
import sys
import os
import random
import json
import glob
import time
import traceback
from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QMessageBox
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QPixmap, QMovie, QPainter, QIcon, QAction

from constants import (GIF_NAMES, DRAW_SEQUENCE, SPECIAL_DURATIONS,
                       CLICK_REACTION_OPTIONS, AI_CONFIG_FILE, AI_CONFIG_TEMPLATE,
                       GENDER_FILE, GENDER_ADDRESS)
from ai import AIWorker, trim_history
from chat import SpeechBubble, AIChatWindow
from games import rps_winner, GuessGame, RPSGame, MoleGame, GameWindow
from alarm import AlarmPopup, AlarmManager, AlarmWindow
from draw import DrawResultPopup


class DesktopPet(QLabel):
    """桌宠主窗口：一个置顶透明、播放 GIF 的 QLabel"""

    def __init__(self):
        super().__init__()
        if getattr(sys, 'frozen', False):
            self._resource_path = sys._MEIPASS
            self._data_dir = os.path.dirname(sys.executable)
        else:
            self._resource_path = os.path.dirname(os.path.abspath(__file__))
            self._data_dir = self._resource_path

        icon_path = os.path.join(self._resource_path, 'favicon.ico')
        if os.path.exists(icon_path):
            QApplication.instance().setWindowIcon(QIcon(icon_path))

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.gif_files = [os.path.join(self._resource_path, 'gif', name) for name in GIF_NAMES]
        self.current_gif_index = 0
        self.config_file = os.path.join(self._data_dir, '坐标配置.json')
        self.offsets = self.load_offsets()
        self.settings_file = os.path.join(self._data_dir, '设置.json')
        self.load_settings()
        self.gender_file = os.path.join(self._data_dir, GENDER_FILE)
        self.gender = self._load_gender()
        self.scale_factor = 1.0
        self.original_size = None
        self.drag_position = QPoint()
        self.press_position = QPoint()
        self.is_dragging = False
        self.pre_drag_gif_index = 0
        self.drag_threshold = 5
        self.draw_sequence = DRAW_SEQUENCE
        self.draw_index = 0
        self.drawing = False
        self.draw_timer = QTimer(self)
        self.draw_timer.timeout.connect(self.next_draw_step)
        self.special_durations = SPECIAL_DURATIONS
        self.click_recovery_timer = QTimer(self)
        self.click_recovery_timer.setSingleShot(True)
        self.click_recovery_timer.timeout.connect(self.recover_from_click)
        self.click_reaction_options = CLICK_REACTION_OPTIONS
        self.ai_config = self.load_ai_config()
        self._base_prompt = str(self.ai_config.get('system_prompt', ''))
        self.chat_window = None
        self._bubble = None
        self.game_window = None
        self.alarm_window = None
        self.alarm_manager = AlarmManager(self)
        self.movie = QMovie(self.gif_files[self.current_gif_index])
        self.movie.frameChanged.connect(self.update_frame)
        self.setMovie(self.movie)
        self.movie.start()
        self.adjustSize()
        if hasattr(self, '_saved_pos') and hasattr(self, '_saved_scale'):
            self.scale_factor = self._saved_scale
            self.move(self._saved_pos)
            self.update_frame(self.movie.currentFrameNumber())
        else:
            self.move_to_corner()

    def load_offsets(self):
        """加载坐标配置（每个 GIF 的绘制偏移）"""
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {name: {'x': 0, 'y': 0} for name in GIF_NAMES}

    def load_settings(self):
        """加载上次保存的位置和大小"""
        if os.path.exists(self.settings_file):
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._saved_pos = QPoint(data.get('x', 0), data.get('y', 0))
            self._saved_scale = data.get('scale', 1)

    def save_settings(self):
        """保存当前位置和大小"""
        pos = self.pos()
        data = {'x': pos.x(), 'y': pos.y(), 'scale': self.scale_factor}
        with open(self.settings_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def reset_position_and_size(self):
        """重置位置和大小到默认"""
        self.scale_factor = 1
        self.move_to_corner()
        self.update_frame(self.movie.currentFrameNumber())
        self.save_settings()

    def move_to_corner(self):
        """移动到屏幕右下角"""
        screen = QApplication.primaryScreen().geometry()
        x = screen.width() - self.width() - 100
        y = screen.height() - self.height() - 100
        self.move(x, y)

    def update_frame(self, frame_number):
        """更新每一帧：应用坐标偏移并缩放"""
        current_frame = self.movie.currentPixmap()
        if current_frame.isNull():
            return
        if self.original_size is None:
            self.original_size = (current_frame.width(), current_frame.height())
        gif_name = os.path.basename(self.gif_files[self.current_gif_index])
        offset = self.offsets.get(gif_name, {'x': 0, 'y': 0})
        pad = 50
        canvas_w = current_frame.width() + pad * 2
        canvas_h = current_frame.height() + pad * 2
        canvas = QPixmap(canvas_w, canvas_h)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.drawPixmap(pad + offset['x'], pad + offset['y'], current_frame)
        painter.end()
        current_frame = canvas
        if self.scale_factor != 1.0:
            orig_w, orig_h = self.original_size
            new_w = int(orig_w * self.scale_factor)
            new_h = int(orig_h * self.scale_factor)
            scaled_frame = current_frame.scaled(new_w, new_h,
                                                Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation)
            self.setPixmap(scaled_frame)
            self.setFixedSize(new_w, new_h)
        else:
            self.setPixmap(current_frame)
            self.adjustSize()

    def wheelEvent(self, event):
        """鼠标滚轮：缩放桌宠"""
        delta = event.angleDelta().y()
        if delta > 0:
            self.scale_factor *= 1.1
        else:
            self.scale_factor /= 1.1
        self.scale_factor = max(0.5, min(2, self.scale_factor))
        self.update_frame(self.movie.currentFrameNumber())
        event.accept()

    def start_drawing(self):
        """开始画一张画：执行一轮动画序列后停止并弹作品"""
        self.drawing = True
        self.draw_index = 0
        self.switch_to_gif(self.draw_sequence[self.draw_index])
        self.schedule_next_draw_step()

    def schedule_next_draw_step(self):
        """安排下一步的等待时间"""
        current_gif = self.draw_sequence[self.draw_index]
        if current_gif in self.special_durations:
            duration = self.special_durations[current_gif]
        else:
            duration = random.randint(3000, 10000)
        self.draw_timer.start(duration)

    def next_draw_step(self):
        """执行下一步，到达序列末尾后停止"""
        self.draw_index += 1
        if self.draw_index >= len(self.draw_sequence):
            self.drawing = False
            self.draw_timer.stop()
            self.switch_to_gif(0)
            self.show_draw_result()
            return
        self.switch_to_gif(self.draw_sequence[self.draw_index])
        self.schedule_next_draw_step()

    def show_draw_result(self):
        """在桌宠右上角弹出随机画画结果图片"""
        pics_dir = os.path.join(self._resource_path, 'pics')
        if not os.path.exists(pics_dir):
            return
        png_files = glob.glob(os.path.join(pics_dir, '*.png'))
        if not png_files:
            return
        pic_path = random.choice(png_files)
        pet_pos = self.frameGeometry().topRight()
        start_pos = QPoint(pet_pos.x() - 30, pet_pos.y() - 20)
        self._popup = DrawResultPopup(pic_path, start_pos)

    def load_ai_config(self):
        """加载 AI 配置，缺失时优先用 AI配置.json.example 生成，否则用内置模板"""
        path = os.path.join(self._data_dir, AI_CONFIG_FILE)
        cfg = dict(AI_CONFIG_TEMPLATE)
        if not os.path.exists(path):
            for base in (self._data_dir, self._resource_path):
                example = os.path.join(base, AI_CONFIG_FILE + '.example')
                if os.path.exists(example):
                    try:
                        with open(example, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        cfg.update(data)
                    except Exception:
                        pass
                    break
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            return cfg
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            cfg.update(data)
        except Exception:
            pass
        return cfg

    def _load_gender(self):
        """读取使用者性别，未设置返回 None"""
        try:
            with open(self.gender_file, 'r', encoding='utf-8') as f:
                return json.load(f).get('gender')
        except Exception:
            return None

    def _save_gender(self):
        """保存使用者性别"""
        try:
            with open(self.gender_file, 'w', encoding='utf-8') as f:
                json.dump({'gender': self.gender}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def set_gender(self, gender):
        """设置性别并立即生效（更新称谓提示词）"""
        self.gender = gender
        self._save_gender()
        self.ai_config['system_prompt'] = self._build_system_prompt()
        if self.chat_window is not None and self.chat_window._history:
            self.chat_window._history[0]['content'] = self.ai_config['system_prompt']

    def _build_system_prompt(self):
        """根据性别生成完整系统提示词（追加称谓，未设置时叫"共犯"）"""
        base = self._base_prompt
        address = GENDER_ADDRESS.get(self.gender, '共犯')
        return base + '称呼对方为"{}"，绝不叫"主人"。'.format(address)

    def _ask_gender(self):
        """选择/修改性别，决定小蕾米对你的称谓"""
        box = QMessageBox(self)
        box.setWindowTitle('你好呀，共犯' if not self.gender else '更换称呼')
        box.setText('小蕾米想知道共犯是男生还是女生～\n'
                    '男生会叫"{}"，女生会叫"{}"哦。'.format(
                        GENDER_ADDRESS.get('男'), GENDER_ADDRESS.get('女')))
        male = box.addButton('我是男生', QMessageBox.ButtonRole.AcceptRole)
        female = box.addButton('我是女生', QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        if box.clickedButton() is male:
            self.set_gender('男')
        elif box.clickedButton() is female:
            self.set_gender('女')

    def showEvent(self, event):
        """首次使用弹窗确认性别"""
        super().showEvent(event)
        if self.gender is None:
            QTimer.singleShot(0, self._ask_gender)

    def open_chat(self):
        """打开/聚焦 AI 聊天窗口"""
        if self.chat_window is not None:
            self.chat_window.show()
            self.chat_window.raise_()
            self.chat_window.activateWindow()
            return
        self.ai_config = self.load_ai_config()
        if not self.ai_config.get('api_key'):
            QMessageBox.information(self, 'AI 未配置',
                                    '请先编辑程序目录下的 AI配置.json，\n'
                                    '填入 api_key 和 base_url（任意 OpenAI 兼容接口）后重试。')
            return
        self._base_prompt = str(self.ai_config.get('system_prompt', ''))
        self.ai_config['system_prompt'] = self._build_system_prompt()
        self.chat_window = AIChatWindow(self, self.ai_config)
        self.chat_window.show()

    def open_game(self):
        """打开/聚焦小游戏窗口"""
        if self.game_window is not None:
            self.game_window.show()
            self.game_window.raise_()
            self.game_window.activateWindow()
            return
        self.game_window = GameWindow(self)
        self.game_window.show()

    def open_alarm_window(self):
        """打开/聚焦定时提醒窗口"""
        if self.alarm_window is not None:
            self.alarm_window.show()
            self.alarm_window.raise_()
            self.alarm_window.activateWindow()
            return
        self.alarm_window = AlarmWindow(self)
        self.alarm_window.show()

    def set_thinking(self, thinking):
        """AI 请求进行中切到思考表情，结束后恢复"""
        if thinking:
            self._pre_think_index = self.current_gif_index
            self.switch_to_gif(2)
        elif self.current_gif_index == 2:
            if self.drawing:
                self.switch_to_gif(self.draw_sequence[self.draw_index])
            else:
                self.switch_to_gif(self._pre_think_index)

    def show_bubble(self, text):
        """在桌宠上方弹出短气泡，点击打开聊天窗口"""
        text = text.strip()
        if not text:
            return
        if len(text) > 120:
            text = text[:120] + '…'
        if self._bubble is not None:
            try:
                self._bubble.close()
            except Exception:
                pass
        pos = self.frameGeometry().topLeft()
        start_pos = QPoint(pos.x() + 20, pos.y() - 90)
        self._bubble = SpeechBubble(text, start_pos, on_click=self.open_chat)

    def recover_from_click(self):
        """单击互动后恢复"""
        if self.drawing:
            self.switch_to_gif(self.draw_sequence[self.draw_index])
        else:
            self.switch_to_gif(0)

    def mousePressEvent(self, event):
        """鼠标按下事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.press_position = event.globalPosition().toPoint()
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.is_dragging = False
            self.pre_drag_gif_index = self.current_gif_index
            event.accept()

    def mouseMoveEvent(self, event):
        """鼠标移动事件（拖拽）"""
        if event.buttons() & Qt.MouseButton.LeftButton:
            current_pos = event.globalPosition().toPoint()
            distance = (current_pos - self.press_position).manhattanLength()
            if distance > self.drag_threshold:
                if not self.is_dragging:
                    self.is_dragging = True
                self.switch_to_gif(4)
                self.move(current_pos - self.drag_position)
                event.accept()

    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            current_pos = event.globalPosition().toPoint()
            distance = (current_pos - self.press_position).manhattanLength()
            if self.is_dragging:
                self.is_dragging = False
                self.switch_to_gif(self.pre_drag_gif_index)
            elif distance <= self.drag_threshold:
                reaction_gif = random.choice(self.click_reaction_options)
                self.switch_to_gif(reaction_gif)
            self.click_recovery_timer.start(2000)
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.show_context_menu(event.globalPosition().toPoint())

    def mouseDoubleClickEvent(self, event):
        """鼠标双击：切换下一个 GIF"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.switch_to_next_gif()
            event.accept()

    def switch_to_next_gif(self):
        """切换到下一个 GIF"""
        self.current_gif_index = (self.current_gif_index + 1) % len(self.gif_files)
        self.switch_to_gif(self.current_gif_index)

    def show_context_menu(self, position):
        """显示右键菜单"""
        menu = QMenu(self)
        chat_action = QAction('和小蕾米聊天', self)
        chat_action.triggered.connect(self.open_chat)
        menu.addAction(chat_action)
        menu.addSeparator()
        draw_action = QAction('画画', self)
        draw_action.setEnabled(not self.drawing)
        draw_action.triggered.connect(self.start_drawing)
        menu.addAction(draw_action)
        menu.addSeparator()
        game_action = QAction('和小蕾米玩游戏', self)
        game_action.triggered.connect(self.open_game)
        menu.addAction(game_action)
        menu.addSeparator()
        alarm_action = QAction('⏰ 定时提醒', self)
        alarm_action.triggered.connect(self.open_alarm_window)
        menu.addAction(alarm_action)
        menu.addSeparator()
        reset_action = QAction('重置位置和大小', self)
        reset_action.triggered.connect(self.reset_position_and_size)
        menu.addAction(reset_action)
        menu.addSeparator()
        gender_action = QAction('✏️ 更换称呼（性别）', self)
        gender_action.triggered.connect(self._ask_gender)
        menu.addAction(gender_action)
        menu.addSeparator()
        about_action = QAction('作者信息', self)
        about_action.triggered.connect(self.show_about)
        menu.addAction(about_action)
        quit_action = QAction('退出', self)
        quit_action.triggered.connect(self.do_quit)
        menu.addAction(quit_action)
        menu.exec(position)

    def show_about(self):
        """作者信息：展示作者头像图片 + 一句寄语"""
        box = QMessageBox(self)
        box.setWindowTitle('作者信息')
        box.setText('每天都要保持嘴角上扬')
        image_path = ''
        for name in ('作者.png', '作者.jpg', '作者.jpeg'):
            candidate = os.path.join(self._resource_path, name)
            if os.path.exists(candidate):
                image_path = candidate
                break
        if not image_path:
            image_path = os.path.join(self._resource_path, 'favicon.ico')
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(200, 200,
                                       Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                label = QLabel()
                label.setPixmap(pixmap)
                grid = box.layout()
                if grid is not None:
                    grid.addWidget(label, grid.rowCount(), 0, 1, grid.columnCount())
        box.exec()

    def do_quit(self):
        """退出前保存设置"""
        if self.chat_window is not None:
            self.chat_window.close()
        if self.game_window is not None:
            self.game_window.close()
        if self.alarm_window is not None:
            self.alarm_window.close()
        self.save_settings()
        QApplication.quit()

    def switch_to_gif(self, index):
        """切换到指定索引的 GIF"""
        if index != self.current_gif_index:
            self.current_gif_index = index
            self.movie.stop()
            self.movie = QMovie(self.gif_files[self.current_gif_index])
            self.movie.frameChanged.connect(self.update_frame)
            self.setMovie(self.movie)
            self.movie.start()
            self.adjustSize()


if __name__ == '__main__':
    def _excepthook(tp, val, tb):
        # Ctrl+C 正常停止程序，不当作错误记录
        if tp is KeyboardInterrupt:
            return
        try:
            log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '错误日志.txt')
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write('\n[%s]\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
                traceback.print_exception(tp, val, tb, file=f)
        except Exception:
            pass
        traceback.print_exception(tp, val, tb)

    sys.excepthook = _excepthook
    app = QApplication(sys.argv)
    # 桌宠是 Tool 窗口，关闭聊天/游戏窗口时不要退出整个进程
    app.setQuitOnLastWindowClosed(False)
    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec())
