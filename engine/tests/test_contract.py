"""HTTP 契约测试：用桌宠同款请求方式（urllib、POST 空 body）打全部路由。"""

import json
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from remi_od.core.context import EngineContext
from remi_od.server.main import serve
from remi_od.server.service import EngineService


class _SlowController:

    """假控制器：截图慢（让运行持续一会儿），无游戏窗口。"""

    def __init__(self, delay: float = 1.5):
        self.delay = delay
        self.automatic = False
        self.screenshot_calls = 0

    def screenshot(self):
        self.screenshot_calls += 1
        time.sleep(self.delay)
        return None

    def is_window_ready(self) -> bool:
        return False

    def find_game_window(self):
        return None

    def window_status(self) -> dict:
        return {'win_title': '', 'is_win_valid': False, 'is_win_active': False,
                'is_win_scale': False, 'x': 0, 'y': 0, 'width': 0, 'height': 0}

    def click(self, *args, **kwargs):
        return False


class _Client:

    """复刻桌宠 zzz_daily 的请求风格。"""

    def __init__(self, port: int):
        self.base = f'http://127.0.0.1:{port}'

    def get(self, path: str, timeout: float = 5) -> dict:
        with urllib.request.urlopen(self.base + path, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def post_empty(self, path: str, timeout: float = 8) -> dict:
        req = urllib.request.Request(self.base + path, data=b'', method='POST')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))


@pytest.fixture()
def server(tmp_path: Path):
    ctx = EngineContext(tmp_path)
    ctx.init()
    ctx.controller = _SlowController()
    service = EngineService(ctx)
    service.ready = True
    httpd = serve(service, '127.0.0.1', 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield service, _Client(httpd.server_address[1])
    httpd.shutdown()
    httpd.server_close()


def test_health_identity(server):
    _, client = server
    data = client.get('/health')
    # 桌宠 is_up 要求 ok==True 且 server=='zzz_od'（精确匹配）
    assert data['ok'] is True
    assert data['server'] == 'zzz_od'
    assert data['ready'] is True


def test_window_status(server):
    _, client = server
    data = client.get('/game/window')
    for key in ('win_title', 'is_win_valid', 'is_win_active', 'is_win_scale',
                'x', 'y', 'width', 'height'):
        assert key in data


def test_applications(server):
    _, client = server
    data = client.get('/game/applications')
    assert 'current_instance_idx' in data
    ids = [a['app_id'] for a in data['applications']]
    # 桌宠 4 个快捷按钮关键词依赖的 app_id 必须在列
    for expected in ('coffee', 'daily_signin', 'random_play', 'engagement_reward',
                     'one_dragon'):
        assert expected in ids
    for app in data['applications']:
        for key in ('app_id', 'app_name', 'description',
                    'enabled_in_one_dragon', 'in_standalone_list'):
            assert key in app
    # 默认配置全启用
    enabled = {a['app_id']: a['enabled_in_one_dragon'] for a in data['applications']}
    assert enabled['daily_signin'] is True


def test_status_idle(server):
    _, client = server
    data = client.get('/game/status')
    assert data['state'] == 'idle'
    for key in ('app', 'current_node', 'retry_count', 'last_status',
                'failed_node', 'duration_seconds', 'started_at', 'source'):
        assert key in data


def test_run_one_dragon_nonblocking_and_stop(server):
    service, client = server
    started = client.post_empty('/game/run/one-dragon?block=false')
    assert started['started'] is True

    # 并发拒绝
    conflict = client.post_empty('/game/run/one-dragon?block=false')
    assert conflict['started'] is False
    assert conflict['error'] == '已有运行在进行中'

    status = client.get('/game/status')
    assert status['state'] == 'running'
    assert status['app'] == '一条龙'

    # 停止 → 终态 stopped
    stopped = client.post_empty('/game/stop')
    assert stopped['stopped'] is True
    deadline = time.time() + 15
    while time.time() < deadline:
        status = client.get('/game/status')
        if status['state'] == 'stopped':
            break
        time.sleep(0.3)
    assert status['state'] == 'stopped'

    # 无运行时停止要拒绝
    again = client.post_empty('/game/stop')
    assert again['stopped'] is False
    assert '当前无运行' in again['error']


def test_run_standalone_and_enter(server):
    service, client = server
    started = client.post_empty('/game/run/standalone?app_id=daily_signin&block=false')
    assert started['started'] is True
    client.post_empty('/game/stop')
    _wait_terminal(client)

    started = client.post_empty('/game/enter?block=false')
    assert started['started'] is True
    client.post_empty('/game/stop')
    _wait_terminal(client)

    bad = client.post_empty(
        '/game/run/standalone?app_id=' + urllib.parse.quote('不存在的') + '&block=false')
    assert bad['started'] is True  # 启动成功，运行内判定失败
    _wait_terminal(client)
    status = client.get('/game/status')
    assert status['state'] == 'failed'


def test_run_block_mode(server):
    service, client = server
    data = client.post_empty('/game/run/standalone?app_id=coffee&block=true',
                             timeout=120)
    assert 'result' in data


def _wait_terminal(client: _Client, timeout: float = 20) -> str:
    deadline = time.time() + timeout
    state = ''
    while time.time() < deadline:
        state = client.get('/game/status')['state']
        if state in ('success', 'failed', 'stopped'):
            return state
        time.sleep(0.3)
    raise AssertionError(f'等待终态超时，当前 {state}')
