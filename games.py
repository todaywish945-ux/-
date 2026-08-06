# -*- coding: utf-8 -*-
"""小游戏：猜数字 / 石头剪刀布 / 打地鼠"""
import random
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QMovie
from PyQt6.QtWidgets import (QWidget, QLabel, QPushButton, QLineEdit,
                             QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget)


# 石头剪刀布：返回 1=我赢 0=平 -1=蕾米赢
def rps_winner(me, opponent):
    if me == opponent:
        return 0
    wins = {'石头': '剪刀', '剪刀': '布', '布': '石头'}
    return 1 if wins[me] == opponent else -1


class GuessGame(QWidget):
    """猜数字：1~100，蕾米出题"""

    def __init__(self, pet, parent=None):
        super().__init__(parent)
        self._pet = pet
        self.new_round()
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        tip = QLabel('我心里想了个 1~100 的数字，来猜猜看！', self)
        tip.setWordWrap(True)
        layout.addWidget(tip)
        row = QHBoxLayout()
        self._input = QLineEdit(self)
        self._input.setPlaceholderText('输入数字')
        self._input.returnPressed.connect(self._guess)
        row.addWidget(self._input)
        btn = QPushButton('猜', self)
        btn.clicked.connect(self._guess)
        row.addWidget(btn)
        layout.addLayout(row)
        self._hint = QLabel('', self)
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)
        restart = QPushButton('重新开始', self)
        restart.clicked.connect(self.new_round)
        layout.addWidget(restart)
        layout.addStretch()

    def new_round(self):
        self._secret = random.randint(1, 100)
        self._tries = 0

    def _guess(self):
        try:
            g = int(self._input.text().strip())
        except ValueError:
            self._hint.setText('请输入一个数字哦～')
            return
        self._tries += 1
        if g == self._secret:
            self._hint.setText('🎉 猜对啦！就是 %d，用了 %d 次！' % (self._secret, self._tries))
            self._pet.switch_to_gif(1)
            self.new_round()
        elif g < self._secret:
            self._hint.setText('小了哦，再大一点～')
        else:
            self._hint.setText('大了哦，再小一点～')


class RPSGame(QWidget):
    """石头剪刀布：计分对战"""

    def __init__(self, pet, parent=None):
        super().__init__(parent)
        self._pet = pet
        self._score_me = 0
        self._score_pet = 0
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        tip = QLabel('和蕾米石头剪刀布！', self)
        layout.addWidget(tip)
        row = QHBoxLayout()
        for name in ['石头', '剪刀', '布']:
            b = QPushButton(name, self)
            b.clicked.connect(lambda _=False, n=name: self._play(n))
            row.addWidget(b)
        layout.addLayout(row)
        self._result = QLabel('选择你的出拳～', self)
        self._result.setWordWrap(True)
        layout.addWidget(self._result)
        self._score = QLabel('蕾米 0 : 0 我', self)
        layout.addWidget(self._score)
        layout.addStretch()

    def _play(self, me):
        pet_pick = random.choice(['石头', '剪刀', '布'])
        r = rps_winner(me, pet_pick)
        text = '你出%s，蕾米出%s。' % (me, pet_pick)
        if r == 1:
            self._score_me += 1
            text += '你赢啦！'
            self._pet.switch_to_gif(2)
        elif r == -1:
            self._score_pet += 1
            text += '蕾米赢啦！'
            self._pet.switch_to_gif(1)
        else:
            text += '平手～'
            self._pet.switch_to_gif(0)
        self._result.setText(text)
        self._score.setText('蕾米 %d : %d 我' % (self._score_pet, self._score_me))


