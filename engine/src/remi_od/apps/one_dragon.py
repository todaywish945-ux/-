"""一条龙编排：按 _group.yml 顺序执行启用的应用，跳过当日已成功的，单个失败不阻断后续。"""

from remi_od.apps.enter_game import EnterGameOp
from remi_od.apps.schedule_transport import CompendiumMixin
from remi_od.core import config as config_mod
from remi_od.core.log import log
from remi_od.core.operation import Operation, from_node, node
from remi_od.core.round_result import Round

APP_ID = 'one_dragon'

# 日常页任务卡关键词 → 对应应用（读卡进度决定跑不跑）
TASK_CARDS = [('录像店', 'random_play'), ('盲盒', 'daily_signin'), ('咖啡', 'coffee')]
APP_NAME = '一条龙'


class OneDragonOp(CompendiumMixin, Operation):

    """一条龙主指令（本身无运行记录，逐个应用各自记录）。"""

    op_name = '一条龙'

    STATUS_NEXT = '下一个应用'
    STATUS_ALL_DONE = '全部结束'

    def handle_init(self) -> None:
        from remi_od.core.app import is_app_done_today

        self.ctx.enter_scope('')
        self._registry = registry()
        plan = config_mod.group_apps(self.ctx.paths)
        self._plan: list[tuple[str, bool]] = [
            (app_id, enabled) for app_id, enabled in plan
            if app_id != APP_ID and app_id in self._registry
        ]
        self._unknown_apps: list[str] = [
            app_id for app_id, _ in plan if app_id not in self._registry and app_id != APP_ID
        ]
        # 应用进入前先保证在游戏内：由首个业务应用前插入进入游戏
        self._entered = False
        self._idx = -1
        self._fail_apps: list[str] = []
        self._done_apps: list[str] = []
        self._skip_apps: list[str] = []
        if self._unknown_apps:
            log('一条龙', f'忽略未注册应用: {self._unknown_apps}')

    def handle_done(self, result) -> None:
        self.ctx.exit_scope()

    @node('进入游戏', is_start=True)
    def enter_game(self) -> Round:
        """任何应用都在游戏内执行；已在游戏则直接成功。"""
        result = EnterGameOp(self.ctx).execute()
        if result.success:
            self._read_account_uid()
            return self.round_success('已进游戏')
        return self.round_fail(result.status or '进入游戏失败')

    @from_node('进入游戏')
    @node('读取日程任务', max_retry=20)
    def read_schedule(self) -> Round:
        """F2 日常页读三张任务卡的进度（界面 = 真相，换号/记录皆免疫）。

        只把"进度 0/1"的卡对应应用排进计划；看不清的卡也跑（各应用对
        已完成态都有快速收尾路径，跑一次代价很小）；全部 1/1 → 只跑活跃奖励。
        读取失败 → 回退按运行记录的老计划。
        """
        from remi_od.core.geometry import Rect

        if not (self._compendium_open() and self._on_daily_tab()):
            self.ctx.controller.key('f2', press_time=0.15)
            self._reshoot(1.0)  # 首拍等动画放完（同其他 F2 处）
            if self.shot is None or not self._compendium_open():
                self._reshoot(0.4)
        if self.shot is not None and self._compendium_open():
            if not self._on_daily_tab():
                result = self.find_area('快捷手册-日常', 'TAB-日常')
                if result is not None and result.data is not None:
                    self.ctx.controller.click(result.data.center)
                    self._reshoot(0.4)
            items = self.ctx.ocr.run(self.shot, Rect(300, 380, 1750, 1010))
            pending: list[str] = []
            for keyword, app_id in TASK_CARDS:
                card = next((i for i in items if keyword in i.text), None)
                if card is None:
                    # 找不到卡 ≠ 已完成：任务池每天轮换文案，关键词可能失配。
                    # 保守处理：把该应用排进计划（各应用对已完成态有快速收尾）
                    pending.append(app_id)
                    continue
                prog = next((i for i in items
                             if '/' in i.text and abs(i.center.x - card.center.x) < 230
                             and i.center.y < card.center.y), None)
                done = prog is not None and prog.text.strip().startswith('1/')
                if not done:
                    pending.append(app_id)
            self.ctx.controller.key('esc')
            self._reshoot(0.4)
            if pending:
                ordered = [(a, True) for a, _ in self._plan if a in pending]
                self._plan = ordered + [('engagement_reward', True)]
                log('一条龙', f'日程读取：未完成 {pending}，计划 {[(a) for a, _ in self._plan]}')
                return self.round_success('日程已读取')
            self._plan = [('engagement_reward', True)]
            log('一条龙', '日程读取：三任务已完成，仅复核活跃奖励')
            return self.round_success('日程全部完成')
        self._diag_times = getattr(self, '_diag_times', 0) + 1
        if self._diag_times % 4 == 1:
            try:
                self.ctx.save_debug_image('one_dragon_日程读取失败', self.shot)
            except Exception:
                pass
        return self.round_retry('F2 读取日程（失败将回退记录计划）', wait=0.3)

    def _read_account_uid(self) -> None:
        """从大世界右下角 OCR 当前账号 UID，运行记录按账号区分（换号防串）。"""
        from remi_od.core.geometry import Rect

        try:
            self.shot = self.ctx.controller.screenshot()
            if self.shot is None:
                return
            item = self.ctx.ocr.find_text(self.shot, 'UID',
                                          Rect(1650, 1030, 1920, 1080), lcs=0.6)
            if item is not None:
                digits = ''.join(ch for ch in item.text if ch.isdigit())
                if digits:
                    self.ctx.uid = digits
                    from remi_od.core.log import log
                    log('一条龙', f'当前账号 UID: {digits}')
        except Exception:
            pass

    @from_node('进入游戏')
    @from_node('读取日程任务')
    @from_node('读取日程任务', success=False)
    @node('执行应用')
    def run_next(self) -> Round:
        """自环节点（WAIT 不换节点）：每轮推进一个应用，跑完计划后汇总结束。"""
        self._idx += 1
        if self._idx >= len(self._plan):
            return self.round_success(self._summary())
        app_id, enabled = self._plan[self._idx]
        app_info = self._registry[app_id]
        if not enabled:
            self._skip_apps.append(app_info.app_name)
            return self.round_wait(self.STATUS_NEXT, wait=0.1)
        # 日程页读取的计划即真相，不再按运行记录跳过
        log('一条龙', f'运行 {app_info.app_name}')
        app = app_info.factory(self.ctx)
        result = app.execute()
        if result.success:
            self._done_apps.append(app_info.app_name)
        else:
            self._fail_apps.append(app_info.app_name)
            log('一条龙', f'{app_info.app_name} 失败: {result.status}')
        return self.round_wait(self.STATUS_NEXT, wait=0.1)

    def _summary(self) -> str:
        parts = []
        if self._done_apps:
            parts.append('完成:' + ','.join(self._done_apps))
        if self._fail_apps:
            parts.append('失败:' + ','.join(self._fail_apps))
        if self._skip_apps:
            parts.append('跳过:' + ','.join(self._skip_apps))
        return '；'.join(parts) if parts else self.STATUS_ALL_DONE


