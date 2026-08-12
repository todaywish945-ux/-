# -*- coding: utf-8 -*-
"""小游戏：猜数字 / 石头剪刀布 / 打地鼠"""
import random
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal
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


# 吃豆人地图：#=墙 .=豆 o=大力豆 =空地 P=玩家 G=幽灵
PACMAN_MAP = [
    "###################",
    "#.........o.......#",
    "#.#.#.###.#.###.#.#",
    "#o#.#.....#.....#.#",
    "#.#.#.#####.#.#.#.#",
    "#.........#.......#",
    "###.###.###.###.###",
    "#...........#.....#",
    "#.###.#.#####.#.###",
    "#G....#..P....#...#",
    "#.###.#.#####.#.###",
    "#...........#.....#",
    "###.###.###.###.###",
    "#.........#.......#",
    "#.#.#.#####.#.#.#.#",
    "#o#.#.....#.....#.#",
    "#.#.#.###.#.###.#.#",
    "#.........o.......#",
    "###################",
]


class PacmanGame(QWidget):
    """吃豆人：方向键控制蕾米，避开幽灵吃掉所有豆子"""

    def __init__(self, pet, parent=None):
        super().__init__(parent)
        self._pet = pet
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        info = QHBoxLayout()
        self._score_label = QLabel('得分：0', self)
        self._lives_label = QLabel('生命：3', self)
        self._status_label = QLabel('方向键控制移动', self)
        info.addWidget(self._score_label)
        info.addWidget(self._lives_label)
        info.addWidget(self._status_label)
        layout.addLayout(info)

        self._grid_widget = QWidget(self)
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setSpacing(0)
        self._grid.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._grid_widget, 1)

        self._restart_btn = QPushButton('重新开始', self)
        self._restart_btn.clicked.connect(self.start_game)
        layout.addWidget(self._restart_btn)

        self._cols = len(PACMAN_MAP[0])
        self._rows = len(PACMAN_MAP)
        self._cell = 17
        self._init_grid()
        self._player_label = QLabel(self._grid_widget)
        self._player_label.setFixedSize(self._cell, self._cell)
        self._player_movie = QMovie(self._pet.gif_files[1])
        self._player_movie.setScaledSize(QSize(self._cell - 4, self._cell - 4))
        self._player_label.setMovie(self._player_movie)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._move_delay = 200
        self.start_game()

    def _init_grid(self):
        self._cells = []
        for r in range(self._rows):
            row = []
            for c in range(self._cols):
                label = QLabel(self._grid_widget)
                label.setFixedSize(self._cell, self._cell)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._grid.addWidget(label, r, c)
                row.append(label)
            self._cells.append(row)

    def _draw_cell(self, r, c, ch):
        label = self._cells[r][c]
        if ch == '#':
            label.setStyleSheet('background: #c62828;'
                                'border: 2px solid #ff8a80; border-radius: 3px;')
            label.setText('')
        elif ch == '.':
            label.setStyleSheet('background: #1a1a1a; color: #ffd54f; font-weight: bold;')
            label.setText('.')
        elif ch == 'o':
            label.setStyleSheet('background: #1a1a1a; color: #ff9aa2; font-weight: bold;')
            label.setText('●')
        elif ch == 'G':
            label.setStyleSheet('background: #1a1a1a; color: #ff5252; font-weight: bold;')
            label.setText('👻')
        elif ch == 'P':
            label.setStyleSheet('background: #1a1a1a;')
            label.setText('')
        else:
            label.setStyleSheet('background: #1a1a1a;')
            label.setText('')

    def start_game(self):
        self._board = [list(row) for row in PACMAN_MAP]
        for r in range(self._rows):
            for c in range(self._cols):
                if self._board[r][c] == 'P':
                    self._pac_r, self._pac_c = r, c
                    self._board[r][c] = ' '
                elif self._board[r][c] == 'G':
                    self._ghost_r, self._ghost_c = r, c
                    self._board[r][c] = ' '
        self._score = 0
        self._lives = 3
        self._running = True
        self._dir_r, self._dir_c = 0, -1
        self._status_label.setText('方向键控制移动')
        self._timer.start(self._move_delay)
        self._refresh()

    def _tick(self):
        """幽灵每 tick 追击一次，玩家不动"""
        if not self._running:
            return
        self._move_ghost()
        self._check_win()
        self._refresh()

    def _step(self, direction):
        """玩家走一格：移动 + 吃豆 + 幽灵追击"""
        if not self._running:
            return
        self._try_move(direction)
        if self._board[self._pac_r][self._pac_c] == '.':
            self._board[self._pac_r][self._pac_c] = ' '
            self._score += 10
        elif self._board[self._pac_r][self._pac_c] == 'o':
            self._board[self._pac_r][self._pac_c] = ' '
            self._score += 50
        self._move_ghost()
        self._check_win()
        self._refresh()

    def _try_move(self, direction):
        dr, dc = direction
        nr, nc = self._pac_r + dr, self._pac_c + dc
        if self._board[nr][nc] == '#':
            return
        self._dir_r, self._dir_c = dr, dc
        self._pac_r, self._pac_c = nr, nc

    def _move_ghost(self):
        # 幽灵简单追击：优先朝玩家方向移动
        best = None
        best_dist = None
        for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nr, nc = self._ghost_r + dr, self._ghost_c + dc
            if self._board[nr][nc] == '#':
                continue
            dist = abs(nr - self._pac_r) + abs(nc - self._pac_c)
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best = (dr, dc)
        if best is not None:
            self._ghost_r += best[0]
            self._ghost_c += best[1]
        if (self._ghost_r, self._ghost_c) == (self._pac_r, self._pac_c):
            self._lives -= 1
            self._lives_label.setText('生命：%d' % self._lives)
            if self._lives <= 0:
                self._running = False
                self._timer.stop()
                self._status_label.setText('游戏结束！得分 %d' % self._score)
                self._pet.switch_to_gif(2)
            else:
                self._reset_positions()

    def _reset_positions(self):
        for r in range(self._rows):
            for c in range(self._cols):
                if self._board[r][c] in ('P', 'G'):
                    self._board[r][c] = ' '
        self._pac_r, self._pac_c = 9, 10
        self._ghost_r, self._ghost_c = 9, 1

    def _check_win(self):
        remaining = sum(row.count('.') + row.count('o') for row in self._board)
        if remaining == 0:
            self._running = False
            self._timer.stop()
            self._status_label.setText('🎉 通关啦！得分 %d' % self._score)
            self._pet.switch_to_gif(1)

    def _refresh(self):
        for r in range(self._rows):
            for c in range(self._cols):
                ch = self._board[r][c]
                if (r, c) == (self._ghost_r, self._ghost_c):
                    ch = 'G'
                self._draw_cell(r, c, ch)
        self._grid.addWidget(self._player_label, self._pac_r, self._pac_c)
        self._player_label.raise_()
        self._player_movie.start()
        self._score_label.setText('得分：%d' % self._score)

    def keyPressEvent(self, event):
        k = event.key()
        if k == Qt.Key.Key_Up:
            self._step((-1, 0))
        elif k == Qt.Key.Key_Down:
            self._step((1, 0))
        elif k == Qt.Key.Key_Left:
            self._step((0, -1))
        elif k == Qt.Key.Key_Right:
            self._step((0, 1))
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        self.setFocus()
        super().mousePressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self.setFocus()


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
                         ('打地鼠', self.show_mole), ('吃豆人', self.show_pacman)]:
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
        QTimer.singleShot(0, game.setFocus)

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

    def show_pacman(self):
        self._show(self._get('pacman', lambda: PacmanGame(self._pet)))

    def closeEvent(self, event):
        self._pet.game_window = None
        event.accept()
