"""一次性安装：让"桌宠 → 一键日常"开箱即用。

做四件事（本脚本需以管理员运行，由 安装服务.bat 触发 UAC）：
1. 结束 23001 端口上的旧占用（如原版引擎）
2. 创建开机自启计划任务（最高权限运行引擎服务，日常零 UAC）
3. 立即启动一次服务
4. 把桌宠的 绝区零配置.json 指向本引擎（保留原配置为备份）

重复运行安全（幂等）。
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
TASK_NAME = '小蕾米引擎服务'
PORT = 23001


def python_exe() -> Path:
    """引擎用解释器：优先便携 runtime（自包含分发包），回退 .venv（开发机）。"""
    runtime = ENGINE_ROOT / 'runtime' / 'pythonw.exe'
    if runtime.exists():
        return runtime
    return ENGINE_ROOT / '.venv' / 'Scripts' / 'pythonw.exe'


def find_pet_config() -> Path | None:
    """桌宠配置自动发现：环境变量显式指定 > 桌面常见布局 > 引擎同级目录。"""
    candidates = []
    env = os.environ.get('XIAOLEIMI_PET_CONFIG')
    if env:
        candidates.append(Path(env))
    desktop = Path.home() / 'Desktop'
    candidates += [
        desktop / '小蕾米AI助理' / '小蕾米AI助理' / '绝区零配置.json',
        desktop / '小蕾米AI助理' / '绝区零配置.json',
        ENGINE_ROOT.parent / '小蕾米AI助理' / '小蕾米AI助理' / '绝区零配置.json',
        ENGINE_ROOT.parent / '小蕾米AI助理' / '绝区零配置.json',
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                          errors='replace', **kw)


def kill_port(port: int) -> None:
    r = run(['netstat', '-ano', '-p', 'TCP'])
    pids = set()
    for line in (r.stdout or '').splitlines():
        if f':{port}' in line and 'LISTENING' in line:
            pids.add(line.split()[-1])
    for pid in pids:
        run(['taskkill', '/F', '/PID', pid])
        print(f'  已结束端口 {port} 占用 PID {pid}')
    if pids:
        time.sleep(1)


def health_ok() -> dict | None:
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/health', timeout=2) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception:
        return None


def create_task() -> None:
    run(['schtasks', '/Delete', '/TN', TASK_NAME, '/F'])  # 幂等
    pythonw = python_exe()
    guard = ENGINE_ROOT / 'scripts' / 'serve_with_port_guard.py'
    cmd = (f'schtasks /Create /TN "{TASK_NAME}" /TR "\\"{pythonw}\\" \\"{guard}\\" '
           f'--host 127.0.0.1 --port {PORT}" /SC ONLOGON /RL HIGHEST /F')
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    ok = r.returncode == 0
    print(f'  计划任务创建: {"成功（含端口守卫）" if ok else "失败 " + (r.stderr or "")}'
          f'  解释器: {pythonw.parent.name}')


def start_task() -> None:
    run(['schtasks', '/Run', '/TN', TASK_NAME])
    for _ in range(20):
        time.sleep(1)
        h = health_ok()
        if h and h.get('ok'):
            print(f'  服务已启动: {h}')
            return
    print('  服务启动超时（看 debug/引擎服务.log）')


def config_pet() -> None:
    pet_config = find_pet_config()
    if pet_config is None:
        print('  未找到小蕾米桌宠（桌面/引擎同级均无），跳过对接。'
              '装好桌宠后重新运行本脚本即可。')
        return
    backup = pet_config.with_suffix('.json.bak')
    if not backup.exists():
        backup.write_bytes(pet_config.read_bytes())
        print(f'  原配置已备份: {backup.name}')
    data = json.loads(pet_config.read_text(encoding='utf-8'))
    if data.get('engine_dir') == str(ENGINE_ROOT):
        print('  桌宠已指向本引擎')
        return
    data['engine_dir'] = str(ENGINE_ROOT)
    data['host'] = '127.0.0.1'
    data['port'] = PORT
    pet_config.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                          encoding='utf-8')
    print(f'  桌宠已指向本引擎: {ENGINE_ROOT}')


def detect_game_path() -> None:
    """静默探测游戏路径（各盘 miHoYo Launcher 默认布局）；未命中不打扰用户。"""
    sys.path.insert(0, str(ENGINE_ROOT / 'scripts'))
    from set_game_path import detect

    exe = detect()
    if exe is None:
        print('  未自动找到游戏路径（不影响手动开着游戏使用；'
              '需要自动启动游戏时运行 scripts/set_game_path.py 填写）')
        return
    from remi_od.core import config as config_mod

    paths = config_mod.EnginePaths(ENGINE_ROOT)
    data = config_mod.game_account(paths)
    if data.get('game_path') == str(exe):
        print(f'  游戏路径已配置: {exe}')
        return
    data['game_path'] = str(exe)
    config_mod.save_game_account(paths, data)
    print(f'  游戏路径已写入: {exe}')


def main() -> int:
    import ctypes

    if not ctypes.windll.shell32.IsUserAnAdmin():
        print('需要管理员权限运行（请通过 一键安装.bat 启动）')
        return 1
    print('1. 清理端口占用…')
    kill_port(PORT)
    print('2. 创建开机自启计划任务（日常免 UAC）…')
    create_task()
    print('3. 启动服务…')
    start_task()
    print('4. 配置桌宠指向本引擎…')
    config_pet()
    print('5. 探测游戏路径…')
    detect_game_path()
    print()
    print('完成！以后直接用小蕾米桌宠的[一键日常]即可。')
    input('回车键退出…')
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    sys.exit(main())
