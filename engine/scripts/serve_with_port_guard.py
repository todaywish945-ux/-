"""引擎服务启动守卫：先清理 23001 端口占用（旧版引擎可能开机自启抢占），
再启动迷你引擎 HTTP 服务。作为计划任务的入口，保证任何启动顺序下
迷你引擎最终持有端口。
"""

import subprocess
import sys
import time
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT / 'src'))

PORT = 23001


def port_pids() -> list[str]:
    r = subprocess.run(['netstat', '-ano', '-p', 'TCP'], capture_output=True,
                       text=True, errors='replace')
    pids = []
    for line in (r.stdout or '').splitlines():
        if f':{PORT}' in line and 'LISTENING' in line:
            pid = line.split()[-1]
            if pid not in pids:
                pids.append(pid)
    return pids


def main() -> int:
    from remi_od.core.log import log

    time.sleep(2)  # 等旧实例退出（热重启场景）
    for pid in port_pids():
        subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True)
        log('守卫', f'已清理端口 {PORT} 占用 PID {pid}')
    if port_pids():
        time.sleep(1)

    from remi_od.server.main import main as serve_main

    serve_main()
    return 0


if __name__ == '__main__':
    main()
