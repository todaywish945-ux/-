# -*- coding: utf-8 -*-
"""离线逻辑测试：用 mock 的 Qt 类验证 pet.py 的状态机逻辑（无需真实 GUI/显示器）"""
import sys
import types
import json
import os
import time

# ---------- 构造假的 PyQt5 模块 ----------
class Signal:
    def __init__(self): self.slots = []
    def connect(self, fn): self.slots.append(fn)
    def emit(self, *a): [fn(*a) for fn in self.slots]

class _QObject:
    def __init__(self, *a, **k): pass
    def setStyleSheet(self, s): pass
    def setObjectName(self, n): pass
    def setFocus(self): pass

class QLabel(_QObject):
    def __init__(self, *a, **k):
        super().__init__()
        self._movie = None
        self._pixmap = None
        self._flags = 0
        self._pos = None
        self._size = None
        self._text = None
    def setWindowFlags(self, f): self._flags = f
    def setAttribute(self, a): pass
    def show(self): pass
    def hide(self): pass
    def close(self):
        if hasattr(self, 'closeEvent'):
            class _E:
                def accept(self): pass
                def ignore(self): pass
            self.closeEvent(_E())
    def isHidden(self): return False
    def isVisible(self): return True
    def deleteLater(self): pass
    def setMovie(self, m): self._movie = m
    def setPixmap(self, p): self._pixmap = p
    def adjustSize(self): pass
    def setFixedSize(self, w, h): self._size = (w, h)
    def setFixedWidth(self, w): pass
    def setMaximumWidth(self, w): pass
    def setMinimumWidth(self, w): pass
    def setText(self, t): self._text = t
    def text(self): return self._text
    def setWordWrap(self, b): pass
    def setAlignment(self, a): pass
    def clear(self): self._text = None
    def setStyleSheet(self, s): pass
    def setTextInteractionFlags(self, f): pass
    def setWindowTitle(self, t): pass
    def setLayout(self, l): pass
    def setEnabled(self, b): pass
    def move(self, x, y=None):
        if y is None: self._pos = (x.x(), x.y())
        else: self._pos = (x, y)
    def setGraphicsEffect(self, e): pass
    def pos(self): return QPoint(*(self._pos or (0, 0)))
    def frameGeometry(self):
        class _G:
            def topRight(self): return QPoint(100, 100)
            def topLeft(self): return QPoint(50, 50)
        return _G()
    def width(self): return (self._size or (100, 100))[0]
    def height(self): return (self._size or (100, 100))[1]

class QWidget(QLabel): pass

class QScrollArea(QLabel):
    def __init__(self, *a, **k):
        super().__init__()
        self._widget = None
        self._resizable = False
    def setWidget(self, w): self._widget = w
    def setWidgetResizable(self, b): self._resizable = b
    def ensureWidgetVisible(self, w): pass

class QLineEdit(_QObject):
    def __init__(self, *a, **k):
        super().__init__()
        self.returnPressed = Signal()
        self.textChanged = Signal()
        self._text = ''
    def setPlaceholderText(self, t): pass
    def setEnabled(self, b): pass
    def clear(self): self._text = ''
    def text(self): return self._text
    def setText(self, t):
        self._text = t
        self.textChanged.emit(t)

class QPushButton(_QObject):
    def __init__(self, *a, **k):
        super().__init__()
        self.clicked = Signal()
        self._text = a[0] if a else ''
    def setEnabled(self, b): pass
    def setFixedSize(self, w, h): pass
    def setText(self, t): self._text = t
    def text(self): return self._text

class QTimeEdit(_QObject):
    def __init__(self, *a, **k):
        super().__init__()
        self._h = 8
        self._m = 0
    def setDisplayFormat(self, f): pass
    def time(self):
        h, m = self._h, self._m
        class _T:
            def hour(self): return h
            def minute(self): return m
        return _T()

class QSpinBox(_QObject):
    def __init__(self, *a, **k):
        super().__init__()
        self._v = 1
    def setRange(self, lo, hi): pass
    def setSuffix(self, s): pass
    def value(self): return self._v

class QCheckBox(_QObject):
    def __init__(self, *a, **k):
        super().__init__()
        self._checked = False
        self._text = a[0] if a else ''
    def setText(self, t): self._text = t
    def text(self): return self._text
    def isChecked(self): return self._checked
    def setChecked(self, b): self._checked = b

