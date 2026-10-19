"""统一日志：输出到 stdout（桌宠会把引擎 stdout 重定向到日志文件）。

pythonw（无窗口）运行时 stdout 为 None，自动改写入 引擎根/debug/引擎服务.log。
"""

import sys
import time
from pathlib import Path

_LOG_FILE: Path | None = None


def _ensure_output() -> None:
    global _LOG_FILE
    if sys.stdout is None:
        root = Path(__file__).resolve().parents[3]
        _LOG_FILE = root / 'debug' / '引擎服务.log'
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        sys.stdout = open(_LOG_FILE, 'a', encoding='utf-8', buffering=1)
    elif hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    # pythonw 下 stderr 为 None，异常栈会丢——一并落到日志文件
    if sys.stderr is None and _LOG_FILE is not None:
        sys.stderr = open(_LOG_FILE, 'a', encoding='utf-8', buffering=1)


def log(tag: str, msg: str) -> None:
    _ensure_output()
    now = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{now}] [{tag}] {msg}', flush=True)
