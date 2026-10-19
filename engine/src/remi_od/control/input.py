"""输入注入：ctypes SendInput 键盘（扫描码）与鼠标（前台）。"""

import time
from ctypes import wintypes
import ctypes

user32 = ctypes.windll.user32

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG),
                ('mouseData', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.POINTER(wintypes.ULONG))]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD),
                ('dwExtraInfo', ctypes.POINTER(wintypes.ULONG))]


class _INPUT(ctypes.Structure):
    class _UNION(ctypes.Union):
        _fields_ = [('mi', _MOUSEINPUT), ('ki', _KEYBDINPUT)]

    _fields_ = [('type', wintypes.DWORD), ('union', _UNION)]


# 常用键的扫描码（Set 1）
SCAN_CODES: dict[str, int] = {
    'esc': 0x01, '1': 0x02, '2': 0x03, '3': 0x04, '4': 0x05, '5': 0x06,
    '6': 0x07, '7': 0x08, '8': 0x09, '9': 0x0A, '0': 0x0B,
    'tab': 0x0F, 'q': 0x10, 'w': 0x11, 'e': 0x12, 'r': 0x13, 't': 0x14,
    'y': 0x15, 'u': 0x16, 'i': 0x17, 'o': 0x18, 'p': 0x19,
    'a': 0x1E, 's': 0x1F, 'd': 0x20, 'f': 0x21, 'g': 0x22, 'h': 0x23,
    'j': 0x24, 'k': 0x25, 'l': 0x26, 'z': 0x2C, 'x': 0x2D, 'c': 0x2E,
    'v': 0x2F, 'b': 0x30, 'n': 0x31, 'm': 0x32,
    'enter': 0x1C, 'ctrl': 0x1D, 'shift': 0x2A, 'alt': 0x38, 'space': 0x39,
    'f1': 0x3B, 'f2': 0x3C, 'f3': 0x3D, 'f4': 0x3E,
    'up': 0xC8, 'left': 0xCB, 'right': 0xCD, 'down': 0xD0,
}


def _send_key(scancode: int, up: bool) -> None:
    inp = _INPUT(type=INPUT_KEYBOARD)
    inp.union.ki = _KEYBDINPUT(
        wVk=0, wScan=scancode,
        dwFlags=KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0),
        time=0, dwExtraInfo=None,
    )
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def _send_mouse(flags: int) -> None:
    inp = _INPUT(type=INPUT_MOUSE)
    inp.union.mi = _MOUSEINPUT(0, 0, 0, flags, 0, None)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def key_down(name: str) -> None:
    code = SCAN_CODES[name.lower()]
    _send_key(code, up=False)


def key_up(name: str) -> None:
    code = SCAN_CODES[name.lower()]
    _send_key(code, up=True)


def key_tap(name: str, press_time: float = 0.05) -> None:
    key_down(name)
    time.sleep(press_time)
    key_up(name)


def move_to(x: int, y: int) -> None:
    user32.SetCursorPos(int(x), int(y))


def get_cursor_pos() -> tuple[int, int]:
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)


def click(press_time: float = 0.08) -> None:
    _send_mouse(MOUSEEVENTF_LEFTDOWN)
    time.sleep(press_time)
    _send_mouse(MOUSEEVENTF_LEFTUP)


def click_at(x: int, y: int, press_time: float = 0.08) -> None:
    move_to(x, y)
    time.sleep(0.03)
    click(press_time)


def right_click_at(x: int, y: int, press_time: float = 0.08) -> None:
    move_to(x, y)
    time.sleep(0.03)
    _send_mouse(MOUSEEVENTF_RIGHTDOWN)
    time.sleep(press_time)
    _send_mouse(MOUSEEVENTF_RIGHTUP)


def drag(start: tuple[int, int], end: tuple[int, int], duration: float = 0.3) -> None:
    """从 start 拖到 end（屏幕坐标），带插值让拖动自然。"""
    move_to(*start)
    time.sleep(0.05)
    _send_mouse(MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.05)
    steps = max(2, int(duration / 0.01))
    sx, sy = start
    ex, ey = end
    for i in range(1, steps + 1):
        move_to(sx + (ex - sx) * i // steps, sy + (ey - sy) * i // steps)
        time.sleep(duration / steps)
    time.sleep(0.05)
    _send_mouse(MOUSEEVENTF_LEFTUP)
