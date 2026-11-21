# -*- coding: utf-8 -*-
"""
绝区零每日任务（小蕾米桌宠 × 一条龙引擎）
==========================================
引擎模式集成：本模块不包含任何 ZenlessZoneZero-OneDragon 源码（该项目为
GPL-3.0，保持进程隔离，桌宠自身代码不受其协议影响），只通过本机 HTTP
接口驱动「绝区零一条龙」的后端服务完成游戏内日常：

    刮刮卡 / 咖啡店 / 清体力(电量计划) / 每日活跃奖励，以及一条龙链上其余已启用任务

引擎（ZenlessZoneZero-OneDragon）需安装在本机，默认 D:\\ZenlessZoneZero-OneDragon，
可在 绝区零配置.json 中修改 engine_dir / port / launch_cmd。
首次使用请先用引擎自带界面完成一次引导（游戏路径、游戏画面设置检查），
之后桌宠即可一键执行。

引擎 HTTP 接口（默认 127.0.0.1:23001，见引擎 src/zzz_od/backend）：
    GET  /health                            探测服务是否就绪
    GET  /game/window                       游戏窗口状态
    GET  /game/applications                 可运行应用列表
    POST /game/run/one-dragon?block=false   启动完整一条龙（非阻塞）
    POST /game/run/standalone?app_id=x      启动单个应用（非阻塞）
    GET  /game/status                       运行状态（idle/running/success/failed/stopped）
    POST /game/stop                         停止当前运行

模块结构：
    OneDragonEngine   引擎客户端（HTTP + 进程管理），纯标准库，可脱离 Qt 使用
    ZzzDailyWindow    桌宠里的任务窗口（一键执行 / 单项执行 / 实时日志）
    命令行            python zzz_daily.py apps|chain|run <app_id>|status|stop
"""
import sys
import os
import json
import time
import subprocess
import urllib.request
import urllib.error
import urllib.parse

try:
    import yaml  # PyYAML：设置界面读写引擎配置文件用
except ImportError:
    yaml = None

ENGINE_STATE_TEXT = {
    'idle': '空闲',
    'running': '运行中',
    'success': '成功',
    'failed': '失败',
    'stopped': '已停止',
}

# 桌宠要暴露的日常任务（keywords 用于在引擎应用列表里自动匹配 app_id）
# 注：吼吼饼铺/刮刮卡/卦象集录在引擎 v2.5 里统一由 daily_signin 应用代理运行，
# 默认 selected_sign=hou_hou_bakery（吼吼饼铺）
TASKS = [
    {'key': 'coffee',     'label': '☕ 喝茶(咖啡店)',  'keywords': ['coffee']},
    {'key': 'signin',     'label': '🥐 吼吼饼铺抽奖',  'keywords': ['daily_signin', 'hou_hou']},
    {'key': 'video',      'label': '🎬 录像店经营',    'keywords': ['random_play']},
    {'key': 'engagement', 'label': '📅 领取活跃奖励',  'keywords': ['engagement']},
]

DEFAULT_CONFIG = {
    'engine_dir': r'D:\ZenlessZoneZero-OneDragon',
    'host': '127.0.0.1',
    'port': 23001,
    # 自定义引擎启动命令（列表，如 ["D:\\...\\runtime\\python.exe", "-m",
    # "zzz_od.backend.entry.server"]）；留空则自动探测
    'launch_cmd': [],
    # 首次连上引擎后自动记录的任务 app_id（key -> app_id）
    'resolved_app_ids': {},
}