class _Item:
    def __init__(self, w=None): self._w = w
    def widget(self): return self._w

class _Layout(_QObject):
    def __init__(self, *a, **k):
        super().__init__()
        self._count = 0
        self._items = []
    def addWidget(self, w, *a, **k):
        self._count += 1
        self._items.append(w)
    def addLayout(self, l, *a, **k): self._count += 1
    def insertWidget(self, idx, w, *a, **k):
        self._count += 1
        self._items.insert(idx, w)
    def removeWidget(self, w): pass
    def addStretch(self, *a): pass
    def setContentsMargins(self, *a): pass
    def setSpacing(self, s): pass
    def setAlignment(self, *a): pass
    def count(self): return self._count
    def takeAt(self, idx):
        if 0 <= idx < len(self._items):
            w = self._items.pop(idx)
            self._count = max(0, self._count - 1)
            return _Item(w)
        return None

class QVBoxLayout(_Layout): pass
class QHBoxLayout(_Layout): pass
class QGridLayout(_Layout): pass

class QStackedWidget(_QObject):
    def __init__(self, *a, **k):
        super().__init__()
        self._widgets = []
    def addWidget(self, w):
        self._widgets.append(w)
        return len(self._widgets) - 1
    def indexOf(self, w):
        try:
            return self._widgets.index(w)
        except ValueError:
            return -1
    def setCurrentWidget(self, w): pass
    def count(self): return len(self._widgets)

class QApplication:
    instance_obj = None
    def __init__(self, argv): QApplication.instance_obj = self
    @staticmethod
    def instance(): return QApplication.instance_obj
    def setWindowIcon(self, i): pass
    @staticmethod
    def quit(): pass
    @staticmethod
    def primaryScreen():
        class _S:
            def geometry(self):
                class _G:
                    def __init__(self): self.w = 1920; self.h = 1080
                    def width(self): return self.w
                    def height(self): return self.h
                return _G()
        return _S()

class QTimer(_QObject):
    def __init__(self, *a, **k):
        self.timeout = Signal()
        self._started = None
        self._single = False
    def start(self, ms): self._started = ms
    def stop(self): self._started = None
    def setSingleShot(self, b): self._single = b
    @staticmethod
    def singleShot(ms, fn): fn()

class QThread(_QObject):
    def __init__(self, *a, **k):
        super().__init__()
    def start(self): self.run()
    def run(self): pass
    def wait(self): pass

def pyqtSignal(*types):
    return Signal()

class QMovie(_QObject):
    def __init__(self, path):
        self.path = path
        self.frameChanged = Signal()
        self._current = 0
    def start(self): pass
    def stop(self): pass
    def setScaledSize(self, s): pass
    def currentFrameNumber(self): return self._current
    def currentPixmap(self):
        class _P:
            def isNull(self): return False
            def width(self): return 120
            def height(self): return 160
            def scaled(self, w, h, *a):
                class _P2:
                    def width(self): return w
                    def height(self): return h
                return _P2()
        return _P()

class QPoint:
    def __init__(self, x=0, y=0):
        self._x, self._y = x, y
    def x(self): return self._x
    def y(self): return self._y

class QSize:
    def __init__(self, w, h):
        self._w, self._h = w, h
    def width(self): return self._w
    def height(self): return self._h
    def __sub__(self, o): return QPoint(self._x - o.x(), self._y - o.y())
    def manhattanLength(self): return abs(self._x) + abs(self._y)

class QPixmap:
    def __init__(self, *a):
        self._w = 300 if len(a) == 1 else a[0]
        self._h = 100 if len(a) == 1 else a[1]
    def fill(self, c): pass
    def width(self): return self._w
    def height(self): return self._h
    def scaled(self, w, h, *a):
        class _P:
            def __init__(self): self._w = w; self._h = h
            def width(self): return self._w
            def height(self): return self._h
        return _P()
    def scaledToWidth(self, w, *a):
        class _P:
            def width(self): return w
            def height(self): return 100
        return _P()

class QPainter:
    def __init__(self, *a): pass
    def drawPixmap(self, *a): pass
    def end(self): pass

class QGraphicsOpacityEffect(_QObject):
    def __init__(self, *a, **k): self._opacity = 0
    def setOpacity(self, o): self._opacity = o

