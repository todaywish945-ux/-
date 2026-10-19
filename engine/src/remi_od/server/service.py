"""引擎服务：单跑道运行槽（并发拒绝）+ 状态机 + 对外快照。"""

import threading
from datetime import datetime

from remi_od.core.context import EngineContext
from remi_od.core.log import log
from remi_od.core.round_result import OpResult


class EngineService:

    def __init__(self, ctx: EngineContext):
        self.ctx: EngineContext = ctx
        self.ready: bool = False
        self._lock = threading.Lock()
        self._running: bool = False
        self._worker: threading.Thread | None = None
        self._done_event = threading.Event()
        self._last_result_text: str = ''
        self._start_hotkey_watcher()

    def _start_hotkey_watcher(self) -> None:
        """全局热键：F9 启动一条龙 / F12 游戏全屏⇄窗口切换（与 F10 停止配对）。

        GetAsyncKeyState 读全局按键状态，实体按键有效（软件注入被 UIPI
        过滤）。已有运行时按 F9 忽略并提示。
        """
        import ctypes
        import time as _time
        from ctypes import wintypes as _wt

        user32 = ctypes.windll.user32
        VK_F9, VK_F12 = 0x78, 0x7B
        GWL_STYLE = -16
        WS_CAPTION, WS_THICKFRAME = 0x00C00000, 0x00040000
        # 已验证可用的窗口化摆放（1920x1080 客户区）
        WIN_X, WIN_Y, WIN_W, WIN_H = 200, 100, 1936, 1145

        def toggle_fullscreen() -> None:
            hwnd = user32.FindWindowW(None, '绝区零')
            if not hwnd:
                log('引擎', 'F12：游戏窗口未找到')
                return
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            if style & WS_CAPTION:
                # → 无边框铺满整个显示器（识别按比例缩放不受影响）
                user32.SetWindowLongW(hwnd, GWL_STYLE,
                                      style & ~(WS_CAPTION | WS_THICKFRAME))
                user32.SetWindowPos(hwnd, 0, 0, 0,
                                    user32.GetSystemMetrics(0),
                                    user32.GetSystemMetrics(1), 0x0040)
                log('引擎', 'F12：已切换为无边框全屏')
            else:
                # → 恢复 1920x1080 窗口化
                user32.SetWindowLongW(hwnd, GWL_STYLE,
                                      style | WS_CAPTION | WS_THICKFRAME)
                user32.SetWindowPos(hwnd, 0, WIN_X, WIN_Y, WIN_W, WIN_H, 0x0040)
                log('引擎', 'F12：已恢复窗口化')

        def poll() -> None:
            f9_down = f12_down = False
            while True:
                try:
                    d9 = bool(user32.GetAsyncKeyState(VK_F9) & 0x8000)
                    if d9 and not f9_down:
                        if self._running:
                            log('引擎', 'F9 按下：已有运行在进行中，忽略')
                        else:
                            log('引擎', 'F9 按下：启动一条龙')
                            self.start_run('one_dragon')
                    f9_down = d9
                    d12 = bool(user32.GetAsyncKeyState(VK_F12) & 0x8000)
                    if d12 and not f12_down:
                        toggle_fullscreen()
                    f12_down = d12
                except Exception as e:
                    log('引擎', f'热键监听异常: {e}')
                _time.sleep(0.1)

        threading.Thread(target=poll, daemon=True, name='hotkeys').start()

    # ---- 应用清单 ----

    def applications(self) -> dict:
        from remi_od.apps.one_dragon import registry
        from remi_od.core import config as config_mod

        reg = registry()
        enabled_map = dict(config_mod.group_apps(self.ctx.paths))
        apps = [{
            'app_id': APP_ID_ONE_DRAGON,
            'app_name': '一条龙',
            'description': '按任务清单顺序执行全部日常',
            'enabled_in_one_dragon': True,
            'in_standalone_list': True,
        }]
        for app_id, info in reg.items():
            apps.append({
                'app_id': app_id,
                'app_name': info.app_name,
                'description': info.description,
                'enabled_in_one_dragon': enabled_map.get(app_id, False),
                'in_standalone_list': info.standalone,
            })
        return {
            'current_instance_idx': self.ctx.paths.instance_idx,
            'active_standalone_app_id': None,
            'applications': apps,
        }

    # ---- 窗口与截图 ----

    def window_status(self) -> dict:
        return self.ctx.controller.window_status()

    def run_visible(self, app_id: str) -> dict:
        """以服务自身权限弹出可见控制台运行应用（免 UAC）。

        服务是提权进程，它启动的 python.exe 控制台继承权限，
        且游戏输入注入可用。控制台会自动停靠在游戏右侧（见
        scripts/run_app_elevated.py 的 _dock_console_beside_game）。
        """
        import subprocess
        import sys

        if self._running:
            return {'started': False, 'error': '已有运行在进行中'}
        root = self.ctx.paths.root
        python_exe = root / '.venv' / 'Scripts' / 'python.exe'
        if not python_exe.exists():
            python_exe = root / '.venv' / 'Scripts' / 'pythonw.exe'
        script = root / 'scripts' / 'run_app_elevated.py'
        try:
            subprocess.Popen(
                [str(python_exe), str(script), app_id, 'visible'],
                cwd=str(root),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            return {'started': True, 'note': '新弹出的控制台窗口可实时查看每轮判断'}
        except Exception as e:
            return {'started': False, 'error': str(e)}

    def debug_kbtest(self) -> dict:
        """在服务进程内做键盘通路诊断：M 开地图前后像素差。

        用于区分"键盘注入被 UIPI 拦截"与"游戏端不响应"：
        外部终端无管理员权限时 SendInput 会被静默丢弃，结论不可信。
        """
        import time

        import cv2

        ctl = self.ctx.controller
        was_automatic = ctl.automatic
        ctl.automatic = True
        try:
            if not ctl.ensure_foreground():
                return {'error': '无法把游戏带到前台', 'foreground': False}
            img1 = ctl.screenshot()
            if img1 is None:
                return {'error': '截图失败'}
            ctl.key('m', press_time=0.2)
            time.sleep(1.5)
            img2 = ctl.screenshot()
            diff_m = float(cv2.absdiff(img1, img2).mean())
            ctl.key('m', press_time=0.2)  # 关回地图（若已打开）
            time.sleep(1.0)
            return {
                'foreground': True,
                'diff_m': round(diff_m, 1),
                'keyboard_ok': diff_m > 30,
                'note': 'diff_m>30 说明 M 打开了地图，键盘注入有效',
            }
        finally:
            ctl.automatic = was_automatic

    def capture_png(self) -> bytes | None:
        import cv2

        shot = self.ctx.controller.screenshot()
        if shot is None:
            return None
        ok, buf = cv2.imencode('.png', shot)
        return buf.tobytes() if ok else None

    # ---- 运行控制 ----

    def start_run(self, kind: str, app_id: str = '') -> tuple[bool, str | None]:
        """启动一次运行。kind: one_dragon / app / enter。已有运行时拒绝。"""
        with self._lock:
            if self._running:
                return False, '已有运行在进行中'
            self._running = True
            self._done_event.clear()
            state = self.ctx.run_state
            state.state = 'running'
            state.app = {'one_dragon': '一条龙', 'enter': '进入游戏'}.get(kind, app_id)
            state.current_node = None
            state.retry_count = 0
            state.last_status = None
            state.failed_node = None
            state.started_at = datetime.now().isoformat()
            self.ctx.clear_stop()
            self.ctx.controller.automatic = True  # 运行中截图前强制游戏前台
            self._worker = threading.Thread(
                target=self._worker_run, args=(kind, app_id), daemon=True,
                name='remi-run')
            self._worker.start()
        label = state.app or kind
        return True, None

    def _worker_run(self, kind: str, app_id: str) -> None:
        # 单任务模式：录像店/签到/咖啡成功后自动补跑活跃奖励
        # （这三项会涨活跃度，解锁新档位；一次 40 秒，防"忘领"）
        follow_up = (kind == 'app' and app_id in
                     ('random_play', 'daily_signin', 'coffee'))
        result: OpResult
        try:
            if kind == 'one_dragon':
                from remi_od.apps.one_dragon import OneDragonOp

                op = OneDragonOp(self.ctx)
                result = op.execute(op_timeout_s=45 * 60)
                text = result.status if result.success else f'失败: {result.status}'
            elif kind == 'enter':
                from remi_od.apps.enter_game import EnterGameOp

                op = EnterGameOp(self.ctx)
                result = op.execute(op_timeout_s=20 * 60)
                text = '进入游戏成功' if result.success else f'失败: {result.status}'
            else:
                from remi_od.apps.one_dragon import registry

                reg = registry()
                if app_id not in reg:
                    result = OpResult(False, f'未注册应用: {app_id}')
                    text = f'失败: 未注册应用 {app_id}'
                else:
                    app = reg[app_id].factory(self.ctx)
                    result = app.execute(op_timeout_s=45 * 60)
                    text = (f'{reg[app_id].app_name}完成' if result.success
                            else f'失败: {result.status}')
        except Exception as e:
            log('运行', f'运行异常: {e}')
            result = OpResult(False, f'异常: {e}')
            text = f'失败: 异常 {e}'

        # 单任务成功且不是活跃奖励本身 → 自动补跑活跃奖励（新解锁档位一块领）
        if follow_up and result.success and app_id != 'engagement_reward':
            log('运行', '单任务完成，自动补跑活跃奖励领取')
            try:
                from remi_od.apps.engagement_reward import EngagementRewardApp

                app = EngagementRewardApp(self.ctx)
                claim = app.execute(op_timeout_s=10 * 60)
                text += '；活跃奖励:' + ('已领取' if claim.success
                                          else f'领取失败({claim.status})')
            except Exception as e:
                log('运行', f'补跑活跃奖励异常: {e}')
                text += '；活跃奖励:补跑异常'

        state = self.ctx.run_state
        if result.status == '人工结束':
            state.state = 'stopped'
        elif result.success:
            state.state = 'success'
        else:
            state.state = 'failed'
            state.failed_node = state.current_node
        state.last_status = result.status
        self._last_result_text = text
        self.ctx.controller.automatic = False
        log('运行', f'结束 state={state.state} status={result.status}')
        with self._lock:
            self._running = False
        self._done_event.set()

    def wait_done(self, timeout_s: float = 3700.0) -> str:
        self._done_event.wait(timeout_s)
        return self._last_result_text

    def stop(self) -> tuple[bool, str | None]:
        with self._lock:
            if not self._running:
                return False, '当前无运行'
        self.ctx.request_stop()
        return True, None

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def status(self) -> dict:
        return self.ctx.run_state.snapshot()


APP_ID_ONE_DRAGON = 'one_dragon'
