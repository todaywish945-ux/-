"""引擎上下文：控制器、识别、配置、停止标志、运行状态汇报的总枢纽。"""

import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from remi_od.control.controller import Controller
from remi_od.core import config as config_mod
from remi_od.core.geometry import Point
from remi_od.core.log import log
from remi_od.core.round_result import RoundResult
from remi_od.vision.screen_info import ScreenBook
from remi_od.vision.template import MatchResult, TemplateStore, match_template


@dataclass
class RunState:

    """对外（/game/status）暴露的运行状态快照。"""

    state: str = 'idle'  # idle / running / success / failed / stopped
    app: str | None = None
    current_node: str | None = None
    retry_count: int = 0
    last_status: str | None = None
    failed_node: str | None = None
    started_at: str | None = None
    source: str = 'http'

    def snapshot(self) -> dict:
        duration = 0.0
        if self.started_at and self.state == 'running':
            started = datetime.fromisoformat(self.started_at)
            duration = (datetime.now() - started).total_seconds()
        return {
            'state': self.state,
            'source': self.source,
            'app': self.app,
            'started_at': self.started_at,
            'duration_seconds': round(duration, 1),
            'current_node': self.current_node,
            'retry_count': self.retry_count,
            'last_status': self.last_status,
            'failed_node': self.failed_node,
        }


