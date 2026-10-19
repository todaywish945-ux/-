"""冒烟：桌宠真实客户端代码 × 迷你引擎 shim 进程契约。

流程（全程只读，不影响正在运行的游戏）：
1. 按桌宠 zzz_daily.py 的启动方式（-m zzz_od.backend.entry.server + PYTHONPATH=src）
   拉起迷你引擎服务进程（临时端口）；
2. 用 importlib 加载桌宠的真实 OneDragonEngine 类连上引擎；
3. 验证 is_installed / health / 应用列表 / 窗口状态 / 状态查询。

用法：python tests/smoke_pet_client.py
"""

import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
PET_DAILY = Path(r'C:\Users\鲁释暄\Desktop\小蕾米AI助理\小蕾米AI助理\zzz_daily.py')
TEST_PORT = 23099


def main() -> int:
    venv_py = ENGINE_ROOT / '.venv' / 'Scripts' / 'python.exe'
    assert venv_py.exists(), 'venv 不存在'

    # ---- 1. 按桌宠的方式启动引擎进程（shim 模块路径） ----
    env = dict(os.environ)
    env['PYTHONPATH'] = str(ENGINE_ROOT / 'src')
    cmd = [str(venv_py), '-m', 'zzz_od.backend.entry.server',
           '--host', '127.0.0.1', '--port', str(TEST_PORT)]
    proc = subprocess.Popen(
        cmd, cwd=str(ENGINE_ROOT), env=env,
        creationflags=0x08000000,  # CREATE_NO_WINDOW，与桌宠一致
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(f'[冒烟] 引擎进程已启动 pid={proc.pid} cmd={" ".join(cmd)}')

    failures: list[str] = []
    try:
        # ---- 2. 等健康检查通过 ----
        ok = False
        for _ in range(30):
            if proc.poll() is not None:
                output = proc.stdout.read().decode('utf-8', 'replace')
                print('[冒烟] 进程提前退出:\n', output)
                return 1
            try:
                with urllib.request.urlopen(
                        f'http://127.0.0.1:{TEST_PORT}/health', timeout=2) as resp:
                    data = json.loads(resp.read())
                if data.get('ok') and data.get('server') == 'zzz_od':
                    ok = True
                    break
            except Exception:
                time.sleep(1)
        print(f'[冒烟] /health = {data}')
        if not ok:
            failures.append('健康检查未通过')
            return finish(failures)

        # ---- 3. 桌宠真实客户端代码连引擎 ----
        spec = importlib.util.spec_from_file_location('pet_zzz_daily', PET_DAILY)
        pet = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pet)

        cfg = {
            'engine_dir': str(ENGINE_ROOT),
            'host': '127.0.0.1',
            'port': TEST_PORT,
        }
        engine = pet.OneDragonEngine(cfg=cfg, data_dir=str(ENGINE_ROOT / 'debug'))

        installed = engine.is_installed()
        print(f'[冒烟] 桌宠 is_installed(engine_dir=迷你引擎) = {installed}')
        if not installed:
            failures.append('桌宠的已安装判据失败：需要 <root>/src/zzz_od 目录')

        apps = engine.applications()
        names = {a['app_id']: a['app_name'] for a in apps['applications']}
        print(f'[冒烟] 桌宠 applications() = {names} (instance {apps["current_instance_idx"]})')
        for need in ('coffee', 'daily_signin', 'random_play', 'engagement_reward'):
            if need not in names:
                failures.append(f'应用缺失: {need}')

        # 桌宠的关键词解析（快捷按钮依赖；注意入参是关键词列表）
        for keywords, expect in [(['coffee'], 'coffee'),
                                 (['签到'], 'daily_signin'),
                                 (['录像店'], 'random_play'),
                                 (['活跃'], 'engagement_reward')]:
            got = engine.resolve_app_id(keywords)
            mark = 'OK' if got == expect else f'期望 {expect} 实得 {got}'
            print(f'[冒烟] 关键词 {keywords} -> {got} [{mark}]')
            if got != expect:
                failures.append(f'关键词解析失败: {keywords}')

        win = engine.window_status()
        print(f'[冒烟] /game/window = {win}')
        if win.get('is_win_valid'):
            print(f'[冒烟] 真实游戏窗口: {win["width"]}x{win["height"]} '
                  f'(标准1080p: {win["is_win_scale"]})')

        status = engine.status()
        print(f'[冒烟] /game/status = {status}')
        if status.get('state') not in ('idle', 'success', 'failed', 'stopped'):
            failures.append(f'state 异常: {status.get("state")}')

        return finish(failures)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        print('[冒烟] 引擎进程已停止')


def finish(failures: list[str]) -> int:
    if failures:
        print('[冒烟] 失败项:')
        for f in failures:
            print('  -', f)
        return 1
    print('[冒烟] 全部通过 ✔')
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    sys.exit(main())
