"""录像店营业：录像带店日常经营（宣传/上架/营业/结算）。无消耗，产出菲林与丁尼。

移植自原项目 RandomPlayApp，传送点用「澄辉坪-录像店营业点」。
2026-09-25 实测：该落点离柜台 NPC 阿玖有一段距离（名字牌出现在画面上方 y≈390，
官方参考图的交互距离下名字牌在 y≈800），直接按 F 无反应——需朝名字牌转向并
前移进入交互距离。交互后先出阿玖旁白/问句，点击底部对话文字推进后右侧才出现
「查看经营状况」选项；对话状态中按 F 无效。
简化：宣传员固定选 1 号位（原版支持按代理人名/头像选择，日常收益无差别）。
"""

from remi_od.apps.schedule_transport import ScheduleTransport
from remi_od.apps.transport import Transport
from remi_od.core.app import App
from remi_od.core.geometry import Point
from remi_od.core.operation import from_node, node
from remi_od.core.round_result import Round

APP_ID = 'random_play'
APP_NAME = '录像店随机游玩'

STATUS_ALREADY_RUNNING = '正在营业'
STATUS_ALL_VIDEO_CHOOSE = '已选择全部录像带'

# 全部录像带主题（原项目 _all_video_themes）
ALL_VIDEO_THEMES = [
    '纪实', '怀旧', '冒险', '幻想', '喜剧', '动作', '惊悚', '悬疑',
    '访谈', '都市', '时尚', '灾难', '悲剧', '亲情', '广告', '爱情',
]


