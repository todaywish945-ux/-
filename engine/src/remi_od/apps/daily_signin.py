"""每日签到。签到方式由桌宠写入 daily_signin.yml 的 selected_sign 决定：
- hou_hou_bakery 吼吼饼铺（默认，已实现）
- trigrams_collection 卦象集录 / scratch_card 刮刮卡（未移植）

吼吼饼铺流程（移植自原项目 HouHouBakeryApp）：
传送到布亚斯特城区-吼吼饼铺 → 与吼吼先生交互 → OCR 驱动领取「零食盲盒」→ 回大世界。
"""


from remi_od.apps.schedule_transport import ScheduleTransport
from remi_od.apps.transport import Transport
from remi_od.core.app import App
from remi_od.core.geometry import Point
from remi_od.core.operation import from_node, node
from remi_od.core.round_result import Round

APP_ID = 'daily_signin'
APP_NAME = '每日签到'

SIGN_NAMES = {
    'hou_hou_bakery': '吼吼饼铺',
    'trigrams_collection': '卦象集录',
    'scratch_card': '刮刮卡',
}

# 吼吼饼铺领取流程的状态文字（全屏 OCR 判断，坐标无关）
STATUS_TEXTS_FULL_SCREEN = [0, 0, 1920, 1080]


class DailySigninApp(App):

    def __init__(self, ctx):
        App.__init__(self, ctx, app_id=APP_ID, app_name=APP_NAME,
                     description='每日签到（吼吼饼铺/卦象集录/刮刮卡）')
        self.sign: str = 'hou_hou_bakery'
        self.claimed: bool = False

    def handle_init(self) -> None:
        App.handle_init(self)
        from remi_od.core import config as config_mod

        self.sign = config_mod.selected_sign(self.ctx.paths)
        self.claimed = False
        self._collect_round = 0

    @node('确认在大世界', is_start=True, max_retry=8)
    def check_world(self) -> Round:
        if self.shot is None:
            return self.round_retry('等待截图')
        if self.ctx.is_screen(self.shot, '大世界'):
            return self.round_success('大世界')
        result = self.find_area('快捷手册-日常', '关闭按钮')
        if result is not None and result.data is not None:
            self.ctx.controller.click(result.data.center)
            return self.round_retry('已点关闭', wait=0.35)
        # 剧情对话开着时 ESC 无效（对话必须点击推进——用户既证）；
        # 带选项的问句点文字无反应，必须点选项（2026-10-07 咖啡问句实测）
        from remi_od.core.geometry import Rect
        wide = self.ctx.ocr.run(self.shot, Rect(400, 500, 1914, 1080))
        dialog = [i for i in wide
                  if Rect(400, 860, 1500, 1060).contains(i.center) and len(i.text) >= 8]
        if dialog:
            zone = Rect(1438, 536, 1914, 830)
            options = sorted((i for i in wide if zone.contains(i.center)
                              and any('\u4e00' <= c <= '\u9fff' for c in i.text)),
                             key=lambda i: i.center.y)
            if options:
                bail = next((i for i in options
                             if any(k in i.text for k in ('不喝', '不了', '不用', '先不'))), None)
                self.ctx.controller.click((bail or options[0]).center)
                return self.round_retry('点对话选项', wait=0.4)
            self.ctx.controller.click(dialog[0].center)
            return self.round_retry('点剧情对话推进', wait=0.35)
        self.ctx.controller.key('esc')
        return self.round_retry('按ESC关闭面板', wait=0.25)

    @from_node('确认在大世界')
    @node('传送')
    def transport(self) -> Round:
        if self.sign != 'hou_hou_bakery':
            return self.round_fail(f'签到方式未移植: {SIGN_NAMES.get(self.sign, self.sign)}')
        # 日程传送优先：日常页"抽取饼铺盲盒"卡的前往直达
        result = ScheduleTransport(self.ctx, 'daily_signin').execute(op_timeout_s=90)
        if result.success:
            return self.round_success(result.status)
        if '任务卡不在' in (result.status or ''):
            return self.round_success('签到已完成')
        op = Transport(self.ctx, '布亚斯特城区', '吼吼饼铺')
        result = op.execute(op_timeout_s=180)
        if result.success:
            return self.round_success(result.status)
        return self.round_fail(result.status or '传送失败')

    @from_node('传送', status='签到已完成')
    @node('签到已完成收尾', max_retry=3)
    def signin_done(self) -> Round:
        """任务卡不在=今日已完成：直接结束应用，绝不在日程页上继续操作。"""
        return self.round_success('今日已完成')

    @from_node('传送')
    @node('交互', max_retry=10)
    def interact(self) -> Round:
        """传送后立即按 F 直到交互界面打开（用户提速要求，不做额外等待）。"""
        if self.shot is not None and not self.ctx.is_screen(self.shot, '大世界'):
            return self.round_success('界面已打开')
        self.ctx.controller.key('f', press_time=0.2)
        self._reshoot(0.35)  # F 后同轮复检
        if self.shot is not None and not self.ctx.is_screen(self.shot, '大世界'):
            return self.round_success('界面已打开')
        return self.round_retry('按F交互', wait=0.35)

    @from_node('交互')
    @node('领取奖励', max_retry=20)
    def collect(self) -> Round:
        """领取循环（用户流程提速版：先赶快选一个盒子，之后连点直到出奖励）。

        每轮只做一次全图 OCR 并复用结果（OCR 是最大耗时项）。
        - 大世界 → 交互没生效，补按 F
        - 「同类型奖励」: 今日已领 → 成功退出（须先于确认判定，防误点循环）
        - 「确定/确认」: 奖励弹窗 → 点掉
        - 「查看今天」: 盲盒已居中 → 点屏幕中心
        - 其余 → 直接点盲盒槽位连点（不等文字提示），出奖励后由确认分支接手
        """
        if self.shot is None:
            return self.round_retry('等待截图')
        from remi_od.core.geometry import Rect

        # 提速：判定文字（确定 y≈854 / 同类型奖励 y≈959 / 机器界面标签）全部在
        # y>380，只 OCR 下半屏一次；介绍页误触检查复用同一份结果（原为每轮 2 次 OCR）
        items = self.ctx.ocr.run(self.shot, Rect(0, 380, 1920, 1080))
        if self._collect_round % 4 == 0:  # 诊断留档（限量）
            try:
                self.ctx.save_debug_image('bakery_collect', self.shot)
            except Exception:
                pass
        self._collect_round += 1

        def find(word: str, region: Rect | None = None, lcs: float = 0.5):
            best = None
            for it in items:
                if region is not None and not region.contains(it.center):
                    continue
                if word in it.text:
                    return it
                import difflib

                ratio = difflib.SequenceMatcher(None, word, it.text).ratio()
                if ratio >= lcs and (best is None or ratio > best[0]):
                    best = (ratio, it)
            return best[1] if best else None

        # 还停在大世界（交互没生效/事件干扰）→ 补按 F 重试交互
        if self.ctx.is_screen(self.shot, '大世界'):
            self.ctx.controller.key('f', press_time=0.2)
            return self.round_retry('大世界补按F', wait=0.35)

        # 必须先判「同类型奖励」，否则弹窗自带的确认会被误点造成循环
        if find('同类型奖励') is not None:
            status = '领取成功' if self.claimed else '今日已领取'
            return self.round_success(status, wait=0.25)

        # 奖励弹窗确认在画面中下方（实测翻牌结果界面 确定 在 y≈868）；高阈值防误匹配
        for confirm_word in ('确定', '确认'):
            item = find(confirm_word, region=Rect(700, 500, 1300, 1000), lcs=0.85)
            if item is not None:
                self.ctx.controller.click(item.center)
                self.claimed = True
                return self.round_wait(confirm_word, wait=0.25)

        if find('查看今天') is not None:
            self.ctx.controller.click(Point(960, 540))
            return self.round_wait('点击盲盒', wait=0.25)

        # 误入道具/物品介绍页（如点到了"丁尼"图标）→ ESC 关掉，别再连点
        # （介绍页头部在 y 380-660，直接过滤合并 OCR 的结果，不再二次 OCR）
        intro_region = Rect(400, 380, 1400, 660)
        if any('当前拥有' in i.text or 'X ' in i.text[:4]
               for i in items if intro_region.contains(i.center)):
            self.ctx.controller.key('esc')
            return self.round_retry('关闭误触的介绍页', wait=0.35)
        # 直接连点盲盒槽位（用户流程：赶快选一个盒子，之后一直点到出奖励）
        area = self.ctx.get_area('吼吼饼铺', '盲盒')
        if area is not None:
            self.ctx.controller.click(area.center)
            return self.round_wait('连点盲盒', wait=0.25)
        return self.round_retry('盲盒区域未建档', wait=0.25)

    @from_node('领取奖励')
    @node('返回大世界', max_retry=10)
    def back_world(self) -> Round:
        if self.shot is not None and self.ctx.is_screen(self.shot, '大世界'):
            return self.round_success('大世界')
        self.ctx.controller.key('esc')
        return self.round_retry('等待大世界', wait=0.25)