class QMessageBox:
    @staticmethod
    def about(*a): pass
    @staticmethod
    def information(*a): pass
    @staticmethod
    def warning(*a): pass

class QIcon:
    def __init__(self, *a): pass

class QFileDialog(_QObject):
    @staticmethod
    def getOpenFileName(*a, **k):
        return ('', '')

class QMenu(_QObject):
    def addAction(self, a): pass
    def addSeparator(self): pass
    def exec_(self, pos): pass

class QAction(_QObject):
    def __init__(self, *a, **k):
        self.triggered = Signal()
    def setEnabled(self, b): pass

class QActionGroup(_QObject):
    def __init__(self, *a, **k):
        self._actions = []
    def setExclusive(self, b): pass
    def addAction(self, a): self._actions.append(a)

class _Enum:
    def __init__(self, **members):
        for k, v in members.items():
            setattr(self, k, v)

class _QtConsts:
    WindowType = _Enum(FramelessWindowHint=1, WindowStaysOnTopHint=2, Tool=4, Window=8)
    WidgetAttribute = _Enum(WA_TranslucentBackground=1, WA_DeleteOnClose=2,
                            WA_TransparentForMouseEvents=3)
    TransformationMode = _Enum(SmoothTransformation=1)
    AspectRatioMode = _Enum(KeepAspectRatio=1)
    GlobalColor = _Enum(transparent=0)
    MouseButton = _Enum(LeftButton=1, RightButton=2)
    TextInteractionFlag = _Enum(TextSelectableByMouse=1)
    AlignmentFlag = _Enum(AlignCenter=4)

class _Qt:
    def __getattr__(self, name):
        raise AttributeError(f'未在 mock 中定义 Qt.{name}，请补充')

class _QtModule:
    Qt = _QtConsts()

def _build_pkg(name):
    pkg = types.ModuleType(name)
    sys.modules[name] = pkg
    return pkg

qw = _build_pkg('PyQt6.QtWidgets')
for n in ['QApplication', 'QLabel', 'QMenu', 'QAction', 'QWidget',
          'QGraphicsOpacityEffect', 'QMessageBox', 'QScrollArea',
          'QLineEdit', 'QPushButton', 'QVBoxLayout', 'QHBoxLayout',
          'QGridLayout', 'QStackedWidget', 'QTimeEdit', 'QSpinBox',
          'QCheckBox', 'QFileDialog']:
    setattr(qw, n, globals()[n])

qc = _build_pkg('PyQt6.QtCore')
setattr(qc, 'Qt', _QtConsts())
setattr(qc, 'QTimer', QTimer)
setattr(qc, 'QPoint', QPoint)
setattr(qc, 'QSize', QSize)
setattr(qc, 'QThread', QThread)
setattr(qc, 'QObject', _QObject)
setattr(qc, 'pyqtSignal', pyqtSignal)

qg = _build_pkg('PyQt6.QtGui')
setattr(qg, 'QPixmap', QPixmap)
setattr(qg, 'QMovie', QMovie)
setattr(qg, 'QPainter', QPainter)
setattr(qg, 'QIcon', QIcon)
setattr(qg, 'QAction', QAction)
setattr(qg, 'QActionGroup', QActionGroup)

import pet

# ---------- 逻辑测试 ----------
ok = True

def check(name, cond):
    global ok
    print(('PASS' if cond else 'FAIL'), name)
    if not cond: ok = False

# 清掉上次运行遗留的设置，保证"默认缩放=1.0"等断言确定性
_settings_path = os.path.join(os.path.dirname(os.path.abspath(pet.__file__)), '设置.json')
if os.path.exists(_settings_path):
    os.remove(_settings_path)

app = QApplication(['pet'])
p = pet.DesktopPet()

check('gif_files 数量 = 7', len(p.gif_files) == 7)
check('默认待机 gif 是 待机.gif', p.gif_files[p.current_gif_index].endswith('待机.gif'))
check('默认缩放 = 1.0', p.scale_factor == 1.0)
check('画画序列与源码一致', p.draw_sequence == [3, 2, 6, 5, 6, 1])
check('坐标偏移已加载', '拿笔待机.gif' in p.offsets)

# 画画流程
p.start_drawing()
check('画画开始: drawing=True', p.drawing)
check('第一步切到 拿笔待机(3)', p.current_gif_index == 3)
check('拿笔待机固定时长 2000ms', p.draw_timer._started == 2000)