class EngineContext:

    def __init__(self, engine_root: Path, instance_idx: int = 1):
        self.root: Path = engine_root
        self.paths: config_mod.EnginePaths = config_mod.EnginePaths(engine_root, instance_idx)
        self.controller: Controller = Controller()
        self.screen_book: ScreenBook = ScreenBook(self.paths.screen_info_dir)
        self.templates: TemplateStore = TemplateStore(self.paths.template_dir)
        self._stop_event = threading.Event()
        self._f10_stop = threading.Event()  # F10 热键触发的停止（随时停止键）
        self._op_depth: int = 0  # Operation.execute 嵌套深度（最外层才清 F10 标志）
        self.run_state: RunState = RunState()
        self.uid: str = ''  # 当前游戏账号 UID（运行记录按账号区分，换号防串）
        self._app_scope: str = ''  # 当前应用的画面范围（app_id，空=全局）
        self._ocr = None  # 惰性 OCR 引擎
        self._debug_counts: dict[str, int] = {}  # 每个 tag 已存的调试图数（防刷盘）

    # ---- 初始化 ----

    def init(self) -> None:
        config_mod.write_default_configs_if_missing(self.paths)
        self._start_f10_watcher()
        self._warm_ocr()
        log('引擎', f'初始化完成: root={self.root}')

    def _warm_ocr(self) -> None:
        """后台预热 OCR（建会话+首次推理约 1-2s），挪到启动期避免首跑卡顿。"""
        import threading as _threading

        def warm() -> None:
            try:
                self.ocr.warmup()
                log('引擎', 'OCR 预热完成')
            except Exception as e:
                log('引擎', f'OCR 预热失败（不影响运行，首次调用会重建）: {e}')

        _threading.Thread(target=warm, daemon=True, name='ocr-warmup').start()

    def _start_f10_watcher(self) -> None:
        """F10 全局热键：运行中任意时刻按下立即停止当前运行（用户要求）。

        GetAsyncKeyState 读全局按键状态，无需窗口焦点；仅在有运行嵌套时
        触发（闲置按 F10 无效果，也不会污染下一次运行）。
        """
        import ctypes
        import time as _time

        VK_F10 = 0x79

        def poll() -> None:
            was_down = False
            while True:
                try:
                    down = bool(ctypes.windll.user32.GetAsyncKeyState(VK_F10) & 0x8000)
                    if down and not was_down and self._op_depth > 0 \
                            and not self._f10_stop.is_set():
                        log('引擎', 'F10 按下：停止当前运行')
                        self._f10_stop.set()
                    was_down = down
                except Exception:
                    pass
                _time.sleep(0.1)

        threading.Thread(target=poll, daemon=True, name='f10-stop').start()

    # ---- 停止 ----

    def request_stop(self) -> None:
        self._stop_event.set()

    def clear_stop(self) -> None:
        self._stop_event.clear()

    def is_stop_requested(self) -> bool:
        return self._stop_event.is_set() or self._f10_stop.is_set()

    def op_begin(self) -> None:
        """Operation.execute 进入：最外层操作清除上次运行残留的 F10 标志。"""
        self._op_depth += 1
        if self._op_depth == 1:
            self._f10_stop.clear()

    def op_end(self) -> None:
        self._op_depth = max(0, self._op_depth - 1)

    # ---- 运行状态汇报（供 /game/status 轮询） ----

    def report_node(self, op_name: str, node_name: str) -> None:
        self.run_state.current_node = node_name

    def report_retry(self, retry_times: int) -> None:
        self.run_state.retry_count = retry_times

    # ---- 画面范围 ----

    def enter_scope(self, app_id: str) -> None:
        self._app_scope = app_id

    def exit_scope(self) -> None:
        self._app_scope = ''

    # ---- 识别 ----

    @property
    def ocr(self):
        from remi_od.vision.ocr import OcrEngine

        if self._ocr is None:
            self._ocr = OcrEngine()
        return self._ocr

    def get_area(self, screen_name: str, area_name: str):
        return self.screen_book.get_area(screen_name, area_name)

    def find_area(self, shot: np.ndarray, screen_name: str,
                  area_name: str) -> RoundResult | None:
        """在截图中找区域。返回 round_success 风格的 RoundResult（data=MatchResult）；
        未命中返回 None；区域无定义抛错由节点层兜底。"""
        area = self.screen_book.get_area(screen_name, area_name)
        if area is None:
            raise ValueError(f'区域未建档: {screen_name}.{area_name}')
        if area.is_template_area:
            pair = self.templates.get(area.template)
            if pair is None:
                raise ValueError(f'模板图缺失: {area.template} (区域 {area.key})')
            template, mask = pair
            x1, y1, x2, y2 = area.rect.as_tuple()
            crop = shot[y1:y2, x1:x2]
            hits = match_template(crop, template, area.threshold, mask)
            if hits:
                best = hits[0]
                absolute = MatchResult(
                    score=best.score,
                    center=Point(best.center.x + x1, best.center.y + y1),
                    rect=best.rect,
                )
                return RoundResult(1, area.key, absolute)
            return None
        if area.is_text_area:
            item = self.ocr.find_text(shot, area.ocr_text, area.rect, area.lcs)
            if item is not None:
                return RoundResult(1, area.key, MatchResult(item.score, item.center, item.rect))
            return None
        # 纯坐标区域（无模板无文本）：视为命中（用于固定点击位）
        return RoundResult(1, area.key, MatchResult(1.0, area.center, area.rect))

    def is_screen(self, shot: np.ndarray, screen_name: str) -> bool:
        """画面判定：该画面所有 id_mark 区域全部命中。"""
        screen = self.screen_book.screens.get(screen_name)
        if screen is None or not screen.id_marks:
            return False
        for area in screen.id_marks:
            result = self.find_area(shot, screen_name, area.area_name)
            if result is None:
                return False
        return True

    def which_screen(self, shot: np.ndarray, last_screen: str | None = None) -> str | None:
        """识别当前画面名。先查上次画面，再查范围内的全部画面。"""
        if last_screen and self.is_screen(shot, last_screen):
            return last_screen
        for name in self.screen_book.screen_names(self._app_scope):
            if self.is_screen(shot, name):
                return name
        return None

    # ---- 调试 ----

    def save_debug_image(self, tag: str, image: np.ndarray) -> Path | None:
        """按 tag 限量存调试图（每 tag 最多 3 张：诊断够用，又不随重试轮刷盘）。"""
        if self._debug_counts.get(tag, 0) >= 3:
            return None
        import cv2

        self.paths.debug_dir.mkdir(parents=True, exist_ok=True)
        safe = tag.replace('/', '_').replace('\\', '_')
        path = self.paths.debug_dir / f'{datetime.now().strftime("%H%M%S")}_{safe}.png'
        cv2.imencode('.png', image)[1].tofile(str(path))
        self._debug_counts[tag] = self._debug_counts.get(tag, 0) + 1
        return path
