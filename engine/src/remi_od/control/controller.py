"""控制器：窗口定位 + 截图 + 标准坐标点击换算，是引擎与游戏交互的唯一入口。"""

import time

import numpy as np

from remi_od.control import input as input_ctl
from remi_od.control import launch as launch_ctl
from remi_od.control import screenshot as shot_ctl
from remi_od.control import window as win_ctl
from remi_od.core.geometry import Point, Rect, STANDARD_HEIGHT, STANDARD_WIDTH
from remi_od.core.log import log


class Controller:

    def __init__(self, window_title: str = win_ctl.GAME_WINDOW_TITLE):
        self.window_title: str = window_title
        self.hwnd: int | None = None
        # 自动化运行中：截图前强制把游戏窗口带到前台。
        # ZZZ 屏蔽 PrintWindow，只能 BitBlt（屏幕区域拷贝），被遮挡会截到遮挡物。
        self.automatic: bool = False

    # ---- 窗口 ----

    def find_game_window(self) -> int | None:
        self.hwnd = win_ctl.find_window(self.window_title)
        return self.hwnd

    def is_window_ready(self) -> bool:
        """窗口存在且客户区为标准 1920x1080。"""
        hwnd = self.find_game_window()
        if not hwnd:
            return False
        width, height = shot_ctl.client_size(hwnd)
        return (width, height) == (STANDARD_WIDTH, STANDARD_HEIGHT)

    def window_status(self) -> dict:
        hwnd = self.find_game_window()
        if not hwnd:
            return {
                'win_title': '', 'is_win_valid': False, 'is_win_active': False,
                'is_win_scale': False, 'x': 0, 'y': 0, 'width': 0, 'height': 0,
            }
        width, height = shot_ctl.client_size(hwnd)
        left, top = win_ctl.client_left_top(hwnd)
        return {
            'win_title': win_ctl.window_title(hwnd),
            'is_win_valid': width > 0 and height > 0,
            'is_win_active': win_ctl.is_foreground(hwnd),
            'is_win_scale': (width, height) == (STANDARD_WIDTH, STANDARD_HEIGHT),
            'x': left, 'y': top, 'width': width, 'height': height,
        }

    def active_window(self) -> None:
        if self.hwnd:
            win_ctl.set_foreground(self.hwnd)

    def ensure_foreground(self) -> bool:
        """确保游戏窗口是前台（键盘注入的接收方），带验证重试。

        2026-09-25 实测：用户点开其他窗口（如抖音）后游戏失焦，注入的 F/W
        全部落空且无任何报错；set_foreground 在前台锁下也可能静默失败。
        因此激活后必须回读验证，失败重试一次。automatic 模式下 key()/turn()
        前调用。
        """
        hwnd = self.hwnd or self.find_game_window()
        if not hwnd:
            return False
        if win_ctl.is_foreground(hwnd):
            return True
        for _ in range(2):
            self.active_window()
            time.sleep(0.15)
            if win_ctl.is_foreground(hwnd):
                return True
        return False

    # ---- 截图 ----

    def screenshot(self) -> np.ndarray | None:
        """返回 1920x1080 BGR 截图；窗口不在时返回 None。

        automatic 模式下确保游戏窗口前台（还原+激活），保证 BitBlt 截到
        的是游戏画面而不是遮挡物。已在前台时不重复激活（省 0.15s/张）。
        """
        hwnd = self.find_game_window()
        if not hwnd:
            return None
        if self.automatic:
            self.ensure_foreground()  # 前台才截得到真实画面；失败仍尝试截
            hwnd = self.hwnd or self.find_game_window()
            if not hwnd:
                return None
        return shot_ctl.capture_window(hwnd)

    # ---- 坐标换算与点击 ----

    def _to_screen(self, point: Point) -> Point | None:
        """标准 1920x1080 坐标 → 客户区屏幕坐标。"""
        hwnd = self.hwnd or self.find_game_window()
        if not hwnd:
            return None
        width, height = shot_ctl.client_size(hwnd)
        if width <= 0 or height <= 0:
            return None
        left, top = win_ctl.client_left_top(hwnd)
        return Point(left + point.x * width // STANDARD_WIDTH,
                     top + point.y * height // STANDARD_HEIGHT)

    def _ensure_mouse_mode(self) -> None:
        """确保游戏处于可点击的键鼠模式。

        绝区零在视角控制状态会把光标 ClipCursor 钉在一个点上（隐藏光标用
        Raw Input 转视角），此时所有 SetCursorPos 都会被拉回钉点、点击全落空。
        处理：解锁光标裁剪 + 发一次微小相对移动触发 Raw Input 让游戏切回键鼠。
        """
        import ctypes

        ctypes.windll.user32.ClipCursor(None)
        if self.hwnd or self.find_game_window():
            self.active_window()
        ctypes.windll.user32.mouse_event(0x0001, 2, 0, 0, 0)  # MOUSEEVENTF_MOVE dx=2
        time.sleep(0.05)

    def turn(self, dx: float, dy: float = 0.0) -> None:
        """相对移动鼠标转动视角。

        不调用 _ensure_mouse_mode（那会把游戏切到自由光标态）；
        仅在大世界键鼠视角控制态下有效，其他画面下移动无害。
        """
        if dx == 0 and dy == 0 or not self.find_game_window():
            return
        if self.automatic:
            self.ensure_foreground()  # 相对鼠标移动同样只作用于前台窗口
        import ctypes

        ctypes.windll.user32.mouse_event(0x0001, int(dx), int(dy), 0, 0)
        time.sleep(0.1)

    def click(self, point: Point | None = None, press_time: float = 0.08,
              alt: bool = False) -> bool:
        """点击标准坐标（None=原地点击当前光标处）。

        alt=True：按住 ALT 再点击（大世界等锁鼠标画面需要 ALT 解锁光标）。
        """
        if not self.find_game_window():
            return False
        self._ensure_mouse_mode()
        if alt:
            input_ctl.key_down('alt')
            time.sleep(0.2)
        try:
            if point is not None:
                target = self._to_screen(point)
                if target is None:
                    return False
                from remi_od.core.log import log
                t0 = time.time()
                input_ctl.move_to(target.x, target.y)
                time.sleep(0.03)
                input_ctl.click(press_time)
                log('操作', f'点击({target.x},{target.y}) 用时{time.time()-t0:.2f}s')
            else:
                input_ctl.click(press_time)
        finally:
            if alt:
                input_ctl.key_up('alt')
        return True

    def click_area(self, area) -> bool:
        """点击画面区域中心。"""
        return self.click(area.center)

    def key(self, name: str, press_time: float = 0.05) -> None:
        if self.automatic:
            self.ensure_foreground()  # 键盘注入必须落在游戏上，失焦则全落空
        from remi_od.core.log import log
        t0 = time.time()
        input_ctl.key_tap(name, press_time)
        log('操作', f'按键[{name}] 按住{press_time:.2f}s 用时{time.time()-t0:.2f}s')

    def key_down(self, name: str) -> None:
        input_ctl.key_down(name)

    def key_up(self, name: str) -> None:
        input_ctl.key_up(name)

    def drag(self, start: Point, end: Point, duration: float = 0.3) -> bool:
        s = self._to_screen(start)
        e = self._to_screen(end)
        if s is None or e is None:
            return False
        input_ctl.drag(s.as_tuple(), e.as_tuple(), duration)
        return True

    # ---- 启动 ----

    def launch_game(self, game_path: str) -> bool:
        return launch_ctl.launch_game(game_path)

    def wait_window(self, timeout_s: float = 60.0) -> int | None:
        """轮询等待游戏窗口出现。"""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            hwnd = self.find_game_window()
            if hwnd:
                return hwnd
            time.sleep(1)
        return None