class _MoleCell(QLabel):
    """打地鼠格子：点击触发信号，显示小蕾米待机动画"""

    clicked = pyqtSignal(int)

    def __init__(self, idx, parent=None):
        super().__init__(parent)
        self._idx = idx
        self._movie = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(110, 110)
        self.setStyleSheet('background: #fff0f6;'
                           'border: 2px solid #ff8fbf; border-radius: 12px;')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._idx)
        event.accept()

    def show_mole(self, gif_path):
        self.clear()
        if self._movie is not None:
            self._movie.stop()
        self._movie = QMovie(gif_path)
        self._movie.frameChanged.connect(self._update_frame)
        self._movie.start()

    def _update_frame(self, _frame):
        pm = self._movie.currentPixmap()
        if pm.isNull():
            return
        scaled = pm.scaled(self.width() - 12, self.height() - 12,
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(scaled)

    def hide_mole(self):
        if self._movie is not None:
            self._movie.stop()
            self._movie = None
        self.clear()


class MoleGame(QWidget):
    """打地鼠：30 秒内点击冒头的小蕾米加分"""

    def __init__(self, pet, parent=None):
        super().__init__(parent)
        self._pet = pet
        self._gif_path = pet.gif_files[0]
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        top = QHBoxLayout()
        self._score_label = QLabel('得分：0', self)
        self._time_label = QLabel('时间：30', self)
        top.addWidget(self._score_label)
        top.addWidget(self._time_label)
        layout.addLayout(top)
        grid = QGridLayout()
        grid.setSpacing(8)
        self._cells = []
        for i in range(3):
            for j in range(3):
                cell = _MoleCell(i * 3 + j)
                cell.clicked.connect(self._hit)
                grid.addWidget(cell, i, j)
                self._cells.append(cell)
        layout.addLayout(grid)
        self._status = QLabel('点"开始"，拍打冒头的小蕾米！', self)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._start_btn = QPushButton('开始', self)
        self._start_btn.clicked.connect(self.start_game)
        layout.addWidget(self._start_btn)
        self._mole_timer = QTimer(self)
        self._mole_timer.timeout.connect(self._spawn)
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick_time)
        self._cur = None
        self._score = 0
        self._time = 30
        self._running = False

    def start_game(self):
        self._score = 0
        self._time = 30
        self._running = True
        self._start_btn.setEnabled(False)
        self._status.setText('快拍！')
        self._update_labels()
        self._mole_timer.start(900)
        self._tick_timer.start(1000)

    def _spawn(self):
        if not self._running:
            return
        if self._cur is not None:
            self._cells[self._cur].hide_mole()
        available = [i for i in range(9) if i != self._cur]
        self._cur = random.choice(available)
        self._cells[self._cur].show_mole(self._gif_path)
        self._pet.switch_to_gif(4)

    def _hit(self, idx):
        if not self._running:
            return
        if idx == self._cur:
            self._score += 1
            self._cells[idx].hide_mole()
            self._cur = None
            self._pet.switch_to_gif(1)
        else:
            self._score = max(0, self._score - 1)
        self._update_labels()

    def _tick_time(self):
        if not self._running:
            return
        self._time -= 1
        if self._time <= 0:
            self._time = 0
            self._end()
        self._update_labels()

    def _end(self):
        self._running = False
        self._mole_timer.stop()
        self._tick_timer.stop()
        if self._cur is not None:
            self._cells[self._cur].hide_mole()
            self._cur = None
        self._start_btn.setEnabled(True)
        self._status.setText('游戏结束！得分 %d' % self._score)
        self._pet.switch_to_gif(1)

    def _update_labels(self):
        self._score_label.setText('得分：%d' % self._score)
        self._time_label.setText('时间：%d' % self._time)


class GameWindow(QWidget):
    """和小蕾米玩游戏：多个小游戏切换"""

    def __init__(self, pet, parent=None):
        super().__init__(parent)
        self._pet = pet
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle('🎮 和小蕾米玩游戏')
        self.setFixedSize(420, 500)
        self.setStyleSheet('font-size: 13px; background: #ffe4f1; color: black;')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        title = QLabel('选择一个小游戏，和蕾米一起玩吧～', self)
        title.setStyleSheet('color: black; font-weight: bold;')
        layout.addWidget(title)
        btn_row = QHBoxLayout()
        for name, fn in [('猜数字', self.show_guess), ('石头剪刀布', self.show_rps),
                         ('打地鼠', self.show_mole)]:
            b = QPushButton(name, self)
            b.setStyleSheet('color: black;')
            b.clicked.connect(lambda _=False, f=fn: f())
            btn_row.addWidget(b)
        layout.addLayout(btn_row)
        self._stack = QStackedWidget(self)
        layout.addWidget(self._stack, 1)
        self._games = {}
        self._current = None
        self.show_guess()

    def _show(self, game):
        if self._stack.indexOf(game) == -1:
            self._stack.addWidget(game)
        self._stack.setCurrentWidget(game)
        self._current = game

    def _get(self, key, builder):
        if key not in self._games:
            self._games[key] = builder()
        return self._games[key]

    def show_guess(self):
        self._show(self._get('guess', lambda: GuessGame(self._pet)))

    def show_rps(self):
        self._show(self._get('rps', lambda: RPSGame(self._pet)))

    def show_mole(self):
        self._show(self._get('mole', lambda: MoleGame(self._pet)))

    def closeEvent(self, event):
        self._pet.game_window = None
        event.accept()