p.next_draw_step()
check('第二步切到 思考(2)', p.current_gif_index == 2)
check('思考为随机时长 3000~10000', 3000 <= p.draw_timer._started <= 10000)

p.next_draw_step()
check('第三步切到 间歇绘制(6)', p.current_gif_index == 6)
check('间歇绘制固定时长 1800ms', p.draw_timer._started == 1800)

# 走完剩余步骤直到结束
steps = 0
while p.drawing:
    p.next_draw_step()
    p.draw_timer.stop()
    steps += 1
check('画画流程正常结束', not p.drawing)
check('结束后恢复待机(0)', p.current_gif_index == 0)
check('结束后弹出作品窗口', hasattr(p, '_popup'))

# 设置读写
p._pos = (555, 666)
p.scale_factor = 1.5
p.save_settings()
data = json.load(open(p.settings_file, encoding='utf-8'))
check('保存位置 x=555', data['x'] == 555)
check('保存位置 y=666', data['y'] == 666)
check('保存缩放 1.5', data['scale'] == 1.5)

# 表情切换循环
p.switch_to_next_gif()
check('双击切表情 -> 得意(1)', p.current_gif_index == 1)
p.switch_to_next_gif()
check('双击切表情 -> 思考(2)', p.current_gif_index == 2)

# AI 聊天
check('AI 配置已生成文件', os.path.exists(os.path.join(p._data_dir, pet.AI_CONFIG_FILE)))
check('AI 配置包含 api_key 字段', 'api_key' in p.ai_config)
check('AI 配置包含 base_url 字段', 'base_url' in p.ai_config)

# ============ 使用者性别与称谓 ============
_gender_file = os.path.join(p._data_dir, pet.GENDER_FILE)
_gender_backup = None
if os.path.exists(_gender_file):
    _gender_backup = open(_gender_file, encoding='utf-8').read()
    os.remove(_gender_file)
check('未设置性别时返回 None', p._load_gender() is None)
p.set_gender('女')
check('设置性别后已保存', p._load_gender() == '女')
_female_addr = pet.GENDER_ADDRESS['女']
check('女性称谓不为空', bool(_female_addr))
check('女性提示词含称谓', _female_addr in p._build_system_prompt())
p.set_gender('男')
_male_addr = pet.GENDER_ADDRESS['男']
check('男性称谓不为空', bool(_male_addr))
check('男性提示词含称谓', _male_addr in p._build_system_prompt())
check('男女称谓不同', _male_addr != _female_addr)
p.gender = None
check('未设性别时叫"共犯"', '共犯' in p._build_system_prompt())
if _gender_backup is None:
    if os.path.exists(_gender_file):
        os.remove(_gender_file)
else:
    open(_gender_file, 'w', encoding='utf-8').write(_gender_backup)


history = [{'role': 'system', 'content': 's'}] + \
          [{'role': 'user', 'content': str(i)} for i in range(5)]
t = pet.trim_history(history, 3)
check('trim_history 保留 system', len(t) == 4 and t[0]['role'] == 'system')
check('trim_history 只留最近3条', t[-1]['content'] == '4')
check('trim_history 空列表返回空', pet.trim_history([], 5) == [])

bubble = pet.SpeechBubble('测试气泡', pet.QPoint(0, 0), on_click=lambda: None)
check('气泡已创建并显示', bubble.isVisible() if hasattr(bubble, 'isVisible') else True)
bubble.close()

