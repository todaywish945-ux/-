# -*- coding: utf-8 -*-
"""
绝区零每日任务窗口（小蕾米桌宠 · 自带启动器）
==========================================
桌宠自身就是「启动器」：启动/重启引擎后端、任务开关、签到方式、体力计划
全部在本窗口完成（直接读写引擎配置文件），不需要打开一条龙自带的界面。

依赖 PyQt6、PyYAML 与 zzz_daily.OneDragonEngine。所有 HTTP/进程/文件操作
放在后台线程，界面只由 QTimer 轮询刷新（与 pet.py 同一套模式），不会卡 UI。
"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QPlainTextEdit, QCheckBox, QRadioButton,
                             QSpinBox, QComboBox, QDialogButtonBox, QGroupBox)
from PyQt6.QtCore import Qt, QTimer

import time

from zzz_daily import OneDragonEngine, TASKS, ENGINE_STATE_TEXT

# 每日签到的三种目标（value 与引擎 daily_signin 配置的 selected_sign 对应）
SIGN_CHOICES = [
    ('hou_hou_bakery', '🥐 吼吼饼铺'),
    ('trigrams_collection', '☯ 卦象集录'),
    ('scratch_card', '🎰 刮刮卡'),
]

# 体力计划支持的副本类型（单条默认计划：基础材料-调查专项）
CHARGE_CATEGORIES = ['实战模拟室', '区域巡防', '专业挑战室', '恶名狩猎']

def _foreground_game_window():
    """把绝区零窗口切到前台并置顶（前台模拟操作要求游戏在前台，
    否则点击会落到遮挡游戏的其他窗口上）"""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, '绝区零')
        if not hwnd:
            return False
        user32.ShowWindow(hwnd, 9)      # SW_RESTORE 还原最小化
        # ALT 技巧绕过 Windows 前台锁
        user32.keybd_event(0x12, 0, 0, 0)
        user32.SetForegroundWindow(hwnd)
        user32.keybd_event(0x12, 0, 2, 0)
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0010)  # TOPMOST + NOMOVE + NOSIZE
        user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0010)  # NOTOPMOST（恢复，但已在最前）
        return True
    except Exception:
        pass
    return False


# 运行节点 → 玩家人话提示（避免黑屏/静止画面被当成卡死）
NODE_HINTS = {
    '打开游戏': '🎮 正在启动游戏…（首次启动约1分钟）',
    '进入游戏': '🎮 正在登录进游戏…（黑屏/静止1~5分钟属正常，请勿动键鼠）',
}


class ZzzSettingsDialog(QDialog):
    """任务设置：一条龙任务开关 / 签到方式 / 体力计划（保存即写引擎配置）"""

    def __init__(self, engine, apps, parent=None):
        super().__init__(parent)
        self._engine = engine
        self.setWindowTitle('绝区零任务设置 · 小蕾米')
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        # ---- 一条龙任务开关 ----
        task_box = QGroupBox('一条龙执行的任务（勾选 = 启用，顺序即执行顺序）')
        task_layout = QVBoxLayout(task_box)
        self._task_checks = {}
        for app in apps:
            app_id = app.get('app_id')
            if app_id in ('one_dragon', 'notify'):
                continue
            cb = QCheckBox(app.get('app_name') or app_id)
            cb.setChecked(bool(app.get('enabled_in_one_dragon')))
            cb.setToolTip((app.get('description') or '').splitlines()[0][:60])
            self._task_checks[app_id] = cb
            task_layout.addWidget(cb)
        layout.addWidget(task_box)

        # ---- 签到方式 ----
        sign_box = QGroupBox('每日签到方式')
        sign_layout = QVBoxLayout(sign_box)
        current_sign = (engine.read_config('daily_signin.yml') or {}) \
            .get('selected_sign', 'hou_hou_bakery')
        self._sign_radios = {}
        for value, label in SIGN_CHOICES:
            rb = QRadioButton(label)
            rb.setChecked(value == current_sign)
            self._sign_radios[value] = rb
            sign_layout.addWidget(rb)
        layout.addWidget(sign_box)

        # ---- 体力计划 ----
        charge_box = QGroupBox('体力刷本计划（每日把电量刷完）')
        charge_layout = QHBoxLayout(charge_box)
        plan_cfg = engine.read_config('charge_plan.yml') or {}
        plans = plan_cfg.get('plan_list') or []
        first = plans[0] if plans else {}
        self._charge_category = QComboBox()
        self._charge_category.addItems(CHARGE_CATEGORIES)
        category = first.get('category_name', '实战模拟室')
        if category in CHARGE_CATEGORIES:
            self._charge_category.setCurrentText(category)
        self._charge_times = QSpinBox()
        self._charge_times.setRange(1, 10)
        self._charge_times.setValue(int(first.get('plan_times', 1) or 1))
        charge_layout.addWidget(QLabel('副本：'))
        charge_layout.addWidget(self._charge_category)
        charge_layout.addWidget(QLabel('每次运行刷几把：'))
        charge_layout.addWidget(self._charge_times)
        charge_layout.addStretch(1)
        layout.addWidget(charge_box)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存并应用')
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        """写引擎配置文件（调用方负责重启引擎使配置生效）"""
        enabled_map = {app_id: cb.isChecked()
                       for app_id, cb in self._task_checks.items()}
        self._engine.save_chain_enablement(enabled_map)
        for value, rb in self._sign_radios.items():
            if rb.isChecked():
                self._engine.save_sign_choice(value)
                break
        self._engine.save_charge_plan(
            self._charge_category.currentText(), self._charge_times.value())
        self.accept()


class ZzzDailyWindow(QDialog):
    """绝区零每日任务窗口：一键日常 / 单项执行 / 任务设置 / 实时日志"""

    def __init__(self, pet=None):
        super().__init__()
        self._pet = pet
        self._engine = OneDragonEngine()
        self._busy = False          # 有任务在跑（后台线程）
        self._result = None         # 线程结束后写入 (ok, msg)
        self._last_node = None      # 去重日志用的当前节点
        self._worker = None
        self._note = ''             # 线程写入的一句话进度
        self._engine_error = None
        self._apps = None
        self._need_refresh_chain = False

        self.setWindowTitle('绝区零每日任务 · 小蕾米')
        self.setMinimumSize(520, 440)

        layout = QVBoxLayout(self)

        self._engine_label = QLabel('引擎：检测中…')
        layout.addWidget(self._engine_label)
        self._game_label = QLabel('游戏窗口：—')
        layout.addWidget(self._game_label)
        self._chain_label = QLabel('一条龙任务清单：—')
        self._chain_label.setWordWrap(True)
        layout.addWidget(self._chain_label)

        row = QHBoxLayout()
        self._settings_btn = QPushButton('⚙ 任务设置')
        self._settings_btn.clicked.connect(self.open_settings)
        row.addWidget(self._settings_btn)
        self._enter_btn = QPushButton('🕹 进入游戏')
        self._enter_btn.setToolTip('只启动并进入游戏，不跑任务')
        self._enter_btn.clicked.connect(self.enter_game)
        row.addWidget(self._enter_btn)
        self._run_btn = QPushButton('🎮 一键日常（一条龙）')
        self._run_btn.clicked.connect(self.start_chain)
        row.addWidget(self._run_btn)
        self._stop_btn = QPushButton('⛔ 停止')
        self._stop_btn.clicked.connect(self.stop_run)
        row.addWidget(self._stop_btn)
        layout.addLayout(row)

        task_row = QHBoxLayout()
        self._task_buttons = {}
        for task in TASKS:
            btn = QPushButton(task['label'])
            btn.setToolTip('以"独立应用"方式只跑这一项')
            btn.clicked.connect(lambda checked=False, t=task: self.start_task(t))
            self._task_buttons[task['key']] = btn
            task_row.addWidget(btn)
        layout.addLayout(task_row)

        self._note_label = QLabel('')
        layout.addWidget(self._note_label)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        layout.addWidget(self._log)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(1500)

        self._set_busy(False)
        self.log('引擎目录：%s' % self._engine.cfg.get('engine_dir'))
        self._start_engine_async()

    # ---------- 后台线程（只改共享变量，不碰 UI） ----------

    def _start_engine_async(self):
        """后台确保引擎在线并刷新任务清单"""
        if not self._engine.is_installed():
            self._engine_label.setText('引擎：未安装（%s）' % self._engine.cfg.get('engine_dir'))
            return

        def work():
            try:
                self._engine.wait_up(timeout=300)
            except Exception as e:
                self._engine_error = str(e)
                return
            try:
                self._apps = self._engine.applications()
            except Exception:
                pass

        import threading
        self._engine_error = None
        self._apps = None
        threading.Thread(target=work, daemon=True).start()

    def _worker_run(self, start, label):
        """线程体：启动一次运行并等到结束，结果写 self._result"""
        def progress(text):
            self._note = text

        try:
            self._engine.wait_up(progress=progress)
            ok, msg = self._engine.run_and_wait(start, progress=progress)
        except Exception as e:
            ok, msg = False, str(e)
        self._result = (label, ok, msg)

    def _launch_worker(self, start, label):
        if self._busy:
            return
        import threading
        self._busy = True
        self._result = None
        self._last_node = None
        self._set_busy(True)
        if self._pet is not None and hasattr(self._pet, 'set_thinking'):
            self._pet.set_thinking(True)
        if self._pet is not None and hasattr(self._pet, 'show_bubble'):
            self._pet.show_bubble('开工啦！接下来请勿动键鼠和截屏，黑屏加载都是正常的～')
        # 运行期间最小化本窗口，并把游戏切到前台让玩家看到过程
        self.showMinimized()
        _foreground_game_window()
        self.log('—— 开始：%s ——' % label)
        self._worker = threading.Thread(
            target=self._worker_run, args=(start, label), daemon=True)
        self._worker.start()

    # ---------- 按钮动作 ----------

    def open_settings(self):
        """打开任务设置；保存后重启引擎使配置生效"""
        if yaml_missing():
            self.log('缺少 PyYAML（pip install pyyaml），无法编辑设置')
            return
        if self._apps is None:
            self.log('引擎还没就绪，稍等几秒再打开设置')
            return
        dlg = ZzzSettingsDialog(self._engine,
                                self._apps.get('applications', []), self)
        if dlg.exec():
            self.log('已保存任务配置，正在重启引擎使其生效…')
            self._need_refresh_chain = True

            import threading
            threading.Thread(target=self._apply_restart, daemon=True).start()

    def _apply_restart(self):
        """线程体：重启引擎并刷新应用列表"""
        def progress(text):
            self._note = text
        try:
            self._engine.restart_service(progress=progress)
            self._apps = self._engine.applications()
            self._engine_error = None
        except Exception as e:
            self._engine_error = str(e)

    def enter_game(self):
        """只进入游戏，不跑任务"""
        self._launch_worker(self._engine.enter_game, '进入游戏')

    def start_chain(self):
        """一键日常：跑完整一条龙（含自动打开并进入游戏）"""
        self._launch_worker(self._engine.run_chain, '一条龙日常')

    def start_task(self, task):
        """单项执行：以独立应用方式只跑这一项"""
        engine = self._engine
        keywords = task['keywords']

        def start():
            apps = engine.applications().get('applications', [])
            app_id = engine.resolve_app_id(keywords, apps)
            if not app_id:
                return {'started': False, 'error': '在引擎里找不到匹配的应用（%s）' % keywords}
            self.log('匹配到应用：%s' % app_id)
            return engine.run_standalone(app_id)

        self._launch_worker(start, task['label'])

    def stop_run(self):
        """请求停止当前运行"""
        if not self._busy:
            return

        import threading
        threading.Thread(target=lambda: self._safe_stop(), daemon=True).start()

    def _safe_stop(self):
        try:
            self._engine.stop()
        except Exception:
            pass

    # ---------- 定时刷新 ----------

    def _poll(self):
        """每 1.5 秒：刷新引擎/游戏状态，线程结果落回 UI"""
        # 引擎状态
        if not self._engine.is_installed():
            self._engine_label.setText('引擎：未安装（先安装 ZenlessZoneZero-OneDragon）')
        elif self._engine.is_up():
            self._engine_label.setText('引擎：在线 ✔')
        elif self._engine_error:
            self._engine_label.setText('引擎：启动失败')
        else:
            self._engine_label.setText('引擎：启动中…')

        # 任务清单（拿到应用列表后刷新一次；设置保存后强制再刷）
        if self._apps is not None and (self._need_refresh_chain
                                       or self._chain_label.text().startswith('一条龙任务清单：—')):
            apps = self._apps.get('applications', [])
            enabled = [a.get('app_name') or a.get('app_id')
                       for a in apps if a.get('enabled_in_one_dragon')]
            self._chain_label.setText('一条龙任务清单：%s（点"⚙ 任务设置"可改）'
                                      % ('、'.join(enabled) if enabled else '空'))
            self._need_refresh_chain = False
            idx = self._apps.get('current_instance_idx')
            if idx:
                self.log('当前账号：%02d' % idx)

        # 游戏窗口
        try:
            w = self._engine.window_status()
            if w.get('is_win_valid'):
                self._game_label.setText('游戏窗口：正常（%dx%d）'
                                         % (w.get('width') or 0, w.get('height') or 0))
            else:
                self._game_label.setText('游戏窗口：未找到（一条龙会自动打开游戏）')
        except Exception:
            self._game_label.setText('游戏窗口：—')

        # 引擎在跑（无论谁触发：桌宠按钮/命令行/定时任务）就把游戏拉回前台，
        # 否则引擎的点击会落到遮挡游戏的其他窗口上
        st = self._engine.status() if self._engine.is_installed() else {'state': 'offline'}
        engine_running = st.get('state') == 'running'
        if self._busy or engine_running:
            state = st.get('state')
            node = st.get('current_node')
            if node and node != self._last_node:
                self._last_node = node
                self.log('[%s] %s' % (ENGINE_STATE_TEXT.get(state, state), node))
            _foreground_game_window()
            hint = NODE_HINTS.get(node)
            self._note_label.setText(hint or self._note)

        # 线程结果
        if self._result is not None:
            label, ok, msg = self._result
            self._result = None
            self._busy = False
            self._set_busy(False)
            if self._pet is not None and hasattr(self._pet, 'set_thinking'):
                self._pet.set_thinking(False)
            self.showNormal()
            self.raise_()
            self.log('—— %s：%s ——' % ('完成 ✅' if ok else '失败 ❌', msg))
            self._note_label.setText('%s：%s' % (label, msg))
            if self._pet is not None and hasattr(self._pet, 'show_bubble'):
                if ok:
                    self._pet.show_bubble('绝区零今日任务做完啦，快去领奖励吧 ✨')
                else:
                    self._pet.show_bubble('呜…绝区零任务没跑完，看看日志？')

    # ---------- 杂项 ----------

    def _set_busy(self, busy):
        self._run_btn.setEnabled(not busy)
        self._enter_btn.setEnabled(not busy)
        for btn in self._task_buttons.values():
            btn.setEnabled(not busy)
        self._stop_btn.setEnabled(busy)

    def log(self, text):
        self._log.appendPlainText('[%s] %s' % (time.strftime('%H:%M:%S'), text))

    def closeEvent(self, event):
        """关窗口不停引擎：后端服务继续留在后台，下次秒连"""
        self._timer.stop()
        super().closeEvent(event)


def yaml_missing():
    """PyYAML 是否缺失（设置界面依赖它）"""
    from zzz_daily import yaml
    return yaml is None
