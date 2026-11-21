# -*- coding: utf-8 -*-
"""Agent 工具循环：让小蕾米能"动手"——操作绝区零引擎、设定提醒、做表情、报时等。

实现：OpenAI 兼容 function calling（glm-4-flash 支持工具调用，免费）。
AgentWorker 在后台线程跑"模型 → 工具 → 模型"循环，最多 MAX_ROUNDS 轮。
触碰 GUI 的工具（闹钟/表情）经 MainCaller 排队回主线程执行——
QThread 里直接碰 Qt 对象会崩。
"""
import base64
import ctypes
import json
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

from PyQt6.QtCore import Qt, QMetaObject, QThread, QObject, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

AGENT_PROMPT_SUFFIX = (
    '\n\n# 工具使用规则\n'
    '- 你有一批可调用的工具。涉及现实信息（现在几点、引擎状态、游戏画面、'
    '提醒列表）时必须调工具获取，绝不凭空编造。\n'
    '- run_daily / run_app 会真的操控游戏：调用前必须先用一句话向用户确认，'
    '用户明确同意（说"跑吧/开始/来一杯"等）才能调。\n'
    '- 引擎不在线时，提醒用户先开游戏、确认引擎服务在跑，不要连续重试。\n'
    '- 工具返回的结果要用小蕾米的口吻转述，保持 100 字以内。'
)

# 引擎支持的日常应用（app_id → 中文名），run_app 的合法入参
ENGINE_APPS = {
    'daily_signin': '每日签到', 'coffee': '咖啡',
    'random_play': '录像店营业', 'engagement_reward': '活跃奖励',
}

TOOL_LABELS = {
    'now': '看看时间…', 'engine_status': '查看引擎状态…',
    'engine_window': '检查游戏窗口…', 'run_daily': '启动一条龙…',
    'run_app': '启动日常任务…', 'stop_engine': '停止引擎任务…',
    'describe_game_screen': '看一眼游戏画面…', 'add_clock': '设置闹钟…',
    'add_countdown': '设置倒计时…', 'list_reminders': '翻一下提醒列表…',
    'remove_reminder': '删掉提醒…', 'pet_emote': '做个表情…',
    'set_volume': '调音量…', 'open_url': '打开网页…',
}

TOOLS_SCHEMA = [
    {'type': 'function', 'function': {
        'name': 'now',
        'description': '获取当前日期时间和星期（回答任何时间相关问题前先调用）',
        'parameters': {'type': 'object', 'properties': {}}},
    },
    {'type': 'function', 'function': {
        'name': 'engine_status',
        'description': '查询绝区零引擎当前状态：是否在跑任务、跑的哪个、进行到哪一步',
        'parameters': {'type': 'object', 'properties': {}}},
    },
    {'type': 'function', 'function': {
        'name': 'engine_window',
        'description': '检查绝区零游戏窗口是否开着、是否前台、分辨率是否标准',
        'parameters': {'type': 'object', 'properties': {}}},
    },
    {'type': 'function', 'function': {
        'name': 'run_daily',
        'description': '启动绝区零一条龙日常（签到+咖啡+录像店+活跃奖励，按需自动执行）。'
                       '启动前必须先向用户确认！',
        'parameters': {'type': 'object', 'properties': {}}},
    },
    {'type': 'function', 'function': {
        'name': 'run_app',
        'description': '启动单个绝区零日常任务。启动前必须先向用户确认！',
        'parameters': {'type': 'object', 'properties': {
            'app_id': {'type': 'string', 'enum': list(ENGINE_APPS),
                       'description': '任务：daily_signin=签到 coffee=咖啡 '
                                      'random_play=录像店 engagement_reward=活跃奖励'},
        }, 'required': ['app_id']}},
    },
    {'type': 'function', 'function': {
        'name': 'stop_engine',
        'description': '停止引擎正在执行的任务',
        'parameters': {'type': 'object', 'properties': {}}},
    },
    {'type': 'function', 'function': {
        'name': 'describe_game_screen',
        'description': '截一张绝区零游戏画面并用视觉模型描述当前界面',
        'parameters': {'type': 'object', 'properties': {
            'prompt': {'type': 'string', 'description': '想重点了解什么，可选'},
        }},
    }},
    {'type': 'function', 'function': {
        'name': 'add_clock',
        'description': '添加一个闹钟：到指定时刻弹窗提醒',
        'parameters': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': '提醒内容'},
            'hour': {'type': 'integer'}, 'minute': {'type': 'integer'},
            'daily': {'type': 'boolean', 'description': '是否每天重复'},
        }, 'required': ['hour', 'minute']},
    }},
    {'type': 'function', 'function': {
        'name': 'add_countdown',
        'description': '添加一个倒计时：N 分钟后弹窗提醒',
        'parameters': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': '提醒内容'},
            'minutes': {'type': 'integer'},
        }, 'required': ['name', 'minutes']},
    }},
    {'type': 'function', 'function': {
        'name': 'list_reminders',
        'description': '列出当前所有闹钟和倒计时',
        'parameters': {'type': 'object', 'properties': {}}},
    },
    {'type': 'function', 'function': {
        'name': 'remove_reminder',
        'description': '按 id 删除一个提醒（id 来自 list_reminders）',
        'parameters': {'type': 'object', 'properties': {
            'reminder_id': {'type': 'integer'},
        }, 'required': ['reminder_id']},
    }},
    {'type': 'function', 'function': {
        'name': 'pet_emote',
        'description': '让桌宠做一个表情，几秒后自动恢复待机',
        'parameters': {'type': 'object', 'properties': {
            'emotion': {'type': 'string', 'enum': ['得意', '思考', '期待', '待机']},
        }, 'required': ['emotion']},
    }},
    {'type': 'function', 'function': {
        'name': 'set_volume',
        'description': '调整系统音量（up 调大/down 调小/mute 静音）',
        'parameters': {'type': 'object', 'properties': {
            'action': {'type': 'string', 'enum': ['up', 'down', 'mute']},
        }, 'required': ['action']},
    }},
    {'type': 'function', 'function': {
        'name': 'open_url',
        'description': '用默认浏览器打开一个 http/https 网页。仅在用户明确给出或要求打开网址时使用',
        'parameters': {'type': 'object', 'properties': {
            'url': {'type': 'string'},
        }, 'required': ['url']},
    }},
]

