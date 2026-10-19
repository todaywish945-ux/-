"""咖啡店：每日免费点单 1 杯咖啡（恢复电量+增益）。

移植自原项目 CoffeeApp 的「澄辉坪-汀曼咖啡」对话点单分支（传送落点正对入口，
无需转向）。用户要求（2026-09-26 提速）：点单选右侧选项列表的**第一个**，
不挑特定咖啡名；传送后立即按 F 循环直到对话打开。
"""

from remi_od.apps.schedule_transport import ScheduleTransport
from remi_od.apps.transport import Transport
from remi_od.core.app import App
from remi_od.core.operation import from_node, node
from remi_od.core.round_result import Round

APP_ID = 'coffee'
APP_NAME = '咖啡'


class CoffeeApp(App):

    def __init__(self, ctx):
        App.__init__(self, ctx, app_id=APP_ID, app_name=APP_NAME,
                     description='每日免费咖啡（恢复电量+增益，澄辉坪-汀曼咖啡）')
        self._calm_rounds = 0

    def handle_init(self) -> None:
        App.handle_init(self)
        self._calm_rounds = 0
        self._order_tries = 0  # 本次运行点单动作次数（点击/按键混合，上限 3）

    @node('确认在大世界', is_start=True, max_retry=8)
    def check_world(self) -> Round:
        if self.shot is None:
            return self.round_retry('等待截图')
        if self.ctx.is_screen(self.shot, '大世界'):
            return self.round_success('大世界')
        # 已在咖啡店对话中（汀曼大师标题可见）→ 直接跳到点单，别 ESC 关对话
        title = self.find_area('咖啡店', '对话框标题-汀曼大师')
        if title is not None and title.data is not None:
            return self.round_success('已在咖啡店')
        result = self.find_area('快捷手册-日常', '关闭按钮')
        if result is not None and result.data is not None:
            self.ctx.controller.click(result.data.center)
            return self.round_retry('已点关闭', wait=0.25)
        self.ctx.controller.key('esc')
        return self.round_retry('按ESC关闭面板', wait=0.35)

    @from_node('确认在大世界')
    @node('传送')
    def transport(self) -> Round:
        """日程传送（F2 日常页"前往"直达）优先；地图传送兜底。"""
        result = ScheduleTransport(self.ctx, 'coffee').execute(op_timeout_s=90)
        if result.success:
            return self.round_success(result.status)
        if '任务卡不在' in (result.status or ''):
            return self.round_success('咖啡已完成')
        op = Transport(self.ctx, '澄辉坪', '汀曼咖啡')
        result = op.execute(op_timeout_s=180)
        if result.success:
            return self.round_success(result.status)
        return self.round_fail(result.status or '传送失败')

    @from_node('传送', status='咖啡已完成')
    @node('咖啡已完成收尾', max_retry=3)
    def coffee_done(self) -> Round:
        """任务卡不在=今日已完成：直接结束应用。"""
        return self.round_success('今日已完成')

    @from_node('传送')
    @node('交互', max_retry=10)
    def interact(self) -> Round:
        """传送后立即按 F 直到对话打开（用户提速要求）。"""
        if self.shot is not None and not self.ctx.is_screen(self.shot, '大世界'):
            return self.round_success('对话已打开')
        self.ctx.controller.key('f', press_time=0.2)
        self._reshoot(0.35)  # F 后同轮复检
        if self.shot is not None and not self.ctx.is_screen(self.shot, '大世界'):
            return self.round_success('对话已打开')
        return self.round_retry('按F交互', wait=0.35)

    @staticmethod
    def _has_cjk(text: str) -> bool:
        return any('\u4e00' <= ch <= '\u9fff' for ch in text)

    def _zone_options(self, items=None):
        """选项区真正的选项行（含中文、按从上到下排序）。

        2026-10-07：背景招牌的字母噪声（ORDER HERE 被误读成 DDCD UCDE 等）
        用"含中文"过滤剔除，替代旧的 y>620 过滤——旧过滤会把第一项
        「汀曼特调」(y≈587) 漏掉，导致按 1 时语义上选的不是第一项。
        """
        area = self.ctx.get_area('咖啡店', '右侧选项区域')
        if items is None:
            items = self.ctx.ocr.run(self.shot, area.rect)
        return sorted(
            (i for i in items
             if area.rect.contains(i.center) and self._has_cjk(i.text)),
            key=lambda i: i.center.y)

    def _first_option(self, items=None):
        """选项区最上面的选项；无选项返回 None。"""
        options = self._zone_options(items)
        return options[0] if options else None

    @from_node('确认在大世界', status='已在咖啡店')
    @from_node('交互')
    @node('对话点单', max_retry=15)
    def dialog_order(self) -> Round:
        """推进对话直到出现咖啡选项并点单（用户要求：选第一个选项）。

        2026-09-27 用户实测：选项出现时**直接按数字键 1** 即可选第一个，
        OCR 点文字会点歪。对话状态中按 F 无效：推进靠点击（标题/对话主体）；
        F 只用于"还没进对话"的场景。提速：选项区+对话区合并为一次下半屏 OCR。
        """
        from remi_od.core.geometry import Rect

        items = self.ctx.ocr.run(self.shot, Rect(400, 500, 1914, 1080))
        options = self._zone_options(items)
        if options:
            # 2026-10-07 四次实测：引擎注入的数字键 1 落进前台游戏后问句原样
            # 不动（人工按有效、此前几天引擎按也有效——游戏对"对话框数字
            # 快捷键"的接受与否和当时输入模式有关：传送落地后光标锁定态下
            # 不响应）。点击自带输入模式修复（README 三件套）且全程可靠，
            # 故以点击为主、按键穿插兜底：第1/3次点「特调」，第2次按数字
            # 键 1（首次点击修好输入模式后按键可能生效）。上限 3 次，仍不行
            # 点「不喝了」退出。
            target = next((i for i in options if '特调' in i.text), options[0])
            self._order_tries += 1
            if self._order_tries == 2:
                self.ctx.controller.key('1', press_time=0.15)
                return self.round_wait(f'第{self._order_tries}次按1点单', wait=0.8)
            if self._order_tries <= 3:
                self.ctx.controller.click(target.center)
                return self.round_wait(f'第{self._order_tries}次点击点单', wait=0.8)
            bail = next((i for i in options if '不喝' in i.text), None)
            if bail is not None:
                self.ctx.controller.click(bail.center)
                return self.round_fail('点单三次未生效，已点「不喝了」退出')
            return self.round_fail('点单选项无法安全处理，需人工确认')
        # 选项消失 + 已经点过 = 选择被游戏接受，交给点单后处理
        if self._order_tries > 0:
            return self.round_success('点单已生效')

        # 2. 标题在 → 点标题推进对话
        title = self.find_area('咖啡店', '对话框标题-汀曼大师')
        if title is not None:
            if title.data is not None:
                self.ctx.controller.click(title.data.center)
            return self.round_wait('继续对话', wait=0.25)

        # 3. 对话主体有文字 → 点对话区推进
        dialog_area = Rect(400, 860, 1500, 1060)
        dialog_texts = [i for i in items if dialog_area.contains(i.center)]
        if dialog_texts:
            self.ctx.controller.click(dialog_texts[0].center)
            return self.round_wait('推进对话', wait=0.25)

        # 4. 完全没有对话迹象 → 补按 F（仅此刻有用）
        self.ctx.controller.key('f', press_time=0.2)
        return self.round_retry('补按交互键', wait=0.25)

    @from_node('对话点单')
    @node('点单后处理', max_retry=18)
    def after_order(self) -> Round:
        """点单后的弹窗序列：跳过 → 电量确认 / 不可贪杯确认。

        结束判定：连续三轮无标题、无选项、无弹窗 → 对话结束（喝完或已喝过路径）。
        2026-10-07 实测点单后有约 6s 的无 UI 转场动画，两轮平静会误判——
        提高到三轮，即使仍误判，返回大世界节点也能处理重新弹出的问句。
        """
        from remi_od.core.geometry import Rect

        result = self.find_area('咖啡店', '点单后跳过')
        if result is not None and result.data is not None:
            area = self.ctx.get_area('咖啡店', '点单后跳过')
            # 片刻闲（布亚斯特咖啡店）的跳过按钮是"逆天按钮"：光标不划过
            # 就不生效——官方同款先拖鼠标让光标显形，再原地点击（多点几次）
            self.ctx.controller.drag(area.rect.left_top, area.center, duration=0.2)
            self.ctx.controller.click()
            self._calm_rounds = 0
            return self.round_wait('拖拽跳过', wait=0.25)

        for area_name in ('电量确认', '不可贪杯确认', '对话框确认'):
            result = self.find_area('咖啡店', area_name)
            if result is not None and result.data is not None:
                self.ctx.controller.click(result.data.center)
                self._calm_rounds = 0
                return self.round_wait(area_name, wait=0.25)

        title = self.find_area('咖啡店', '对话框标题-汀曼大师')
        option = self._first_option()  # 独立裁剪（本节点无合并 OCR 可复用）
        if title is None and option is None:
            self._calm_rounds += 1
            if self._calm_rounds >= 3:
                return self.round_success('对话结束')
            return self.round_wait('等待收尾', wait=0.25)

        # 对话还在（标题/选项仍在）→ 回点单分支推进
        self._calm_rounds = 0
        return self.round_success('继续对话')

    @from_node('点单后处理')
    @node('返回大世界', max_retry=15)
    def back_world(self) -> Round:
        """喝完回世界：带选项的问句选「不喝了」退出，剧情对话点击推进，再 ESC。

        2026-10-07 实测：点单后游戏会重新弹出"想要喝点什么？"问句，选项
        挂着时点对话文字永远无反应，必须选退出项；绝不点其他选项（第一项
        是再买一杯，会扣货币）。
        """
        if self.shot is not None and self.ctx.is_screen(self.shot, '大世界'):
            return self.round_success('大世界')
        from remi_od.core.geometry import Rect

        # 单次加宽 OCR 同时覆盖选项区（右中）与对话区（底部），两分支共用
        items = self.ctx.ocr.run(self.shot, Rect(400, 500, 1914, 1060))
        option_zone = Rect(1438, 500, 1914, 850)
        for kw in ('不喝', '不了', '不用', '先不'):
            bail = next((i for i in items
                         if option_zone.contains(i.center) and kw in i.text), None)
            if bail is not None:
                self.ctx.controller.click(bail.center)
                return self.round_retry('选退出项', wait=0.4)
        dialog = [i for i in items
                  if Rect(400, 860, 1500, 1060).contains(i.center) and len(i.text) >= 8]
        if dialog:
            self.ctx.controller.click(dialog[0].center)
            return self.round_retry('点剧情对话推进', wait=0.35)
        self.ctx.controller.key('esc')
        return self.round_retry('等待大世界', wait=0.35)
