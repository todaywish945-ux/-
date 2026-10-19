"""活跃奖励（每日活跃度奖励领取）。

流程移植自原 OneDragon 项目 EngagementRewardApp：
大世界 → 打开快捷手册 → 切到日常页 → 点"今日最大活跃度" → 领取确认 → 回大世界。
官方对确认按钮/奖励预览用 OCR 识别，本引擎改为：先查"活跃度奖励-4"完成标记，
未完成则按官方坐标点确认按钮，不硬性判失败。
"""

import time

from remi_od.core.app import App
from remi_od.core.log import log
from remi_od.core.operation import from_node, node
from remi_od.core.round_result import Round

APP_ID = 'engagement_reward'
APP_NAME = '活跃奖励(养成)'  # 名称含"活跃"：桌宠快捷按钮按关键词匹配 app_name

# 确认按钮 OCR 搜索区（官方坐标 [882,704,1086,754] 外扩，兼容弹窗形态差异）
CONFIRM_REGION = (700, 600, 1300, 850)


class EngagementRewardApp(App):

    def __init__(self, ctx):
        App.__init__(self, ctx, app_id=APP_ID, app_name=APP_NAME,
                     description='领取快捷手册-日常的活跃度奖励（日刷新、无消耗）')

    @node('确认在大世界', is_start=True, max_retry=8)
    def check_world(self) -> Round:
        if self.shot is None:
            return self.round_retry('等待截图')
        if self.ctx.is_screen(self.shot, '大世界'):
            return self.round_success('大世界')
        # 不在大世界：优先点可见的 ✕ 关闭面板（手册类不理 ESC）
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

    def _compendium_open(self) -> bool:
        """快捷手册已打开（任意 TAB）：顶部页签条能 OCR 出 ≥2 个页签名。"""
        from remi_od.core.geometry import Rect

        if self.shot is None:
            return False
        items = self.ctx.ocr.run(self.shot, Rect(700, 100, 1700, 300))  # 高度加到宽高比 8 内：过扁裁剪会被整图拒绝
        names = ''.join(i.text for i in items)
        return sum(1 for k in ('日常', '训练', '作战', '战术') if k in names) >= 2

    def _on_daily_tab(self) -> bool:
        """当前在"日常"TAB：TAB-日常 模板是未激活（白色）态，匹配不到=已激活。"""
        result = self.find_area('快捷手册-日常', 'TAB-日常')
        return not (result is not None and result.data is not None)

    @from_node('确认在大世界')
    @node('打开快捷手册', max_retry=60)
    def open_compendium(self) -> Round:
        """按钮路由进手册（闭环）：点「快捷手册」按钮 → 验证 → 点「日常」TAB → 验证。

        每轮只走一步，下一步前先验证上一步结果，失败只重试当前步——
        对比 F2 开环路线（按键无反馈，每轮盲等 3 秒轮询），这里每步
        ~0.5s 且无翻转风险。F2 降为按钮连续找不到时的兜底，按一次后
        轮询 3 秒再验证，绝不补按第二次（2026-09-27 实测 F2 连按 12 次
        全白按：手册开着时再按会关掉）。
        """
        from remi_od.core.geometry import Rect

        if self.shot is None:
            return self.round_retry('等待截图')

        # 手册已开（任意页签：页签条 OCR ≥2 个页签名）→ 切到日常页
        if self._compendium_open():
            self._route_grace = 0
            if self._on_daily_tab():
                return self.round_success('日常页')
            result = self.find_area('快捷手册-日常', 'TAB-日常')
            if result is not None and result.data is not None:
                self.ctx.controller.click(result.data.center)
                self._reshoot(0.4)
                if self._on_daily_tab():
                    return self.round_success('日常页')
            return self.round_retry('点日常TAB', wait=0.25)

        # 大世界 → 点右上角快捷手册按钮（开手册的正路）
        if self.ctx.is_screen(self.shot, '大世界'):
            result = self.find_area('大世界', '快捷手册')
            if result is not None and result.data is not None:
                area = self.ctx.get_area('大世界', '快捷手册')
                self.ctx.controller.click(result.data.center,
                                          alt=bool(area and area.alt))
                self._route_grace = 5  # 开页动画可长达 3s：宽限期只等不动作
                self._reshoot(0.6)
                return self.round_retry('点快捷手册按钮', wait=0.25)
            self._btn_miss += 1
            if self._btn_miss < 2:  # 按钮模板偶发失配：先重试一轮再降级 F2
                return self.round_retry('未找到快捷手册按钮', wait=0.35)
        # 宽限期：刚点过按钮、手册还没被 OCR 认出、也不在大世界 → 开页动画中，
        # 纯等待。绝不点击（会顶到手册 ✕）也绝不 ESC（会把手册关掉）
        elif self._route_grace > 0:
            self._route_grace -= 1
            return self.round_wait('等手册开页动画', wait=0.4)
        # 非宽限的"别处"：剧情对话/意外弹窗清理（对话 ESC 无效必须点击）
        else:
            dialog = [i for i in self.ctx.ocr.run(self.shot, Rect(400, 860, 1500, 1060))
                      if len(i.text) >= 8]
            if dialog:
                self.ctx.controller.click(dialog[0].center)
                return self.round_retry('点剧情对话推进', wait=0.35)
            result = self.find_area('快捷手册-日常', '关闭按钮')
            if result is not None and result.data is not None:
                self.ctx.controller.click(result.data.center)
                return self.round_retry('已点关闭', wait=0.35)
            self.ctx.controller.key('esc')
            return self.round_retry('按ESC关闭面板', wait=0.25)

        # ---- F2 兜底（按钮连续 2 轮找不到才走）----
        self._diag = getattr(self, '_diag', 0) + 1
        if self._diag % 4 == 1:  # 诊断：看引擎每轮实际画面
            try:
                self.ctx.save_debug_image('engagement_F2诊断', self.shot)
                status = self.ctx.controller.window_status()
                log('活跃奖励', f"F2 诊断: 前台={status['is_win_active']}")
            except Exception:
                pass
        self.ctx.controller.key('f2', press_time=0.15)
        # 轮询观察 3 秒：开页动画可能很长（2026-10-02 实测 1.1s 复检窗口
        # 不够用导致 F2 翻转开关），期间绝不补按第二次 F2
        self._reshoot(1.0)  # 首拍等开页动画放完，避免白识别一帧
        for _ in range(2):
            if self.shot is not None and self._compendium_open():
                break
            self._reshoot(0.8)
        if self.shot is not None and self._compendium_open():
            return self.round_retry('F2已打开手册', wait=0.25)  # 下轮走切页分支
        return self.round_retry('按F2打开手册', wait=0.25)

    @from_node('打开快捷手册')
    @node('连点领取', max_retry=25)
    def claim(self) -> Round:
        """一块领：循环"点入口→弹窗点确定"，直到点入口不再弹奖励。

        每个可领档位弹一个"获得"结算窗；一块领=全部处理完为止。
        判定全凭画面：弹窗有确认点确认；面板无确认（纯展示）→ ESC 收尾；
        点入口不再弹任何东西 = 全领完。
        """
        from remi_od.core.geometry import Rect

        # 不在日常页 → 已领则收尾；页签不对就切日常
        if not (self._compendium_open() and self._on_daily_tab()):
            if self._claimed:
                return self.round_success('奖励领取完毕')
            if self._compendium_open():
                result = self.find_area('快捷手册-日常', 'TAB-日常')
                if result is not None and result.data is not None:
                    self.ctx.controller.click(result.data.center)
                    self._reshoot(0.4)
                    return self.round_retry('切日常TAB', wait=0.25)
            return self.round_retry('等待日常页', wait=0.4)

        for _ in range(3):  # 同轮最多处理 3 步
            items = self.ctx.ocr.run(self.shot, Rect(300, 150, 1700, 1080))
            # 1) 弹窗确认/确定 → 点掉，继续看下一档
            confirm = next((i for i in items
                            if '确认' in i.text or '确定' in i.text), None)
            if confirm is not None:
                self._claimed = True
                self._entry_no_popup = False
                self.ctx.controller.click(confirm.center)
                self._reshoot(0.4)
                continue
            # 2) 面板/结算展示但无确认（纯展示态）→ 领取已完成，ESC 收尾
            if any(k in i.text for i in items
                   for k in ('奖励预览', '已领取', '获得')):
                self.ctx.controller.key('esc')
                self._reshoot(0.4)
                return self.round_success('奖励领取完毕')
            # 3) 点入口；点完无弹窗 = 全领完
            entry = self.find_area('快捷手册-日常', '今日最大活跃度')
            if entry is not None and entry.data is not None:
                if self._entry_no_popup:
                    return self.round_success('奖励全部领取完毕')
                self.ctx.controller.click(entry.data.center)
                self._claimed = True
                self._reshoot(0.5)
                items2 = self.ctx.ocr.run(self.shot, Rect(300, 150, 1700, 1080))
                if not any('确认' in i.text or '确定' in i.text
                           or '获得' in i.text or '奖励预览' in i.text
                           for i in items2):
                    self._entry_no_popup = True  # 点了没弹 = 没有可领了
                continue
            # 4) 档位按钮兜底
            labels = [i for i in items if '活跃度已满' in i.text]
            if labels:
                self.ctx.controller.click(labels[0].center)
                self._reshoot(0.4)
                continue
            break
        if self._claimed:
            return self.round_wait('继续领取', wait=0.25)
        return self.round_success('无可领或已领取完毕')

    @from_node('连点领取')
    @node('关闭快捷手册', max_retry=8)
    def close_compendium(self) -> Round:
        """关掉手册为止：点 ✕，识别不到就 ESC；手册画面消失=成功。"""
        if self.shot is not None and not self.ctx.is_screen(self.shot, '快捷手册-日常'):
            return self.round_success('已关闭')
        result = self.find_area('快捷手册-日常', '关闭按钮')
        if result is not None and result.data is not None:
            self.ctx.controller.click(result.data.center)
            return self.round_retry('已点关闭', wait=0.25)
        self.ctx.controller.key('esc')
        return self.round_retry('ESC关闭手册', wait=0.25)

    @from_node('关闭快捷手册')
    @node('返回大世界', max_retry=10)
    def back_world(self) -> Round:
        if self.shot is not None and self.ctx.is_screen(self.shot, '大世界'):
            return self.round_success('大世界')
        # 兜底按 ESC 关掉可能残留的弹窗
        self.ctx.controller.key('esc')
        return self.round_retry('等待大世界', wait=0.25)

    def handle_init(self) -> None:
        App.handle_init(self)
        self._claimed = False      # 本次运行有过领取动作
        self._entry_no_popup = False  # 点入口不再弹奖励 = 全领完
        self._route_grace = 0      # 点完快捷手册按钮后的开页动画宽限轮数
        self._btn_miss = 0         # 快捷手册按钮模板连续未命中次数（≥2 降级 F2）
