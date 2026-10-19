"""日程传送：F2 快捷手册-日常 → 任务卡"前往"一键直达任务地点。

2026-09-29 用户方案：版本更新会挤占地图底部传送点横条（左右划拉找点不可靠）；
日常页任务卡自带"前往"按钮直通任务地点，且点击本身推进任务进度。
地图传送（Transport）保留为失败兜底。

流程：确认在大世界 → F2 打开手册并切到日常页 → OCR 找任务卡关键词 +
其正下方的"前往"按钮 → 点击 → （确认弹窗/选择弹窗就近处理）→ 等待落地大世界。
"""

from remi_od.core.geometry import Rect
from remi_od.core.operation import Operation, from_node, node
from remi_od.core.round_result import Round

# 日常页内容区（任务卡 + 前往按钮都在此范围内）
_PAGE_RECT = Rect(300, 380, 1750, 1010)


class CompendiumMixin:
    """快捷手册开页判定（活跃奖励与日程传送共用）。"""

    def _compendium_open(self) -> bool:
        """手册已打开（任意 TAB）：顶部页签条能 OCR 出 ≥2 个页签名。"""
        if self.shot is None:
            return False
        items = self.ctx.ocr.run(self.shot, Rect(700, 100, 1700, 300))  # 高度加到宽高比 8 内：过扁裁剪会被整图拒绝
        names = ''.join(i.text for i in items)
        return sum(1 for k in ('日常', '训练', '作战', '战术') if k in names) >= 2

    def _on_daily_tab(self) -> bool:
        """当前在"日常"TAB：TAB-日常 模板是未激活（白色）态，匹配不到=已激活。"""
        result = self.find_area('快捷手册-日常', 'TAB-日常')
        return not (result is not None and result.data is not None)


# 每日任务池每天轮换卡片标题，同一任务每天可能换文案——
# 按候选关键词列表匹配（任一命中即可），匹配不到再按关键词失败
TASK_KEYWORDS = {
    'coffee': ['品尝', '咖啡', '电量', '汀曼'],
    'daily_signin': ['盲盒', '刮刮', '占卜', '饼铺'],
    'random_play': ['录像店', '录像带'],
    'engagement_reward': ['活跃度'],
}


