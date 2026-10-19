"""地图传送：大世界 → 打开地图 → 选区域 → 选传送点 → 确认 → 等待加载回大世界。

流程移植自原 OneDragon 项目 Transport/MapTransport。
关键点：
- 底部传送点横条的 OCR 常把多个名字连读成一行，点击目标名字需按字符比例定位；
- 先扫横条（可能已含目标），没有再点区域标签切换区域；
- 找不到时横向拖拽翻页（先左后右兜底）。
"""

import difflib
import time

from remi_od.core.geometry import Point, Rect
from remi_od.core.operation import Operation, from_node, node
from remi_od.core.round_result import Round

# 地图主区域大致顺序（只影响拖拽方向快慢，不影响正确性）
AREA_ORDER = ['六分街', '澄辉坪', '布亚斯特城区', '录像店', 'HIA俱乐部']

# 传送点横条是固定 6 槽位布局（2026-09-24/25/26 多日截图实测，槽位 x 恒定）。
# 直点槽位可跳过整轮 OCR 搜索（地图页全图 OCR ~4.4 秒/轮，是全流程最大耗时项）。
STRIP_SLOTS_X = [215, 515, 814, 1113, 1418, 1711]
STRIP_Y = 1044
# (区域, 传送点) → 槽位下标（静态 UI 映射；游戏版本更新若换序需重测）
TP_SLOT = {
    ('布亚斯特城区', '吼吼饼铺'): 1,
    ('澄辉坪', '汀曼咖啡'): 2,
    ('澄辉坪', '录像店营业点'): 3,
}


def _best_window(text: str, target: str) -> tuple[int, float]:
    """在 text 中找与 target 最相似的等长窗口，返回 (起始下标, 相似度)。"""
    if not text or not target:
        return (0, 0.0)
    best = (0, 0.0)
    for i in range(0, max(1, len(text) - len(target) + 1)):
        window = text[i:i + len(target)]
        ratio = difflib.SequenceMatcher(None, target, window).ratio()
        if ratio > best[1]:
            best = (i, ratio)
    return best


# 区域标签在地图上的固定位置（多日截图实测：世界地图视图不滚动）。
# 直点坐标可省掉一次大区域 OCR（~4s）；点 3 次横条还没切换则回落 OCR 搜索。
AREA_LABEL_POINTS = {
    '布亚斯特城区': Point(528, 330),
    '澄辉坪': Point(1430, 240),
}