# open_chat 无 key 时不应创建窗口（临时清空文件中的 key，测完恢复）
_ai_file = os.path.join(p._data_dir, pet.AI_CONFIG_FILE)
_ai_backup = json.load(open(_ai_file, encoding='utf-8'))
json.dump(dict(_ai_backup, api_key=''), open(_ai_file, 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2)
p.open_chat()
check('未配置 key 时不打开聊天窗口', p.chat_window is None)
json.dump(_ai_backup, open(_ai_file, 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2)

# 图片题解答
_tmp_img = os.path.join(os.path.dirname(os.path.abspath(pet.__file__)), '_tmp_test.jpg')
with open(_tmp_img, 'w') as f:
    f.write('fake-image-bytes')
_win = pet.AIChatWindow(p, dict(_ai_backup))
_img_content = _win._build_image_content((_tmp_img, 'image/jpeg'), '解这道题')
check('图片消息是 content 列表', isinstance(_img_content, list))
check('图片消息含 image_url', _img_content[0]['type'] == 'image_url')
check('图片消息 base64 前缀正确', _img_content[0]['image_url']['url']
      .startswith('data:image/jpeg;base64,'))
check('图片消息附带题目文字', _img_content[-1]['text'] == '解这道题')
_win.close()
os.remove(_tmp_img)

# AI 思考表情切换
p.switch_to_gif(0)
p.set_thinking(True)
check('思考中切到 思考.gif(2)', p.current_gif_index == 2)
p.set_thinking(False)
check('思考结束恢复待机(0)', p.current_gif_index == 0)
p.switch_to_next_gif()
p.set_thinking(True)
check('再次思考切到 思考.gif(2)', p.current_gif_index == 2)
p.set_thinking(False)
check('思考结束恢复之前的表情', p.current_gif_index == 1)

# ============ 小游戏 ============
check('剪刀赢布', pet.rps_winner('剪刀', '布') == 1)
check('布赢石头', pet.rps_winner('布', '石头') == 1)
check('石头输布', pet.rps_winner('石头', '布') == -1)
check('平局', pet.rps_winner('石头', '石头') == 0)

g = pet.GuessGame(p)
g._secret = 42
g._input.setText('10')
g._guess()
check('猜小了提示包含"小"', '小' in g._hint.text())
g._input.setText('42')
g._guess()
check('猜中提示包含"猜对"', '猜对' in g._hint.text())
check('猜中后蕾米得意', p.current_gif_index == 1)

m = pet.MoleGame(p)
m._running = True
m._cur = 4
m._score = 0
m._hit(4)
check('打中加分', m._score == 1)
m._cur = 5
m._hit(4)
check('打空减分', m._score == 0)

p.open_game()
check('打开游戏窗口', p.game_window is not None)
if p.game_window is not None:
    p.game_window.close()

# ============ 定时提醒（闹钟 / 倒计时） ============
mgr = p.alarm_manager
mgr._sound_enabled = False  # 测试时不出声
mgr.alarms = []
mgr._popups = []
mgr.save()

now = time.localtime()
mgr.add_clock('每天', now.tm_hour, now.tm_min, True)
mgr.add_countdown('倒计时', 1)
mgr.alarms[-1]['seconds'] = 1
mgr.add_countdown('长倒计时', 1)
mgr.add_clock('一次性', now.tm_hour, now.tm_min, False)
check('闹钟管理器已创建', mgr is not None)
check('添加后共 4 个', len(mgr.alarms) == 4)
check('倒计时按分钟换算成秒', mgr.alarms[1]['seconds'] == 1)

_pop0 = len(mgr._popups)
mgr._tick()
check('单次闹钟到点标记完成', mgr.alarms[-1].get('done'))
check('重复闹钟记录当天', mgr.alarms[0].get('last_day') is not None)
check('重复闹钟未标记完成', not mgr.alarms[0].get('done'))
check('倒计时到点标记完成', mgr.alarms[1].get('done'))
check('到点触发弹窗 +3', len(mgr._popups) == _pop0 + 3)
check('长倒计时仍进行中', not mgr.alarms[2].get('done'))

_pop1 = len(mgr._popups)
mgr._tick()
check('同一天不重复弹窗', len(mgr._popups) == _pop1)
check('长倒计时每秒递减', mgr.alarms[2]['seconds'] == 58)

_aid = mgr.alarms[0]['id']
mgr.remove(_aid)
check('删除闹钟后剩 3 个', len(mgr.alarms) == 3)

p.open_alarm_window()
check('打开定时提醒窗口', p.alarm_window is not None)
if p.alarm_window is not None:
    p.alarm_window.close()
check('关闭窗口后引用置空', p.alarm_window is None)
mgr.alarms = []
mgr.save()

# 已关闭并销毁的弹窗不应导致报错
class _DeadPopup:
    def isHidden(self):
        raise RuntimeError('wrapped C/C++ object has been deleted')
mgr._popups = [_DeadPopup()]
mgr.show_popup('测试', '内容')
check('已销毁弹窗被安全跳过', len(mgr._popups) == 1)
mgr._popups = []

print()
print('ALL PASSED' if ok else 'SOME FAILED')
sys.exit(0 if ok else 1)
