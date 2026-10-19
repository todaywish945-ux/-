"""提权运行一次活跃奖励任务（游戏以管理员权限运行时，引擎也需要提权才能注入输入）。

由主进程通过 PowerShell Start-Process -Verb RunAs 触发（UAC 确认后执行）。
完整日志（含状态机节点日志）写入 debug/elevated_run.log。
"""

import sys
import time
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT / 'src'))


def main() -> int:
    from remi_od.control.screenshot import enable_dpi_awareness

    enable_dpi_awareness()

    from remi_od.core.context import EngineContext
    from remi_od.apps.engagement_reward import EngagementRewardApp

    ctx = EngineContext(ENGINE_ROOT)
    ctx.init()
    ctx.controller.automatic = True

    app = EngagementRewardApp(ctx)
    result = app.execute(op_timeout_s=180)
    print(f'结果: {"成功" if result.success else "失败"} | {result.status}', flush=True)
    print(f'运行记录: {"今日已完成" if app.run_record.is_done else "未完成"}', flush=True)
    return 0 if result.success else 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    # 全量日志落盘（框架的节点日志走 print）
    log_path = ENGINE_ROOT / 'debug' / 'elevated_run.log'
    log_path.parent.mkdir(exist_ok=True)
    with open(log_path, 'w', encoding='utf-8', buffering=1) as log_file:
        sys.stdout = log_file
        sys.stderr = log_file
        time.sleep(3)  # 等 UAC 焦点稳定
        sys.exit(main())