class ScheduleTransport(CompendiumMixin, Operation):

    op_name = '日程传送'

    def __init__(self, ctx, task_keyword: str):
        Operation.__init__(self, ctx)
        self.task_keyword: str = task_keyword
        self._keywords = TASK_KEYWORDS.get(task_keyword, [task_keyword])
        self._diag_times: int = 0

    def handle_init(self) -> None:
        self.ctx.enter_scope('')

    def handle_done(self, result) -> None:
        self.ctx.exit_scope()

    def _save_debug(self, tag: str) -> None:
        if self._diag_times >= 6 or self.shot is None:
            return
        self._diag_times += 1
        try:
            self.ctx.save_debug_image(f'schedule_{tag}', self.shot)
        except Exception:
            pass

    @node('确认在大世界', is_start=True, max_retry=8)
    def check_world(self) -> Round:
        if self.shot is None:
            return self.round_retry('等待截图')
        if self.ctx.is_screen(self.shot, '大世界'):
            return self.round_success('大世界')
        result = self.find_area('快捷手册-日常', '关闭按钮')
        if result is not None and result.data is not None:
            self.ctx.controller.click(result.data.center)
            return self.round_retry('已点关闭', wait=0.25)
        self.ctx.controller.key('esc')
        return self.round_retry('按ESC关闭面板', wait=0.25)

    @from_node('确认在大世界')
    @node('打开日常页', max_retry=60)
    def open_daily(self) -> Round:
        """F2 开手册（开关式按键，开了就停手）；开在别的页签点"日常"切过去。

        用户要求：F2 失败就一直按，直到任务界面出现（偶发按键不达，
        多按必达）。60 轮上限仅作死循环保险。
        """
        if self.shot is not None and self._compendium_open():
            if self._on_daily_tab():
                return self.round_success('日常页')
            result = self.find_area('快捷手册-日常', 'TAB-日常')
            if result is not None and result.data is not None:
                self.ctx.controller.click(result.data.center)
                self._reshoot(0.3)
                if self._on_daily_tab():
                    return self.round_success('日常页')
            return self.round_retry('点日常TAB', wait=0.25)
        self._diag_times += 1
        if self._diag_times % 3 == 1:  # 诊断：F2 到底打没打进去
            try:
                self.ctx.save_debug_image('schedule_F2诊断', self.shot)
                status = self.ctx.controller.window_status()
                log('日程传送', f"F2 诊断: 前台={status['is_win_active']}")
            except Exception:
                pass
        # F2 连按 8 轮不达 → 改点大世界右上角快捷手册按钮（另一条打开路径）
        if self._diag_times >= 8:
            btn = self.find_area('大世界', '快捷手册')
            if btn is not None and btn.data is not None:
                area = self.ctx.get_area('大世界', '快捷手册')
                self.ctx.controller.click(btn.data.center,
                                          alt=bool(area and area.alt))
                self._reshoot(0.5)
                if self.shot is not None and self._compendium_open():
                    return self.round_success('手册已开(按钮)')
                return self.round_retry('点快捷手册按钮', wait=0.3)
        self.ctx.controller.key('f2', press_time=0.15)
        # 轮询观察 3 秒：开页动画可能很长（2026-10-02 实测 1.1s 复检窗口
        # 不够用导致 F2 翻转开关），期间绝不补按第二次 F2
        self._reshoot(1.0)  # 首拍等开页动画放完，避免白识别一帧
        for _ in range(2):
            if self.shot is not None and self._compendium_open():
                break
            self._reshoot(0.8)
        if self.shot is not None and self._compendium_open():
            if self._on_daily_tab():
                return self.round_success('日常页')
            result = self.find_area('快捷手册-日常', 'TAB-日常')
            if result is not None and result.data is not None:
                self.ctx.controller.click(result.data.center)
                self._reshoot(0.4)
            return self.round_success('已打开手册') if self._on_daily_tab() \
                else self.round_retry('点日常TAB', wait=0.25)
        return self.round_retry('按F2打开手册', wait=0.25)

    @from_node('打开日常页')
    @node('点击前往', max_retry=8)
    def click_go(self) -> Round:
        """找任务卡关键词 + 其同列正下方的"前往"按钮，点击触发传送。"""
        if self.shot is None:
            return self.round_retry('等待截图')
        self._save_debug('找前往')
        items = self.ctx.ocr.run(self.shot, _PAGE_RECT)
        from remi_od.core.log import log
        log('日程传送', f"找卡[{self.task_keyword}] 命中场={len(items)}项")
        # 反向定位：先找"前往"按钮（只存在于中部任务卡一排，y>800），
        # 再认按钮正上方的卡标题是否为目标任务。不能按关键词直接找卡：
        # 左侧推荐任务列表含同名词（如"消耗60点电量"）会误命中；
        # 已完成任务的卡会从页面消失（找不到匹配卡=任务已完成）。
        goes_all = [i for i in items
                    if '前往' in i.text and i.center.y > 800]
        if not goes_all:
            return self.round_fail(f'任务卡不在（应已完成）: {self.task_keyword}')
        target = None
        go_btn = None
        for go in goes_all:
            title = next((i for i in items
                          if any(k in i.text for k in self._keywords)
                          and go.center.y - 450 < i.center.y < go.center.y
                          and abs(i.center.x - go.center.x) < 300), None)
            if title is not None:
                target, go_btn = title, go
                break
        if target is None:
            return self.round_fail(f'任务卡不在（应已完成）: {self.task_keyword}')
        self.ctx.controller.click(go_btn.center)
        self._reshoot(0.3)  # 传送确认/选择弹窗或直接开始加载
        if self.shot is not None and self.ctx.is_screen(self.shot, '大世界'):
            return self.round_retry('前往未生效', wait=0.25)
        return self.round_success('已点前往')

    @from_node('点击前往')
    @node('处理弹窗', max_retry=6)
    def handle_popup(self) -> Round:
        """前往后的确认弹窗 / 多地点选择弹窗就近处理；已回世界则直接成功。"""
        if self.shot is None:
            return self.round_retry('等待截图')
        if self.ctx.is_screen(self.shot, '大世界'):
            return self.round_success('已落地')
        items = self.ctx.ocr.run(self.shot, Rect(300, 300, 1700, 1000))
        # 多地点任务选择弹窗 → 点含任一候选关键词项
        choice = next((i for i in items
                       if any(k in i.text for k in self._keywords)), None)
        if choice is not None:
            self.ctx.controller.click(choice.center)
            return self.round_wait('选择任务地点', wait=0.35)
        # 传送确认弹窗
        confirm = next((i for i in items
                        if '确认' in i.text or '确定' in i.text or '前往' in i.text), None)
        if confirm is not None:
            self.ctx.controller.click(confirm.center)
            return self.round_wait('点确认', wait=0.35)
        return self.round_retry('等待弹窗处理', wait=0.25)

    @from_node('处理弹窗')
    @node('等待落地', max_retry=60, timeout_s=60)
    def wait_arrive(self) -> Round:
        if self.shot is None:
            return self.round_retry('等待截图')
        if self.ctx.is_screen(self.shot, '大世界'):
            return self.round_success('已落地大世界')
        return self.round_wait('传送加载中', wait=0.35)