VK_VOLUME = {'mute': 0xAD, 'down': 0xAE, 'up': 0xAF}


# ---------- 主线程执行器 ----------

class MainCaller(QObject):
    """把 callable 派发到主线程执行并同步等待结果。

    用 QTimer.singleShot(msec, context, callable) 的 context 重载保证
    callable 在主线程事件循环里跑（context 已 moveToThread 主线程）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.moveToThread(QApplication.instance().thread())
        self._pending = None
        self._evt = None
        self._out = ('err', '未执行')

    @pyqtSlot()
    def _run(self):
        try:
            self._out = ('ok', self._pending())
        except Exception as e:
            self._out = ('err', str(e))
        if self._evt is not None:
            self._evt.set()

    def call(self, fn, timeout=10):
        self._pending = fn
        self._evt = threading.Event()
        # 队列投递到主线程事件循环执行 _run（self 已 moveToThread 主线程）
        QMetaObject.invokeMethod(self, '_run', Qt.ConnectionType.QueuedConnection)
        if not self._evt.wait(timeout):
            return ('err', '主线程执行超时')
        return self._out


# ---------- 工具实现（全部返回字符串给模型） ----------

_engine_inst = None


def _engine():
    """懒加载桌宠目录自带的引擎客户端（zzz_daily.OneDragonEngine）"""
    global _engine_inst
    if _engine_inst is None:
        import zzz_daily
        _engine_inst = zzz_daily.OneDragonEngine()
    return _engine_inst


def _engine_ok():
    eng = _engine()
    if not eng.is_up():
        return None, '引擎不在线：请先开游戏、确认引擎服务已启动（桌宠设置里可查看）'
    return eng, None


def tool_now():
    return time.strftime('现在：%Y-%m-%d %H:%M:%S ' + ['周一', '周二', '周三', '周四',
                                                      '周五', '周六', '周日'][time.localtime().tm_wday])


VOLUME_REPLY = {'up': '音量已调大', 'down': '音量已调小', 'mute': '已切换静音'}


def tool_volume(action):
    if action not in VOLUME_REPLY:
        return '无效的音量操作'
    if sys.platform.startswith('win'):
        vk = VK_VOLUME[action]
        presses = 1 if action == 'mute' else 5
        for _ in range(presses):
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP
            time.sleep(0.02)
        return VOLUME_REPLY[action]
    if sys.platform.startswith('linux'):
        # Linux：优先 pactl（PulseAudio/PipeWire 均支持），回退 amixer（纯 ALSA）
        pactl_cmd = {
            'up':   ['pactl', 'set-sink-volume', '@DEFAULT_SINK@', '+10%'],
            'down': ['pactl', 'set-sink-volume', '@DEFAULT_SINK@', '-10%'],
            'mute': ['pactl', 'set-sink-mute', '@DEFAULT_SINK@', 'toggle'],
        }[action]
        amixer_cmd = {
            'up':   ['amixer', '-q', 'set', 'Master', '10%+', 'unmute'],
            'down': ['amixer', '-q', 'set', 'Master', '10%-', 'unmute'],
            'mute': ['amixer', '-q', 'set', 'Master', 'toggle'],
        }[action]
        for cmd in (pactl_cmd, amixer_cmd):
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=5)
                if r.returncode == 0:
                    return VOLUME_REPLY[action]
            except OSError:  # 命令不存在，试下一个
                continue
        return '无法调整音量：未找到 pactl 或 amixer 命令'
    return '当前系统不支持音量调节'


def tool_open_url(url):
    url = str(url).strip()
    if not (url.startswith('http://') or url.startswith('https://')):
        return '只支持 http/https 网址'
    webbrowser.open(url)
    return '已在浏览器打开 ' + url


def tool_engine_status():
    eng, err = _engine_ok()
    if err:
        return err
    return json.dumps(eng._get('/game/status'), ensure_ascii=False)


def tool_engine_window():
    eng, err = _engine_ok()
    if err:
        return err
    return json.dumps(eng._get('/game/window'), ensure_ascii=False)


def tool_run_daily():
    eng, err = _engine_ok()
    if err:
        return err
    r = eng._post('/game/run/one-dragon', timeout=15)
    if r.get('started'):
        return '一条龙已启动，可用 engine_status 查询进度'
    return '启动失败：' + str(r.get('error') or r)


def tool_run_app(app_id):
    app_id = str(app_id).strip()
    if app_id not in ENGINE_APPS:
        return '未知任务 ' + app_id + '，可选：' + '、'.join(
            '%s=%s' % kv for kv in ENGINE_APPS.items())
    eng, err = _engine_ok()
    if err:
        return err
    r = eng._post('/game/run/standalone?app_id=' + app_id, timeout=15)
    if r.get('started'):
        return ENGINE_APPS[app_id] + '已启动，可用 engine_status 查询进度'
    return '启动失败：' + str(r.get('error') or r)


def tool_stop_engine():
    eng, err = _engine_ok()
    if err:
        return err
    r = eng._post('/game/stop', timeout=15)
    if r.get('stopped'):
        return '已停止当前任务'
    return '没有在跑的任务，或停止失败：' + str(r.get('error') or r)


def tool_describe_game_screen(pet, prompt):
    eng, err = _engine_ok()
    if err:
        return err
    try:
        with urllib.request.urlopen(eng.base_url + '/game/capture', timeout=15) as resp:
            png = resp.read()
    except Exception as e:
        return '截图失败：' + str(e)
    if not png:
        return '截图为空（游戏窗口可能没开）'
    b64 = base64.b64encode(png).decode('ascii')
    text = (prompt or '描述绝区零当前画面：在什么界面或地点、有什么可交互元素。') + ' 100 字内。'
    payload = json.dumps({
        'model': pet.ai_config.get('vision_model', 'glm-4v-flash'),
        'messages': [{'role': 'user', 'content': [
            {'type': 'image_url', 'image_url': {'url': b64}},
            {'type': 'text', 'text': text},
        ]}],
        'stream': False,
    }).encode('utf-8')
    req = urllib.request.Request(
        pet.ai_config.get('base_url', '').rstrip('/') + '/chat/completions',
        data=payload, method='POST')
    req.add_header('Content-Type', 'application/json')
    if pet.ai_config.get('api_key'):
        req.add_header('Authorization', 'Bearer ' + pet.ai_config['api_key'])
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    return data['choices'][0]['message']['content']


# ---------- Agent 循环 ----------

class AgentWorker(QThread):
    """后台跑"模型→工具→模型"循环；finished(content, error) 给最终回复，
    activity(中文短语) 汇报工具动态（聊窗里显示"正在查看引擎状态…"）。"""

    finished = pyqtSignal(str, str)
    activity = pyqtSignal(str)

    MAX_ROUNDS = 6

    def __init__(self, config, messages, pet, parent=None):
        super().__init__(parent)
        self._config = config
        self._messages = list(messages)
        self._pet = pet
        self._caller = MainCaller()

    # ---- 工具分派 ----

    def _execute(self, name, args):
        try:
            if name == 'now':
                return tool_now()
            if name == 'engine_status':
                return tool_engine_status()
            if name == 'engine_window':
                return tool_engine_window()
            if name == 'run_daily':
                return tool_run_daily()
            if name == 'run_app':
                return tool_run_app(args.get('app_id'))
            if name == 'stop_engine':
                return tool_stop_engine()
            if name == 'describe_game_screen':
                return tool_describe_game_screen(self._pet, args.get('prompt'))
            if name == 'set_volume':
                return tool_volume(args.get('action'))
            if name == 'open_url':
                return tool_open_url(args.get('url'))
        except Exception as e:
            return '工具执行出错：' + str(e)
        # 以下需要主线程（触碰 Qt 对象）
        pet = self._pet

        def _alarm_mgr():
            return pet.alarm_manager

        if name == 'add_clock':
            ok, out = self._caller.call(lambda: (
                _alarm_mgr().add_clock(str(args.get('name') or '提醒'),
                                       int(args.get('hour', 0)),
                                       int(args.get('minute', 0)),
                                       bool(args.get('daily'))),
                '闹钟已设好：每天' if args.get('daily') else '闹钟已设好：')[1]
                + '%02d:%02d' % (int(args.get('hour', 0)), int(args.get('minute', 0))),
                timeout=10)
            return out if ok else '设置失败：' + out
        if name == 'add_countdown':
            minutes = int(args.get('minutes', 1))
            ok, out = self._caller.call(lambda: (
                _alarm_mgr().add_countdown(str(args.get('name') or '提醒'), minutes),
                '倒计时已设好：%d 分钟' % minutes)[1], timeout=10)
            return out if ok else '设置失败：' + out
        if name == 'list_reminders':
            ok, out = self._caller.call(lambda: json.dumps(
                _alarm_mgr().alarms, ensure_ascii=False), timeout=10)
            return out if ok else '读取失败：' + out
        if name == 'remove_reminder':
            rid = int(args.get('reminder_id', 0))
            ok, out = self._caller.call(lambda: _alarm_mgr().remove(rid) or '已删除',
                                        timeout=10)
            return out if ok else '删除失败：' + out
        if name == 'pet_emote':
            idx = {'得意': 1, '思考': 2, '期待': 4, '待机': 0}.get(args.get('emotion'), 1)

            def _emote():
                pet.switch_to_gif(idx)
                if idx != 0:
                    pet.click_recovery_timer.start(5000)  # 5 秒后自动回待机

            ok, out = self._caller.call(_emote, timeout=10)
            return ('小蕾米做了「%s」的表情' % args.get('emotion')) if ok \
                else '表情切换失败：' + out
        return '未知工具 ' + name

    # ---- 模型请求 ----

    def _chat(self, messages):
        payload = json.dumps({
            'model': self._config.get('model', 'glm-4-flash'),
            'messages': messages,
            'tools': TOOLS_SCHEMA,
            'tool_choice': 'auto',
            'stream': False,
        }).encode('utf-8')
        req = urllib.request.Request(
            self._config.get('base_url', '').rstrip('/') + '/chat/completions',
            data=payload, method='POST')
        req.add_header('Content-Type', 'application/json')
        if self._config.get('api_key'):
            req.add_header('Authorization', 'Bearer ' + self._config['api_key'])
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        return data['choices'][0]['message']

    def run(self):
        try:
            content = self._loop()
            self.finished.emit(content, '')
        except Exception as e:
            self.finished.emit('', str(e))

    def _loop(self):
        messages = list(self._messages)
        if messages and messages[0].get('role') == 'system':
            messages[0] = dict(messages[0])
            messages[0]['content'] = (messages[0].get('content') or '') + AGENT_PROMPT_SUFFIX
        for _ in range(self.MAX_ROUNDS):
            msg = self._chat(messages)
            tool_calls = msg.get('tool_calls') or []
            if not tool_calls:
                return msg.get('content') or '（小蕾米走神了，再说一遍？）'
            assistant = {'role': 'assistant',
                         'content': msg.get('content') or '',
                         'tool_calls': tool_calls}
            messages.append(assistant)
            for tc in tool_calls:
                fname = tc.get('function', {}).get('name', '')
                self.activity.emit(TOOL_LABELS.get(fname, fname))
                try:
                    args = json.loads(tc.get('function', {}).get('arguments') or '{}')
                except Exception:
                    args = {}
                result = self._execute(fname, args)
                messages.append({'role': 'tool', 'tool_call_id': tc.get('id', ''),
                                 'content': str(result)})
        return '工具轮次用完了，先说到这里，有需要再喊我～'
