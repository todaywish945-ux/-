"""提权运行指定应用（游戏以管理员权限运行时，引擎需同级提权才能注入输入）。

用法（由主进程经 PowerShell -Verb RunAs 触发，app_id 作为参数传入）：
  python scripts/run_app_elevated.py <app_id> [visible]

完整日志写入 debug/elevated_run_<app_id>.log；带 visible 参数时单应用也弹
控制台实时输出（与一条龙一致），同时 tee 到日志文件供外部查看。
"""

import sys
import time
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT / 'src'))


class _Tee:
    """stdout 同时写终端与日志文件。"""

    def __init__(self, *streams) -> None:
        self._streams = streams

    def write(self, data) -> None:
        for s in self._streams:
            try:
                s.write(data)
                s.flush()
            except Exception:
                pass

    def flush(self) -> None:
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass


def _dock_console_beside_game() -> None:
    """把自己的控制台窗口挪到游戏画面右侧，避免盖住游戏导致截图/点击失效。"""
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()  # 注意：此 API 在 kernel32
    if not hwnd:
        return
    user32.SetProcessDPIAware()
    game = user32.FindWindowW(None, '绝区零')
    gx = gy = 0
    if game:
        import ctypes.wintypes as wt

        rect = wt.RECT()
        if user32.GetWindowRect(game, ctypes.byref(rect)):
            gx, gy = rect.right, rect.top
    if not game or gx <= 0:
        gx, gy = user32.GetSystemMetrics(0) - 620, 40
    user32.MoveWindow(hwnd, gx + 8, gy, 600, 900, True)


def main(app_id: str) -> int:
    from remi_od.control.screenshot import enable_dpi_awareness

    enable_dpi_awareness()

    from remi_od.apps.one_dragon import OneDragonOp, registry
    from remi_od.core.context import EngineContext

    ctx = EngineContext(ENGINE_ROOT)
    ctx.init()
    ctx.controller.automatic = True

    if app_id == 'one_dragon':
        op = OneDragonOp(ctx)
        result = op.execute(op_timeout_s=30 * 60)
        print()
        print('=' * 46)
        print(f'一条龙结束: {"全部成功" if result.success else "有失败"} | {result.status}')
        input('回车键退出…')
        return 0 if result.success else 1

    reg = registry()
    if app_id not in reg:
        print(f'未注册应用: {app_id}', flush=True)
        input('回车键退出…')
        return 2
    app = reg[app_id].factory(ctx)
    print(f'开始运行: {app.app_name}（每轮判断实时显示）', flush=True)
    result = app.execute(op_timeout_s=10 * 60)
    print(f'结果: {"成功" if result.success else "失败"} | {result.status}', flush=True)
    print(f'运行记录: {"今日已完成" if app.run_record.is_done else "未完成"}', flush=True)
    input('回车键退出…')
    return 0 if result.success else 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    app_id = sys.argv[1] if len(sys.argv) > 1 else 'daily_signin'
    visible = len(sys.argv) > 2 and sys.argv[2] == 'visible'
    log_path = ENGINE_ROOT / 'debug' / f'elevated_run_{app_id}.log'
    log_path.parent.mkdir(exist_ok=True)
    if app_id == 'one_dragon' or visible:
        # 控制台实时输出（同时 tee 到日志文件）
        _dock_console_beside_game()
        log_file = open(log_path, 'w', encoding='utf-8', buffering=1)
        sys.stdout = _Tee(sys.__stdout__, log_file)
        sys.stderr = _Tee(sys.__stderr__, log_file)
        time.sleep(2)  # 等 UAC 焦点稳定
        sys.exit(main(app_id))
    # 单应用（无 visible）：日志落盘（供外部轮询结果）
    with open(log_path, 'w', encoding='utf-8', buffering=1) as log_file:
        sys.stdout = log_file
        sys.stderr = log_file
        time.sleep(3)  # 等 UAC 焦点稳定
        sys.exit(main(app_id))
