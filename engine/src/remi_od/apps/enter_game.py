"""进入游戏：检测当前状态 → (需要时)打开游戏 → 等待标题画面 → 点击进入 → 等待加载进大世界。

画面依赖（assets/screen_info，实测会建档）：
- 打开游戏：点击进入游戏（id_mark）
- 大世界：主界面角标（id_mark）
- 加载中：NOW LOADING 标志（id_mark，用于加快轮询判断）
未建档时节点会以明确的"画面未建档"状态失败，方便实测会补齐。
"""

from remi_od.core import config as config_mod
from remi_od.core.operation import Operation, from_node, node
from remi_od.core.round_result import Round


class EnterGameOp(Operation):

    """进入游戏到主界面（大世界）；已在游戏内则直接成功。"""

    op_name = '进入游戏'

    LOADING_TIMEOUT_S = 180

    def handle_init(self) -> None:
        self.ctx.enter_scope('')

    def handle_done(self, result) -> None:
        self.ctx.exit_scope()

    @node('检测游戏窗口', is_start=True)
    def check_window(self) -> Round:
        shot = self.ctx.controller.screenshot()
        if shot is not None:
            self.shot = shot
            if self.ctx.is_screen(self.shot, '大世界'):
                return self.round_success('已在游戏')
            return self.round_success('窗口已开')
        return self.round_fail('窗口未开')

    @from_node('检测游戏窗口', success=False)
    @node('打开游戏')
    def open_game(self) -> Round:
        game_path = config_mod.game_path(self.ctx.paths)
        if not game_path:
            return self.round_fail('未配置游戏路径')
        if not self.ctx.controller.launch_game(game_path):
            return self.round_fail('游戏拉起失败')
        return self.round_success(wait=2)

    @from_node('打开游戏')
    @node('等待游戏窗口', max_retry=60)
    def wait_window(self) -> Round:
        if self.ctx.controller.find_game_window():
            self.ctx.controller.active_window()
            return self.round_success('窗口出现')
        return self.round_retry(wait=0.5)

    @from_node('检测游戏窗口', status='窗口已开')
    @from_node('等待游戏窗口')
    @node('等待标题画面', max_retry=60)
    def wait_enter_screen(self) -> Round:
        """等画面变成大世界/标题页；其他界面（地图/菜单残留）用 ESC 关掉。

        2026-09-27 实测：F10 中途停止一条龙后地图留在屏幕上，下一次运行在此
        干等 60 轮失败——任何非世界/标题画面都先 ESC。
        """
        if self.shot is None:
            return self.round_retry('等待截图')
        if self.ctx.is_screen(self.shot, '大世界'):
            return self.round_success('已在游戏')
        if self.ctx.is_screen(self.shot, '打开游戏'):
            return self.round_success('标题画面')
        self.ctx.controller.key('esc')
        return self.round_retry('ESC关闭残留界面', wait=0.25)

    @from_node('等待标题画面', status='标题画面')
    @node('点击进入游戏', max_retry=40)
    def click_enter(self) -> Round:
        """标题画面连续点击"点击进入游戏"，直到画面离开标题页。

        用户实测：点一下等一下永远进不去——游戏要求连点（首次点击常不生效）。
        """
        from remi_od.core.geometry import Point

        if not self.ctx.is_screen(self.shot, '打开游戏'):
            return self.round_success('已离开标题页')
        result = self.find_area('打开游戏', '点击进入游戏')
        if result is not None and result.data is not None:
            self.ctx.controller.click(result.data.center)
        else:
            self.ctx.controller.click(Point(960, 900))  # 按钮识别不到时兜底连点
        return self.round_wait('连点进入游戏', wait=0.25)

    @from_node('点击进入游戏')
    @node('等待加载', max_retry=9999, timeout_s=LOADING_TIMEOUT_S)
    def wait_loading(self) -> Round:
        if self.shot is None:
            return self.round_retry('等待截图')
        if self.ctx.is_screen(self.shot, '大世界'):
            return self.round_success('大世界')
        return self.round_wait('加载中', wait=1)
