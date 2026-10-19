"""控制器实测：拉起记事本 → 找窗口 → PrintWindow 截图 → 关闭。

需要交互式桌面会话；无桌面（如 CI）自动跳过。
"""

import subprocess
import time

import numpy as np
import pytest

from remi_od.control import window as win_ctl
from remi_od.control.screenshot import capture_window


def _spawn_notepad() -> subprocess.Popen | None:
    try:
        return subprocess.Popen(['notepad.exe'])
    except OSError:
        return None


def _kill(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope='module')
def notepad():
    proc = _spawn_notepad()
    if proc is None:
        pytest.skip('无法启动记事本')
    hwnd = None
    for _ in range(30):  # 等窗口出现
        time.sleep(0.5)
        for keyword in ('记事本', 'Notepad'):
            hwnd = win_ctl.find_window_by_keyword(keyword)
            if hwnd:
                break
        if hwnd:
            break
    if not hwnd:
        _kill(proc)
        pytest.skip('记事本窗口未出现（无交互式桌面）')
    yield proc, hwnd
    _kill(proc)


def test_find_window_by_keyword(notepad):
    _, hwnd = notepad
    assert hwnd
    title = win_ctl.window_title(hwnd)
    assert ('记事本' in title) or ('Notepad' in title)


def test_capture_notepad(notepad):
    _, hwnd = notepad
    image = capture_window(hwnd, 640, 360)
    assert image is not None, 'PrintWindow/BitBlt 均失败'
    assert image.shape == (360, 640, 3)
    assert float(image.mean()) > 2.0, '截图全黑'


def test_exact_title_no_match(notepad):
    # 用户可能正开着绝区零——此时跳过而不是误报
    if win_ctl.find_window('绝区零'):
        pytest.skip('绝区零窗口当前存在（用户在游戏）')
    assert win_ctl.find_window('不存在的窗口标题xyz') is None
