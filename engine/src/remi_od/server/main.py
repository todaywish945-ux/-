"""HTTP 后端：标准库实现，兼容桌宠的 8 个路由契约。

桌宠侧请求特征：POST 发空 body（无 Content-Type），全部期待 JSON 响应。
启动：python -m remi_od.server.main --host 127.0.0.1 --port 23001
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from remi_od.core.log import log

# /health 的 server 字段必须是字面量 'zzz_od'——桌宠按它精确匹配判断引擎身份
SERVER_IDENTITY = 'zzz_od'


def make_handler(service) -> type:
    class Handler(BaseHTTPRequestHandler):

        def log_message(self, fmt: str, *args) -> None:
            pass  # 静默默认访问日志，业务日志自行打印

        # ---- 响应工具 ----

        def _json(self, data: dict, status: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _png(self, data: bytes) -> None:
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _not_found(self) -> None:
            self._json({'error': 'not found'}, 404)

        def _read_body(self) -> None:
            length = int(self.headers.get('Content-Length') or 0)
            if length:
                self.rfile.read(length)

        # ---- 分发 ----

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip('/') or '/'
            if path == '/health':
                self._json({'ok': True, 'server': SERVER_IDENTITY, 'ready': service.ready})
            elif path == '/game/window':
                self._json(service.window_status())
            elif path == '/game/applications':
                self._json(service.applications())
            elif path == '/game/status':
                self._json(service.status())
            elif path == '/game/capture':
                data = service.capture_png()
                if data is None:
                    self._json({'error': '无法截图（游戏窗口未找到）'}, 503)
                else:
                    self._png(data)
            elif path == '/debug/kbtest':
                self._json(service.debug_kbtest())
            else:
                self._not_found()

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip('/') or '/'
            query = parse_qs(parsed.query)
            self._read_body()
            block = _parse_block(query)

            if path == '/game/run/one-dragon':
                self._handle_run('one_dragon', '', block, '一条龙')
            elif path == '/game/run/standalone':
                app_id = (query.get('app_id') or [''])[0]
                if not app_id:
                    self._json({'started': False, 'error': '缺少 app_id'}, 400)
                    return
                self._handle_run('app', app_id, block, f'独立应用 {app_id}')
            elif path == '/game/enter':
                self._handle_run('enter', '', block, '进入游戏')
            elif path == '/game/stop':
                stopped, error = service.stop()
                if stopped:
                    self._json({'stopped': True, 'source': 'http'})
                else:
                    self._json({'stopped': False, 'error': error})
            elif path == '/game/run/visible':
                app_id = (query.get('app_id') or [''])[0]
                if not app_id:
                    self._json({'started': False, 'error': '缺少 app_id'}, 400)
                    return
                self._json(service.run_visible(app_id))
            elif path == '/service/reload':
                # 免 UAC 热重启：守卫脚本继承当前进程的提权上下文
                import os
                import subprocess
                import threading

                guard = Path(__file__).resolve().parents[3] / 'scripts' / 'serve_with_port_guard.py'
                self._json({'restarting': True})
                subprocess.Popen([sys.executable, str(guard)], close_fds=True)
                threading.Timer(2.0, os._exit, (0,)).start()
            else:
                self._not_found()

        def _handle_run(self, kind: str, app_id: str, block: bool, label: str) -> None:
            started, error = service.start_run(kind, app_id)
            if not started:
                self._json({'started': False, 'error': error, 'source': 'http',
                            'hint': '请等待当前运行结束或先停止'})
                return
            if block:
                result = service.wait_done()
                self._json({'result': result})
            else:
                self._json({
                    'started': True, 'source': 'http', 'app': label,
                    'started_at': service.ctx.run_state.started_at,
                    'hint': '进度请轮询 /game/status',
                })

    return Handler


def _parse_block(query: dict) -> bool:
    values = query.get('block') or ['false']
    return str(values[0]).lower() == 'true'


def serve(service, host: str = '127.0.0.1', port: int = 23001) -> ThreadingHTTPServer:
    handler = make_handler(service)
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def _self_elevate(args: list[str]) -> str:
    """非提权启动且配置要求提权时，弹 UAC 以管理员经守卫脚本重启。

    游戏以管理员运行时（MOD 环境常见），非提权引擎的键鼠注入会被 Windows
    静默拦截。必须经 serve_with_port_guard.py 重启而非直接跑本文件：脚本
    方式运行 main.py 时 sys.path 上没有 src，import remi_od 直接死
    （2026-10-15 实锤，进程零日志静默退出）；守卫会把 src 加进 sys.path、
    清理端口残留，并把 --host/--port 经 sys.argv 透传给本模块的 argparse。
    返回 'already'（已是管理员）/ 'relaunched'（已触发提权重启）/
    'declined'（用户拒绝了 UAC）。
    """
    import ctypes

    if ctypes.windll.shell32.IsUserAnAdmin():
        return 'already'
    params = ' '.join(args)
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, 'runas', sys.executable, f'"{_GUARD_SCRIPT}" {params}'.strip(),
        None, 0)
    return 'relaunched' if ret > 32 else 'declined'


_GUARD_SCRIPT = str(Path(__file__).resolve().parents[3]
                    / 'scripts' / 'serve_with_port_guard.py')


def main() -> None:
    import argparse

    from remi_od.core import config as config_mod
    from remi_od.core.context import EngineContext
    from remi_od.core.log import log
    from remi_od.server.service import EngineService

    parser = argparse.ArgumentParser(description='小蕾米引擎 HTTP 后端')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=23001)
    args = parser.parse_args()

    # 引擎根 = src/ 的上一级（src/remi_od/server/main.py → 上三级）
    engine_root = Path(__file__).resolve().parents[3]

    # 提权自愈：游戏提权运行的机器上，引擎必须同级提权
    account = config_mod.load_yaml(engine_root / 'config' / '01' / 'game_account.yml', {}) or {}
    if account.get('require_elevation', False):
        outcome = _self_elevate(['--host', args.host, '--port', str(args.port)])
        if outcome == 'relaunched':
            log('服务', '非提权启动，已请求管理员权限重启（请在 UAC 窗口点"是"）')
            return
        if outcome == 'declined':
            log('服务', '未获得管理员权限，退出（游戏以管理员运行时引擎必须提权，'
                       '否则键鼠注入会被系统静默拦截）')
            sys.exit(1)

    from remi_od.control.screenshot import enable_dpi_awareness

    enable_dpi_awareness()

    ctx = EngineContext(engine_root)
    ctx.init()

    # OCR 模型预热（首次调用含模型加载，提前到服务启动而非首个任务）
    try:
        import numpy as np

        ctx.ocr.ocr(np.zeros((64, 64, 3), dtype=np.uint8))
    except Exception:
        pass

    service = EngineService(ctx)
    service.ready = True

    server = serve(service, args.host, args.port)
    log('服务', f'启动 {args.host}:{args.port} root={engine_root}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        log('服务', '已退出')


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    main()