class Transport(Operation):

    op_name = '传送'

    def __init__(self, ctx, area_name: str, tp_name: str):
        Operation.__init__(self, ctx)
        self.area_name: str = area_name
        self.tp_name: str = tp_name
        self._area_drag_x: int | None = None
        self._area_drag_times: int = 0
        self._tp_drag_times: int = 0
        self._debug_times: int = 0
        self._slot_tried: bool = False
        self._label_clicks: int = 0

    def handle_init(self) -> None:
        self.ctx.enter_scope('')

    def _save_debug(self, tag: str) -> None:
        """失败诊断截图（限量）。"""
        if self._debug_times >= 10 or self.shot is None:
            return
        self._debug_times += 1
        try:
            self.ctx.save_debug_image(f'transport_{tag}', self.shot)
        except Exception:
            pass

    # ---- 打开地图 ----

    @node('打开地图', is_start=True, max_retry=10)
    def open_map(self) -> Round:
        if self.shot is not None and self.ctx.is_screen(self.shot, '地图'):
            return self.round_success('已在地图')
        # 地图开启动画期间严禁再点地图按钮：此刻世界 HUD 已消失，
        # ALT+点击会落在地图画面上——2026-09-27 实测点在澄辉坪大标签上，
        # 把横条切去了澄辉坪（用户看到的"先点澄辉坪"）。
        if self.shot is not None and not self.ctx.is_screen(self.shot, '大世界'):
            return self.round_wait('等待地图打开', wait=0.25)
        result = self.find_area('大世界', '地图')
        if result is not None and result.data is not None:
            area = self.ctx.get_area('大世界', '地图')
            self.ctx.controller.click(result.data.center, alt=bool(area and area.alt))
            self._reshoot(0.35)  # 地图动画后同轮复检，省一轮
            if self.ctx.is_screen(self.shot, '地图'):
                return self.round_success('已在地图')
            return self.round_wait('已点击地图', wait=0.25)
        return self.round_retry('等待大世界', 0.4)

    # ---- 选区域（用户流程：一直点区域标签，直到横条出现目标传送点）----

    @from_node('打开地图')
    @node('选择区域', max_retry=60)
    def choose_area(self) -> Round:
        if self.shot is None:
            return self.round_retry('等待截图')
        self._save_debug('选区域')

        # 已知槽位：小裁剪直查横条对应槽位是否已切到目标区域（~0.5s/次，
        # 出现目标名 = 区域已切换，立即放行去点传送点）
        if self._strip_has_tp():
            return self.round_success(f'{self.area_name}·横条已切换', wait=0.1)

        # 横条还没切过来 → 连点目标区域标签。已知固定坐标直点（零 OCR）；
        # 点 3 次没切换才回落到 OCR 搜索（坐标过期/视图不同的兜底）。
        label_pt = AREA_LABEL_POINTS.get(self.area_name)
        if label_pt is not None and self._label_clicks < 3:
            self._label_clicks += 1
            self.ctx.controller.click(label_pt)
            self._reshoot(0.3)  # 切换后同轮复检，命中则下轮直接放行
            if self._strip_has_tp():
                return self.round_success(f'{self.area_name}·横条已切换', wait=0.1)
            return self.round_retry('连点区域标签', wait=0.15)

        area = self.ctx.get_area('地图', '主区域名称')
        target = self.ctx.ocr.find_text(self.shot, self.area_name, area.rect, lcs=0.7)
        if target is not None:
            self.ctx.controller.click(target.center)
            return self.round_retry('连点区域标签', wait=0.2)

        # 未找到区域 → 拖拽地图查找
        if self._area_drag_x is None:
            items = self.ctx.ocr.run(self.shot, area.rect)
            names = [i.text for i in items]
            tgt_idx = next((AREA_ORDER.index(n) for n in AREA_ORDER
                            if n == self.area_name), None)
            cur_idx = [AREA_ORDER.index(n) for n in names if n in AREA_ORDER]
            if tgt_idx is not None and cur_idx:
                self._area_drag_x = -500 if tgt_idx > max(cur_idx) else 500
            else:
                self._area_drag_x = -500
        center = Point(960, 540)
        self.ctx.controller.drag(center, Point(center.x + self._area_drag_x, center.y),
                                 duration=0.4)
        self._area_drag_times += 1
        if self._area_drag_times >= 6 and self._area_drag_x < 0:
            self._area_drag_x = 500
        elif self._area_drag_times >= 12:
            return self.round_fail(f'未找到地图区域 {self.area_name}')
        return self.round_wait('拖拽查找区域', wait=0.25)

    def _strip_has_tp(self) -> bool:
        """横条对应槽位是否已显示目标传送点（区域已切换的标志）。"""
        slot = TP_SLOT.get((self.area_name, self.tp_name))
        if slot is None:
            return False
        cx = STRIP_SLOTS_X[slot]
        item = self.ctx.ocr.find_text(self.shot, self.tp_name,
                                      Rect(cx - 130, 995, cx + 130, 1080), lcs=0.6)
        return item is not None

    # ---- 选传送点（横条已切换，直点槽位；未知目标回落 OCR 搜索）----

    @from_node('选择区域')
    @node('选择传送点', max_retry=14)
    def choose_tp(self) -> Round:
        if self.shot is None:
            return self.round_retry('等待截图')
        self._save_debug('选传送点')

        # 0. 已知槽位直点（提速：跳过 OCR 搜索，见 TP_SLOT 注释）；只试一次，
        #    失败说明槽位映射过期，回落 OCR 搜索路径
        slot = TP_SLOT.get((self.area_name, self.tp_name))
        if slot is not None and not self._slot_tried and self._tp_drag_times == 0:
            self._slot_tried = True
            self.ctx.controller.click(Point(STRIP_SLOTS_X[slot], STRIP_Y))
            time.sleep(0.25)  # 确认弹窗就绪，省下轮扑空
            return self.round_success(self.tp_name, wait=0.1)

        # 1. 横条找目标（高阈值精确匹配）
        if self._click_tp_in_strip(lcs=0.8):
            return self.round_success(self.tp_name, wait=0.2)

        # 2. 地图区域内的传送点标签（区域放大后的 pin）
        area = self.ctx.get_area('地图', '主区域名称')
        target = self.ctx.ocr.find_text(self.shot, self.tp_name, area.rect, lcs=0.7)
        if target is not None:
            self.ctx.controller.click(target.center)
            return self.round_success(self.tp_name, wait=0.2)

        # 3. 拖拽横条翻页（先左后右）
        strip = self.ctx.get_area('地图', '传送点名称')
        cx, cy = strip.center.x, strip.center.y
        dx = -800 if self._tp_drag_times < 5 else 800
        self.ctx.controller.drag(Point(cx - 20, cy - 20),
                                 Point(cx - 20 + dx, cy - 20), duration=0.4)
        self._tp_drag_times += 1
        if self._tp_drag_times >= 10:
            self._save_debug('传送点失败')
            return self.round_fail(f'未找到传送点 {self.tp_name}')
        return self.round_retry('拖拽查找传送点', wait=0.25)

    def _click_tp_in_strip(self, lcs: float = 0.8) -> bool:
        """在横条中找目标传送点并点击（提速：每轮只做一次全图 OCR）。

        注意：裁剪横条再 OCR 会把多个名字连读成一行且常吞字（如 吼吼饼铺→饼销），
        全图 OCR 的分词更准——单次全图识别，先试独立名字项精确匹配，
        再对横条内的连读长行按字符比例定位。
        """
        strip = self.ctx.get_area('地图', '传送点名称')
        items = [i for i in self.ctx.ocr.run(self.shot)
                 if strip.rect.contains(i.center)]
        # 1. 独立名字项精确匹配
        for item in items:
            if self.tp_name in item.text:
                self.ctx.controller.click(item.center)
                return True
        # 2. 连读长行：按字符比例定位（容忍吞字，阈值放宽）
        for item in items:
            if len(item.text) <= len(self.tp_name):
                continue
            idx, ratio = _best_window(item.text, self.tp_name)
            if ratio >= 0.6:
                frac = (idx + len(self.tp_name) / 2) / max(1, len(item.text))
                x = item.rect.x1 + frac * item.rect.width
                self.ctx.controller.click(Point(int(x), item.center.y))
                return True
        return False

    # ---- 确认与加载 ----

    @from_node('选择传送点')
    @node('点击传送', max_retry=10)
    def click_tp(self) -> Round:
        return self.round_by_ocr_and_click('确认', '地图', '确认', lcs=0.9,
                                           wait=0.3, wait_not_found=0.2)

    @from_node('点击传送')
    @node('等待加载', max_retry=90, timeout_s=120)
    def wait_world(self) -> Round:
        if self.shot is None:
            return self.round_retry('等待截图')
        if self.ctx.is_screen(self.shot, '大世界'):
            return self.round_success('大世界')
        return self.round_wait('传送加载中', wait=0.35)