class RandomPlayApp(App):

    def __init__(self, ctx):
        App.__init__(self, ctx, app_id=APP_ID, app_name=APP_NAME,
                     description='录像店营业（宣传/上架/营业/结算）')

    def handle_init(self) -> None:
        App.handle_init(self)
        self._rec_clicked: bool = False  # 本轮已点过"推荐上架"
        self._shelved: bool = False  # 录像带确认上架（"下架"按钮出现）
        self._retransported: bool = False  # 交互失败重传送只允许一次
        self._diag_rounds: int = 0
        self._f_tries: int = 0

    @node('确认在大世界', is_start=True, max_retry=15)
    def check_world(self) -> Round:
        if self.shot is None:
            return self.round_retry('等待截图')
        if self.ctx.is_screen(self.shot, '大世界'):
            return self.round_success('大世界')
        try:  # 诊断：截图 + id_mark 分数
            self.ctx.save_debug_image('rp_不在大世界', self.shot)
            from remi_od.core.log import log as _log
            import cv2
            for a in self.ctx.screen_book.screens['大世界'].id_marks:
                pair = self.ctx.templates.get(a.template)
                if pair:
                    x1, y1, x2, y2 = a.rect.as_tuple()
                    res = cv2.matchTemplate(self.shot[y1:y2, x1:x2], pair[0],
                                            cv2.TM_CCOEFF_NORMED)
                    _log('录像店诊断', f'{a.area_name} 分数 {res.max():.3f}')
        except Exception as e:
            pass
        # 剧情对话开着时 ESC 无效（对话必须点击推进——用户既证）；
        # 带选项的问句点文字无反应，必须点选项（2026-10-07 咖啡问句实测）
        from remi_od.core.geometry import Rect
        result = self.find_area('快捷手册-日常', '关闭按钮')
        if result is not None and result.data is not None:
            self.ctx.controller.click(result.data.center)
            return self.round_retry('已点关闭', wait=0.35)
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
        """日程传送（F2 日常页"前往"直达）优先；地图传送兜底。"""
        result = ScheduleTransport(self.ctx, 'random_play').execute(op_timeout_s=90)
        if result.success:
            return self.round_success(result.status)
        if '任务卡不在' in (result.status or ''):
            return self.round_success('录像店已完成')
        op = Transport(self.ctx, '澄辉坪', '录像店营业点')
        result = op.execute(op_timeout_s=180)
        if result.success:
            return self.round_success(result.status)
        return self.round_fail(result.status or '传送失败')

    @from_node('传送')
    @from_node('交互失败重传送')
    @node('接近交互', max_retry=30)
    def approach_and_interact(self) -> Round:
        """传送后一直按 F 直到出现对话（用户实测流程，同昨日成功路径）。

        每轮：先按 F（加载中按掉也无妨；对话状态中按 F 无效、无害），
        再检查画面：选项→点击进入经营；对话文字/标题→点击推进。
        """
        import time

        if self._f_tries == 0:
            time.sleep(0.25)  # 防交互无效（官方 issue #2405）
        self._f_tries += 1
        self.ctx.controller.key('f', press_time=0.2)
        self._reshoot(0.35)  # F 后同轮复检（对话/经营画面可能已出现）
        self._diag_rounds += 1
        if self._diag_rounds % 4 == 1:
            try:
                self.ctx.save_debug_image('rp_对话诊断', self.shot)
            except Exception:
                pass
        if self.shot is not None and self.ctx.is_screen(self.shot, '影像店营业'):
            return self.round_success('已在经营画面')
        # 轮内连点推进对话（提速）：点→重拍→再点，直到选项出现；一次 OCR 判定状态
        import difflib

        from remi_od.core.geometry import Rect
        option_area = self.ctx.get_area('影像店营业', '右侧选项区域')
        dialog_area = Rect(400, 880, 1500, 970)
        scan = Rect(400, 530, 1914, 980)
        for _ in range(3):  # 一轮内最多推进 3 段对话
            items = self.ctx.ocr.run(self.shot, scan)
            # 选项出现 → 按 1 选第一个（热键，避免点歪）
            has_option = False
            for it in items:
                if not option_area.rect.contains(it.center):
                    continue
                if '查看经营状况' in it.text or difflib.SequenceMatcher(
                        None, '查看经营状况', it.text).ratio() >= 0.5:
                    self.ctx.controller.key('1', press_time=0.1)
                    return self.round_success('已按1查看经营状况', wait=0.25)
            # 底部对话长句 / 标题有字 → 点击推进
            dialog = [t for t in items if dialog_area.contains(t.center) and len(t.text) >= 8]
            title_area = Rect(840, 780, 1080, 860)
            title = [t for t in items if title_area.contains(t.center)]
            if dialog:
                self.ctx.controller.click(dialog[-1].center)
            elif title:
                self.ctx.controller.click(title[0].center)  # 标题区有字才点（裸矩形陷阱）
            else:
                break
            self._reshoot(0.35)
        return self.round_wait(f'按F等对话({self._f_tries})', wait=0.25)

    def _find_npc_tag(self, surname: str):
        """在大世界画面找 NPC 名字牌（如 阿玖，OCR 常误读为 阿廿/阿甘）。

        名字牌特征：短文本、含姓氏字、位于对话线下方以外的画面上部。
        """
        from remi_od.core.geometry import Rect

        for item in self.ctx.ocr.run(self.shot, Rect(400, 150, 1500, 800)):
            text = item.text.replace('《', '').replace('》', '')
            if surname in text and len(text) <= 6 and item.rect.y2 - item.rect.y1 <= 40:
                return item
        return None

    @from_node('接近交互', success=False)
    @node('交互失败重传送', max_retry=1)
    def retry_transport(self) -> Round:
        """交互走不通（官方机制）：重新传送一次再试，仍失败则应用失败。"""
        if self._retransported:
            return self.round_fail('重传送已用尽')
        self._retransported = True
        op = Transport(self.ctx, '澄辉坪', '录像店营业点')
        result = op.execute(op_timeout_s=180)
        if result.success:
            return self.round_success('已重传送')
        return self.round_fail(result.status or '重传送失败')

    @from_node('接近交互')
    @node('等待经营画面', max_retry=10)
    def wait_run(self) -> Round:
        if self.shot is None:
            return self.round_retry('等待截图')
        # 每日首次：昨日账本弹窗 → 关掉再判
        if self.find_area('影像店营业', '昨日账本') is not None:
            close = self.find_area('影像店营业', '按钮-关闭')
            if close is not None and close.data is not None:
                self.ctx.controller.click(close.data.center)
            return self.round_retry('关闭昨日账本', wait=0.25)
        # 用户流程：进店第一件事点"领取奖励"（昨日营收），连点到消失
        from remi_od.core.geometry import Rect
        items = self.ctx.ocr.run(self.shot, Rect(300, 400, 1700, 1000))
        claim = next((i for i in items if '领取奖励' in i.text), None)
        if claim is not None:
            self.ctx.controller.click(claim.center)
            self._reshoot(0.3)
            return self.round_retry('连点领取奖励', wait=0.2)
        # 领取过程弹出的确认 → 就近点掉
        confirm = next((i for i in items
                        if i.center.y > 500 and ('确认' in i.text or '确定' in i.text)), None)
        if confirm is not None:
            self.ctx.controller.click(confirm.center)
            return self.round_retry('点结算确认', wait=0.25)
        # 点一下经营状况标签保证在该分支
        result = self.find_area('影像店营业', '经营状况')
        if result is not None and result.data is not None:
            self.ctx.controller.click(result.data.center)
            return self.round_success(wait=0.4)
        return self.round_retry('等待经营画面', wait=0.25)

    @from_node('等待经营画面')
    @node('识别营业状态', max_retry=10)
    def check_running(self) -> Round:
        """进经营页先巡检："换下"可见=宣传员已选、"下架"可见=录像带已上架，
        跳过对应环节只补缺的；避免空手点开张→弹警告→回炉的往返
        （2026-10-05 二次实测每次回炉往返 30-65 秒）。"""
        if self.find_area('影像店营业', '正在营业') is not None:
            return self.round_success(STATUS_ALREADY_RUNNING)
        self._promoter_ready = self.find_area('影像店营业', '换下') is not None
        self._shelved = self.find_area('影像店营业', '下架') is not None
        return self.round_success('未营业')

    @from_node('识别营业状态', status=STATUS_ALREADY_RUNNING)
    @node('关闭经营页面', max_retry=5)
    def close_business(self) -> Round:
        return self.round_by_find_and_click('影像店营业', '返回', wait=0.25)

    @from_node('识别营业状态')
    @from_node('确认营业', success=False, status='需选宣传员，回炉')
    @node('点击宣传员入口')
    def click_promoter_entry(self) -> Round:
        return self.round_by_click_area('影像店营业', '宣传员入口', wait=0.25)

    @from_node('点击宣传员入口')
    @node('选择宣传员', max_retry=15)
    def choose_promoter(self) -> Round:
        """入口点击可能不生效——没点开就一直点，直到"选择宣传员"界面出现
        （用户要求：无论做什么都点，直到出现新界面）。"""
        if getattr(self, '_promoter_ready', False):
            return self.round_success('宣传员已选(巡检)')
        if self.find_area('影像店营业', '选择宣传员') is None:
            self.round_by_click_area('影像店营业', '宣传员入口', wait=0.3)
            self._reshoot(0.5)
            if self.find_area('影像店营业', '选择宣传员') is None:
                return self.round_retry('连点宣传员入口', wait=0.25)
        try:  # 诊断截图
            self.ctx.save_debug_image('rp_选宣传员', self.shot)
        except Exception:
            pass
        # 已经选过 → 直接返回
        if self.find_area('影像店营业', '换下') is not None:
            return self.round_by_find_and_click('影像店营业', '返回', wait=0.25)
        # 固定选 1 号位
        self.round_by_click_area('影像店营业', '宣传员-1')
        self._reshoot(0.3)  # 确认按钮随后出现，同轮复检省一轮
        from remi_od.core.geometry import Rect
        for word in ('确认', '确定'):
            item = self.ctx.ocr.find_text(self.shot, word,
                                          Rect(1200, 950, 1920, 1080), lcs=0.9)
            if item is not None:
                self.ctx.controller.click(item.center)
                return self.round_success(f'已选{word}', wait=0.25)
        return self.round_retry('未找到确认', wait=0.25)

    @from_node('选择宣传员')
    @node('点击录像带入口')
    def click_video_entry(self) -> Round:
        return self.round_by_click_area('影像店营业', '录像带入口', wait=0.25)

    @from_node('点击录像带入口')
    @from_node('确认营业', success=False, status='未上架录像带，回炉重上')
    @node('推荐上架录像带', max_retry=15)
    def recommend_shelf(self) -> Round:
        """用户流程（2026-09-29）：点右下角"推荐上架"再点"上架"，不挑主题。

        每一步都以画面为准推进并验证（"下架"出现=真上架了），任何点击
        未生效就原地重试；绝不在未验证上架前放行到开始营业。
        """
        from remi_od.core.geometry import Rect
        try:
            self.ctx.save_debug_image('rp_上架步骤', self.shot)
        except Exception:
            pass
        # 录像带画面判定：上架筛选/推荐上架可见才算进来了
        # （不能用"经营状况消失"判定——画面动画期间模板残留会误判，
        #   导致反复点击录像带入口把画面开关开关，永远到不了上架）
        on_tape = (self.find_area('影像店营业', '上架筛选') is not None
                   or self.find_area('影像店营业', '推荐上架') is not None)
        if not on_tape:
            if self._shelved:
                return self.round_success('已上架')
            if self.find_area('影像店营业', '经营状况') is not None:
                if self._rec_clicked:
                    # 点过"上架"后回到经营页 = 上架已完成（游戏会自动返回）
                    self._shelved = True
                    return self.round_success('已上架并返回经营页')
                self._rec_clicked = False
                self.round_by_click_area('影像店营业', '录像带入口', wait=0.25)
                self._reshoot(0.3)  # 等画面动画完成再复检
                on_tape = (self.find_area('影像店营业', '上架筛选') is not None
                           or self.find_area('影像店营业', '推荐上架') is not None)
                if not on_tape:
                    return self.round_retry('进入录像带画面', wait=0.25)
            else:
                return self.round_retry('等待录像带画面', wait=0.25)
        # 上架确认弹窗 → 点掉
        confirm = self.ctx.ocr.find_text(self.shot, '确认', Rect(700, 400, 1300, 900), lcs=0.9)
        if confirm is not None:
            self.ctx.controller.click(confirm.center)
            self._reshoot(0.3)
            return self.round_retry('点上架确认', wait=0.2)
        # 已上架判定：按钮翻转为"下架" → 点返回回经营页
        if self.find_area('影像店营业', '下架') is not None:
            self._shelved = True
            back = self.find_area('影像店营业', '返回')
            if back is not None and back.data is not None:
                self.ctx.controller.click(back.data.center)
            return self.round_success('已上架')
        # 步骤 1：推荐上架
        if not self._rec_clicked:
            rec = self.find_area('影像店营业', '推荐上架')
            if rec is not None and rec.data is not None:
                self._rec_clicked = True
                self.ctx.controller.click(rec.data.center)
                self._reshoot(0.3)
                return self.round_retry('已点推荐上架', wait=0.2)
            return self.round_retry('等待推荐上架按钮', wait=0.25)
        # 步骤 2：点"上架"
        shelf = self.find_area('影像店营业', '上架')
        if shelf is not None and shelf.data is not None:
            self.ctx.controller.click(shelf.data.center)
            self._reshoot(0.3)
            return self.round_retry('已点上架', wait=0.2)
        return self.round_retry('等待上架按钮', wait=0.25)

    @from_node('推荐上架录像带')
    @node('返回经营页', max_retry=5)
    def back_to_status(self) -> Round:
        if self.find_area('影像店营业', '经营状况') is not None:
            return self.round_success('经营状况')
        return self.round_by_find_and_click('影像店营业', '返回', wait=0.25)

    @from_node('返回经营页')
    @node('开始营业', max_retry=5)
    def start_business(self) -> Round:
        return self.round_by_ocr_and_click('开始营业', '影像店营业', '开始营业', wait=0.25)

    @from_node('开始营业')
    @from_node('识别营业状态', status='已点开始营业')
    @node('确认营业', max_retry=10)
    def confirm_business(self) -> Round:
        """开张确认：弹窗按宽区域找"确认"点击；警告弹窗判明缺什么后
        round_fail 走对应失败边回炉（缺录像带→上架链，缺宣传员→选人链）。
        """
        from remi_od.core.geometry import Rect

        # 先读弹窗文字判明类型（警告弹窗上也有确认按钮——先点确认会把它
        # 当成功吞掉，2026-10-02 借号实测"没选人没上架就开张"即此因）
        warn_text = ''.join(i.text for i in self.ctx.ocr.run(self.shot, Rect(500, 400, 1500, 750)))
        # 警告弹窗：判明缺什么 → 点掉 → 对应失败边回炉
        if '还未上架' in warn_text or ('录像带' in warn_text and '上架' in warn_text):
            confirm = self.ctx.ocr.find_text(self.shot, '确认', Rect(500, 400, 1500, 800), lcs=0.9)
            if confirm is not None:
                self.ctx.controller.click(confirm.center)
            self._rec_clicked = False
            self._shelved = False
            return self.round_fail('未上架录像带，回炉重上')
        if '宣传员' in warn_text:
            confirm = self.ctx.ocr.find_text(self.shot, '确认', Rect(500, 400, 1500, 800), lcs=0.9)
            if confirm is not None:
                self.ctx.controller.click(confirm.center)
            return self.round_fail('需选宣传员，回炉')
        # 无警告 → 正常开张确认（宽区域找确认按钮）
        ok = self.ctx.ocr.find_text(self.shot, '确认', Rect(600, 400, 1500, 900), lcs=0.9)
        if ok is not None:
            self.ctx.controller.click(ok.center)
            return self.round_success('已点开张确认', wait=0.4)
        return self.round_by_find_and_click('影像店营业', '开始营业-确认', wait=0.35)

    @from_node('确认营业')
    @node('营业后确认', max_retry=10)
    def confirm_after(self) -> Round:
        return self.round_by_ocr_and_click('确认', '影像店营业', '营业后确认',
                                           lcs=0.9, wait=1)

    @from_node('营业后确认')
    @from_node('关闭经营页面')
    @node('返回大世界', max_retry=10)
    def back_world(self) -> Round:
        if self.shot is not None and self.ctx.is_screen(self.shot, '大世界'):
            return self.round_success('大世界')
        self.ctx.controller.key('esc')
        return self.round_retry('等待大世界', wait=0.25)