def default_data_dir():
    """数据文件目录：打包 exe 时取 exe 所在目录，源码运行取本模块目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def load_config(data_dir=None):
    """读取 绝区零配置.json，缺失时用默认值生成"""
    data_dir = data_dir or default_data_dir()
    path = os.path.join(data_dir, '绝区零配置.json')
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    else:
        save_config(cfg, data_dir)
    return cfg


def save_config(cfg, data_dir=None):
    """保存 绝区零配置.json"""
    data_dir = data_dir or default_data_dir()
    path = os.path.join(data_dir, '绝区零配置.json')
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class OneDragonEngine:
    """一条龙引擎客户端：HTTP 调用 + 服务进程管理"""

    def __init__(self, cfg=None, data_dir=None):
        self.cfg = cfg or load_config(data_dir)
        self.data_dir = data_dir or default_data_dir()
        self._proc = None

    # ---------- 基础 ----------

    @property
    def base_url(self):
        return 'http://%s:%d' % (self.cfg.get('host', '127.0.0.1'),
                                 self.cfg.get('port', 23001))

    def _get(self, path, timeout=8):
        req = urllib.request.Request(self.base_url + path)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def _post(self, path, timeout=8):
        req = urllib.request.Request(self.base_url + path, data=b'', method='POST')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))

    # ---------- 服务进程 ----------

    def is_installed(self):
        engine_dir = self.cfg.get('engine_dir', '')
        return os.path.isdir(os.path.join(engine_dir, 'src', 'zzz_od'))

    def health(self):
        """引擎在线时返回 /health 内容，否则返回 None"""
        try:
            return self._get('/health', timeout=3)
        except Exception:
            return None

    def is_up(self):
        h = self.health()
        return bool(h and h.get('ok') and h.get('server') == 'zzz_od')

    def _find_runtime_python(self):
        """在引擎目录里找可用的 python.exe（uv 还原的 .venv 优先）"""
        engine_dir = self.cfg.get('engine_dir', '')
        candidates = [os.path.join(engine_dir, '.venv', 'Scripts', 'python.exe')]
        for root, dirs, files in os.walk(engine_dir):
            # 只往深处找 4 层，跳过工具/缓存目录，避免扫遍模型目录
            depth = os.path.relpath(root, engine_dir).count(os.sep)
            if depth >= 4:
                dirs[:] = []
                continue
            name = os.path.basename(root).lower()
            if name in ('.venv', '.tools', '.install'):
                dirs[:] = []
                continue
            if 'python.exe' in files:
                candidates.append(os.path.join(root, 'python.exe'))
        for path in candidates:
            if os.path.isfile(path):
                return path
        return None

    ENGINE_TASK_NAME = '小蕾米引擎服务'

    def _start_via_task(self):
        """用引擎的注册计划任务拉起（RL HIGHEST：免 UAC 且必定管理员提权）。

        引擎要求提权运行（游戏被 MOD 装载器以管理员启动时，普通权限进程的
        键鼠注入会被 Windows 静默拦截），而桌宠自身是普通权限：spawn 子进程
        会触发引擎的 UAC 自提权流程、子进程随即退出。计划任务没有这些问题。
        任务未注册（开发机/未跑过安装脚本）返回 False，走 spawn 兜底。
        """
        try:
            q = subprocess.run(['schtasks', '/Query', '/TN', self.ENGINE_TASK_NAME],
                               capture_output=True, timeout=15)
            if q.returncode != 0:
                return False
            r = subprocess.run(['schtasks', '/Run', '/TN', self.ENGINE_TASK_NAME],
                               capture_output=True, timeout=15)
            return r.returncode == 0
        except Exception:
            return False

    def launch(self):
        """启动引擎后端服务进程（重复调用安全：已在线则直接返回）"""
        if self.is_up():
            return True
        if not self.is_installed():
            raise RuntimeError('未找到一条龙引擎：%s' % self.cfg.get('engine_dir', ''))

        # 计划任务优先：免 UAC、必定提权、失败自动落到下面的 spawn 兜底
        if self._start_via_task():
            return True

        cmd = list(self.cfg.get('launch_cmd') or [])
        if not cmd:
            py = self._find_runtime_python()
            if py is None:
                raise RuntimeError('引擎目录里没有找到内嵌 Python，无法启动后端服务；'
                                   '请先打开一条龙主界面（会自动附带后端服务），'
                                   '或在 绝区零配置.json 的 launch_cmd 里手动指定启动命令')
            cmd = [py, '-m', 'zzz_od.backend.entry.server',
                   '--host', str(self.cfg.get('host', '127.0.0.1')),
                   '--port', str(self.cfg.get('port', 23001))]

        log_file = open(os.path.join(self.data_dir, '绝区零引擎服务.log'), 'ab')
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        # 引擎是 src-layout：必须把 src 加进 PYTHONPATH 才能导入 zzz_od
        env = os.environ.copy()
        env['PYTHONPATH'] = os.path.join(self.cfg.get('engine_dir', ''), 'src')
        self._proc = subprocess.Popen(
            cmd, cwd=self.cfg.get('engine_dir', '.'),
            stdout=log_file, stderr=subprocess.STDOUT,
            creationflags=flags, env=env)
        return True

    def wait_up(self, timeout=240, progress=None):
        """确保引擎在线：必要时启动进程并轮询 /health（首次加载模型可能较慢）"""
        if self.is_up():
            return True
        self.launch()
        deadline = time.time() + timeout
        child_gone_since = None
        while time.time() < deadline:
            if self.is_up():
                return True
            if self._proc is not None and self._proc.poll() is not None:
                # 子进程退出≠启动失败：引擎检测到需要管理员权限时会弹 UAC
                # 自提权，自己的子进程随即退出，真正的引擎以管理员另起进程
                # 接管端口（2026-10-15 实锤：之前把退出当失败，报"启动后
                # 立即退出了"）。给健康检查留 20 秒宽限，宽限内没起来才失败。
                if child_gone_since is None:
                    child_gone_since = time.time()
                elif time.time() - child_gone_since > 20:
                    raise RuntimeError('引擎服务进程已退出且健康检查未恢复，'
                                       '详见 绝区零引擎服务.log（UAC 弹窗若被'
                                       '拒绝，引擎无法以管理员启动）')
            if progress:
                progress('正在启动引擎… %ds' % int(deadline - time.time()))
            time.sleep(2)
        raise RuntimeError('引擎启动超时（%d 秒）' % timeout)

    # ---------- 游戏与应用 ----------

    def window_status(self):
        return self._get('/game/window')

    def applications(self):
        """返回 ApplicationListResult 字典（applications 列表含 app_id 等）"""
        return self._get('/game/applications')

    def resolve_app_id(self, keywords, apps=None):
        """按关键词在应用列表里找 app_id（结果缓存进配置文件）"""
        cached = self.cfg.get('resolved_app_ids', {})
        key = ','.join(keywords)
        apps = apps if apps is not None else self.applications().get('applications', [])
        for app in apps:
            app_id = app.get('app_id') or ''
            if app_id in cached.values() and key in cached and cached[key] == app_id:
                return app_id
        for app in apps:
            app_id = (app.get('app_id') or '').lower()
            name = (app.get('app_name') or '').lower()
            if any(kw in app_id or kw in name for kw in keywords):
                cached[key] = app.get('app_id')
                self.cfg['resolved_app_ids'] = cached
                save_config(self.cfg, self.data_dir)
                return app.get('app_id')
        return None

    def status(self):
        """返回运行状态字典：state/app/current_node/duration_seconds/last_status…"""
        try:
            return self._get('/game/status', timeout=4)
        except Exception:
            return {'state': 'offline'}

    def stop(self):
        return self._post('/game/stop')

    def stop_service(self):
        """停止引擎后端服务：找到监听本端口的进程并结束（无论由谁启动）"""
        port = str(self.cfg.get('port', 23001))
        try:
            run = subprocess.run(['netstat', '-ano', '-p', 'TCP'],
                                 capture_output=True, timeout=20)
            # 中文 Windows 的 netstat 输出是 GBK，头部本地文字直接忽略
            out = (run.stdout or b'').decode('utf-8', errors='ignore')
        except Exception:
            return False
        pids = set()
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[3] == 'LISTENING' \
                    and (parts[1].endswith(':' + port) or parts[2].endswith(':' + port)):
                pids.add(parts[4])
        for pid in pids:
            subprocess.run(['taskkill', '/F', '/PID', pid],
                           capture_output=True)
        self._proc = None
        if pids:
            time.sleep(1)
        return bool(pids)

    def restart_service(self, timeout=240, progress=None):
        """重启引擎后端服务（改完配置文件/更新代码后调用使其生效）。

        优先走引擎 /service/reload 热重启：免管理员权限，守卫脚本继承
        引擎自身的提权上下文。普通权限的桌宠 taskkill 杀不掉提权运行的
        引擎（拒绝访问），旧实现会静默假成功——配置/代码改动不生效
        （2026-10-07 排查确认）。热重启时序：旧进程约 2 秒后退出、守卫
        等端口释放后拉起新进程，因此先观察"下线"再等"上线"；10 秒内
        未见下线（引擎不在线或旧版本引擎无此接口）才回退杀进程兜底。
        """
        if progress:
            progress('正在通知引擎热重启…')
        try:
            self._post('/service/reload', timeout=5)
        except Exception:
            pass
        went_down = False
        deadline = time.time() + 10
        while time.time() < deadline:
            if not self.is_up():
                went_down = True
                break
            time.sleep(0.5)
        if went_down:
            if progress:
                progress('引擎已下线，等待新进程就绪…')
            deadline = time.time() + timeout
            while time.time() < deadline:
                if self.is_up():
                    if progress:
                        progress('引擎已重启，最新配置/代码已生效')
                    return True
                time.sleep(1)
            return False
        if progress:
            progress('热重启不可用（引擎不在线或引擎版本过旧），走兜底重启…')
        self.stop_service()
        if progress:
            progress('正在重新启动引擎…')
        self.wait_up(timeout=timeout, progress=progress)
        return True

    # ---------- 引擎配置文件（config/01/one_dragon/*.yml） ----------

    def config_path(self, rel):
        """实例配置路径：config/01/one_dragon/<rel>"""
        return os.path.join(self.cfg.get('engine_dir', ''),
                            'config', '01', 'one_dragon', rel)

    def read_config(self, rel):
        """读一个实例配置 yml（缺文件/无 PyYAML 时返回 None）"""
        if yaml is None:
            return None
        path = self.config_path(rel)
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return None

    def write_config(self, rel, data):
        """写一个实例配置 yml"""
        if yaml is None:
            raise RuntimeError('缺少 PyYAML，请先 pip install pyyaml')
        path = self.config_path(rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    def save_chain_enablement(self, enabled_map):
        """保存一条龙任务开关（保持现有顺序，仅更新 enabled 标志）"""
        rel = '_group.yml'
        data = self.read_config(rel) or {}
        app_list = data.get('app_list') or []
        seen = set()
        for item in app_list:
            app_id = item.get('app_id')
            if app_id in enabled_map:
                item['enabled'] = bool(enabled_map[app_id])
            seen.add(app_id)
        for app_id, enabled in enabled_map.items():
            if app_id not in seen:
                app_list.append({'app_id': app_id, 'enabled': bool(enabled)})
        data['app_list'] = app_list
        self.write_config(rel, data)

    def save_sign_choice(self, choice):
        """保存每日签到的目标（hou_hou_bakery / trigrams_collection / scratch_card）"""
        self.write_config('daily_signin.yml', {'selected_sign': choice})

    def save_charge_plan(self, category_name, plan_times):
        """保存体力计划（单条默认计划：实战模拟室-调查专项）"""
        plan = {
            'tab_name': '训练',
            'category_name': category_name,
            'mission_type_name': '基础材料',
            'mission_name': '调查专项',
            'level': '默认等级',
            'auto_battle_config': '全配队通用',
            'run_times': 0,
            'plan_times': int(plan_times),
            'card_num': '默认数量',
            'predefined_team_idx': -1,
            'notorious_hunt_buff_num': 1,
        }
        self.write_config('charge_plan.yml', {'plan_list': [plan]})

    def run_chain(self, block=False):
        """启动完整一条龙（block=True 时阻塞到结束，返回结果文本）"""
        path = '/game/run/one-dragon?block=%s' % ('true' if block else 'false')
        return self._post(path, timeout=3600 if block else 8)

    def run_standalone(self, app_id, block=False):
        """启动单个应用（block=True 时阻塞到结束）"""
        path = '/game/run/standalone?app_id=%s&block=%s' % (
            urllib.parse.quote(app_id), 'true' if block else 'false')
        return self._post(path, timeout=3600 if block else 8)

    def enter_game(self, block=False):
        """只打开并进入绝区零，不跑任何任务"""
        path = '/game/enter?block=%s' % ('true' if block else 'false')
        return self._post(path, timeout=1200 if block else 8)

    def run_and_wait(self, start, poll_interval=3, timeout=45 * 60, progress=None):
        """启动一次运行并等待结束。

        Args:
            start: 无参可调用对象，内部发起启动（run_chain / run_standalone）。
            progress: 可选回调，收到人话进度字符串。
        Returns:
            (成功?, 描述文本)
        """
        started = start()
        if not started.get('started', False):
            return False, started.get('error', '启动失败')
        deadline = time.time() + timeout
        last_node = None
        while time.time() < deadline:
            st = self.status()
            state = st.get('state')
            if progress and st.get('current_node') != last_node:
                last_node = st.get('current_node')
                progress('运行中：%s' % (last_node or '…'))
            if state in ('success', 'failed', 'stopped', 'idle'):
                ok = state == 'success'
                detail = st.get('last_status') or ENGINE_STATE_TEXT.get(state, state)
                return ok, detail
            time.sleep(poll_interval)
        return False, '等待运行结束超时'


# ---------- 桌宠窗口（依赖 PyQt6，命令行模式下不会导入） ----------


def open_daily_window(pet):
    """给桌宠用的入口：创建/聚焦任务窗口（自动启动引擎并刷新状态）"""
    from zzz_daily_window import ZzzDailyWindow
    win = getattr(pet, '_zzz_window', None)
    if win is not None:
        win.show()
        win.raise_()
        win.activateWindow()
        return win
    win = ZzzDailyWindow(pet)
    pet._zzz_window = win
    win.show()
    return win


if __name__ == '__main__':
    # 命令行模式（无 Qt）：可配合 Windows 计划任务做每日定时
    #   python zzz_daily.py apps              列出引擎应用
    #   python zzz_daily.py chain             跑一条龙并等待结束（退出码 0=成功）
    #   python zzz_daily.py run <app_id>      跑单个应用并等待结束
    #   python zzz_daily.py status|stop       查询状态 / 停止
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    engine = OneDragonEngine()
    action = sys.argv[1] if len(sys.argv) > 1 else 'status'

    if action == 'apps':
        infos = engine.applications().get('applications', [])
        for app in infos:
            print('%-24s %-14s 一条龙:%s 独立:%s  %s' % (
                app.get('app_id'), app.get('app_name'),
                '√' if app.get('enabled_in_one_dragon') else '×',
                '√' if app.get('in_standalone_list') else '×',
                (app.get('description') or '').splitlines()[0][:40]))
    elif action == 'chain':
        engine.wait_up()
        ok, msg = engine.run_and_wait(engine.run_chain,
                                      progress=lambda s: print(s, flush=True))
        print('一条龙：%s' % msg)
        sys.exit(0 if ok else 1)
    elif action == 'run':
        app_id = sys.argv[2]
        engine.wait_up()
        ok, msg = engine.run_and_wait(
            lambda: engine.run_standalone(app_id),
            progress=lambda s: print(s, flush=True))
        print('%s：%s' % (app_id, msg))
        sys.exit(0 if ok else 1)
    elif action == 'stop':
        print(engine.stop())
    else:
        st = engine.status()
        print(json.dumps(st, ensure_ascii=False, indent=2))
