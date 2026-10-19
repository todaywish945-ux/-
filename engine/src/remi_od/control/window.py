"""窗口查找与前台化（按精确标题匹配，避免 MOD 管理器等窗口抢匹配）。"""

import ctypes

import win32con
import win32gui

GAME_WINDOW_TITLE = '绝区零'


def find_window(exact_title: str) -> int | None:
    """按标题精确匹配可见顶层窗口，找不到返回 None。"""
    found: list[int] = []

    def _callback(hwnd: int, _: object) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        if win32gui.GetWindowText(hwnd) == exact_title:
            found.append(hwnd)

    win32gui.EnumWindows(_callback, None)
    return found[0] if found else None


def find_window_by_keyword(keyword: str) -> int | None:
    """调试用：按标题关键字找第一个可见顶层窗口。"""
    found: list[int] = []

    def _callback(hwnd: int, _: object) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        if keyword in win32gui.GetWindowText(hwnd):
            found.append(hwnd)

    win32gui.EnumWindows(_callback, None)
    return found[0] if found else None


def client_size(hwnd: int) -> tuple[int, int]:
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    return right - left, bottom - top


def client_left_top(hwnd: int) -> tuple[int, int]:
    """客户区左上角的屏幕坐标。"""
    return win32gui.ClientToScreen(hwnd, (0, 0))


def window_title(hwnd: int) -> str:
    return win32gui.GetWindowText(hwnd)


def is_foreground(hwnd: int) -> bool:
    return win32gui.GetForegroundWindow() == hwnd


def set_foreground(hwnd: int) -> None:
    """把窗口带到前台。先最小化还原 + ALT 键绕过 Windows 前台锁。"""
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    user32 = ctypes.windll.user32
    user32.keybd_event(0x12, 0, 0, 0)  # ALT down
    user32.keybd_event(0x12, 0, 2, 0)  # ALT up
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
