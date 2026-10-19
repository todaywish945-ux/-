"""窗口截图：PrintWindow(含 RENDERFULLCONTENT) 优先，BitBlt 兜底，统一缩放到 1920x1080。

截图前必须先 enable_dpi_awareness()：高分屏（如 2560x1600@150%）下 DPI 不感知的
进程拿到的窗口坐标/尺寸是被系统缩放过的假值，屏幕 DC 截图会抓错区域。
"""

import ctypes
import time

import cv2
import numpy as np
import win32con
import win32gui
import win32ui

from remi_od.core.geometry import STANDARD_HEIGHT, STANDARD_WIDTH

PW_CLIENTONLY = 1
PW_RENDERFULLCONTENT = 2

_DPI_ENABLED = False


def enable_dpi_awareness() -> None:
    """让本进程拿到物理像素坐标（每显示器感知 V2）。幂等。"""
    global _DPI_ENABLED
    if _DPI_ENABLED:
        return
    user32 = ctypes.windll.user32
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            _DPI_ENABLED = True
            return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
        _DPI_ENABLED = True
    except Exception:
        pass


def _bitmap_to_bgr(bits: bytes, width: int, height: int) -> np.ndarray:
    arr = np.frombuffer(bits, dtype=np.uint8).reshape(height, width, 4)
    return arr[:, :, :3].copy()


def _try_print_window(hwnd: int, width: int, height: int) -> np.ndarray | None:
    try:
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bmp)
        try:
            import ctypes

            ok = ctypes.windll.user32.PrintWindow(
                hwnd, save_dc.GetSafeHdc(), PW_CLIENTONLY | PW_RENDERFULLCONTENT
            )
            if not ok:
                return None
            bits = bmp.GetBitmapBits(width * height * 4)
            return _bitmap_to_bgr(bits, width, height)
        finally:
            win32gui.DeleteObject(bmp.GetHandle())
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)
    except Exception:
        return None


def _try_bitblt(hwnd: int, width: int, height: int) -> np.ndarray | None:
    try:
        hwnd_dc = win32gui.GetDC(hwnd)  # 客户区 DC
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bmp)
        try:
            save_dc.BitBlt((0, 0), (width, height), mfc_dc, (0, 0), win32con.SRCCOPY)
            bits = bmp.GetBitmapBits(width * height * 4)
            return _bitmap_to_bgr(bits, width, height)
        finally:
            win32gui.DeleteObject(bmp.GetHandle())
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)
    except Exception:
        return None


def _try_screen_bitblt(hwnd: int, width: int, height: int) -> np.ndarray | None:
    """从屏幕 DC 截取窗口客户区所在的屏幕区域。

    ZZZ 前台渲染时走硬件叠加层（MPO），窗口 DC 的 GDI 截图全黑，
    只有屏幕 DC 能拿到真实画面（要求窗口前台可见——自动运行已保证）。
    """
    try:
        left, top = win32gui.ClientToScreen(hwnd, (0, 0))
        hdc = win32gui.GetDC(0)
        mfc_dc = win32ui.CreateDCFromHandle(hdc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bmp)
        try:
            save_dc.BitBlt((0, 0), (width, height), mfc_dc, (left, top), win32con.SRCCOPY)
            bits = bmp.GetBitmapBits(width * height * 4)
            return _bitmap_to_bgr(bits, width, height)
        finally:
            win32gui.DeleteObject(bmp.GetHandle())
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(0, hdc)
    except Exception:
        return None


def _is_blank(image: np.ndarray) -> bool:
    """全黑或几乎全黑视为无效截图。"""
    return float(image.mean()) < 2.0


def client_size(hwnd: int) -> tuple[int, int]:
    """客户区尺寸（不改变窗口状态；最小化时也能取）。"""
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    return right - left, bottom - top


def capture_window(
    hwnd: int,
    standard_width: int = STANDARD_WIDTH,
    standard_height: int = STANDARD_HEIGHT,
    retry: int = 2,
) -> np.ndarray | None:
    """截取客户区并缩放到标准分辨率；失败返回 None。

    注意：ZZZ 屏蔽 PrintWindow（返回 0），实际靠 BitBlt——它是屏幕区域拷贝，
    窗口被遮挡时会截到遮挡物。因此自动化运行中必须先保证游戏窗口前台
    （见 Controller.screenshot 的前台激活）。

    2026-09-25 实测：游戏切成小窗口（如 1280x720 窗口化）后 PrintWindow 会
    "成功"但永远返回同一张缓存帧（画面冻结假象），因此前台时改为屏幕 BitBlt
    优先，PrintWindow 仅在非前台（窗口被遮挡）时尝试。
    """
    enable_dpi_awareness()
    try:
        foreground_first = win32gui.GetForegroundWindow() == hwnd
    except Exception:
        foreground_first = False
    for _ in range(max(1, retry)):
        width, height = client_size(hwnd)
        if width <= 0 or height <= 0:
            time.sleep(0.1)
            continue
        if foreground_first:
            image = _try_screen_bitblt(hwnd, width, height)
            if image is None or _is_blank(image):
                image = _try_print_window(hwnd, width, height)
            if image is None or _is_blank(image):
                image = _try_bitblt(hwnd, width, height)
        else:
            image = _try_print_window(hwnd, width, height)
            if image is None or _is_blank(image):
                image = _try_bitblt(hwnd, width, height)
            if image is None or _is_blank(image):
                image = _try_screen_bitblt(hwnd, width, height)
        if image is not None and not _is_blank(image):
            if image.shape[1] != standard_width or image.shape[0] != standard_height:
                image = cv2.resize(image, (standard_width, standard_height))
            return image
        time.sleep(0.1)
    return None