def registry() -> dict:
    """应用注册表：app_id -> AppInfo。"""
    from remi_od.apps.coffee import APP_ID as COFFEE_ID, CoffeeApp
    from remi_od.apps.daily_signin import APP_ID as SIGNIN_ID, DailySigninApp
    from remi_od.apps.engagement_reward import APP_ID as ENGAGE_ID, EngagementRewardApp
    from remi_od.apps.random_play import APP_ID as RANDOM_ID, RandomPlayApp
    from remi_od.core.app import AppInfo

    return {
        SIGNIN_ID: AppInfo(SIGNIN_ID, '每日签到', '每日签到（吼吼饼铺/卦象集录/刮刮卡）',
                           True, lambda ctx: DailySigninApp(ctx)),
        COFFEE_ID: AppInfo(COFFEE_ID, '咖啡', '每日免费咖啡（恢复电量+增益）',
                           True, lambda ctx: CoffeeApp(ctx)),
        RANDOM_ID: AppInfo(RANDOM_ID, '录像店随机游玩', '录像店随机游玩',
                           True, lambda ctx: RandomPlayApp(ctx)),
        ENGAGE_ID: AppInfo(ENGAGE_ID, '活跃奖励(养成)', '每日活跃/养成奖励领取',
                           True, lambda ctx: EngagementRewardApp(ctx)),
    }
