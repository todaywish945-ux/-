"""离线画面验证：用官方测试仓的归档真实截图验证识别链路。

归档位置（仅开发机存在，缺失时跳过）：
D:\\ZenlessZoneZero-OneDragon\\zzz-od-test\\screens
"""

from pathlib import Path

import cv2
import numpy as np
import pytest

from remi_od.core.context import EngineContext

ARCHIVE = Path(r'D:\ZenlessZoneZero-OneDragon\zzz-od-test\screens')
ENGINE_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    not ARCHIVE.exists(), reason='官方截图归档不存在（非开发机）')


def load_shot(rel: str) -> np.ndarray:
    path = ARCHIVE / rel
    image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    assert image is not None, f'无法读取 {path}'
    return image


@pytest.fixture(scope='module')
def ctx() -> EngineContext:
    return EngineContext(ENGINE_ROOT)


def test_world_screen(ctx):
    shot = load_shot('大世界/普通.webp')
    assert ctx.is_screen(shot, '大世界')
    assert ctx.which_screen(shot) == '大世界'


def test_daily_page_screen(ctx):
    shot = load_shot('快捷手册-日常/默认.webp')
    assert ctx.is_screen(shot, '快捷手册-日常')
    assert not ctx.is_screen(shot, '大世界'), '日常页不应误判为大世界'
    assert ctx.which_screen(shot) == '快捷手册-日常'


def test_title_screen(ctx):
    shot = load_shot('打开游戏/ready.webp')
    assert ctx.is_screen(shot, '打开游戏')


def test_daily_page_not_title(ctx):
    shot = load_shot('快捷手册-日常/默认.webp')
    assert not ctx.is_screen(shot, '打开游戏')


def test_tab_daily_inactive_matches(ctx):
    """TAB-日常 模板为白色（未激活）状态：在其他 TAB 页应命中，激活页不命中。"""
    battle_page = load_shot('快捷手册/作战TAB.webp')
    result = ctx.find_area(battle_page, '快捷手册-日常', 'TAB-日常')
    assert result is not None, '作战页上应能找到未激活的日常TAB'
    center = result.data.center
    assert 880 <= center.x <= 1090, f'TAB 命中位置异常: {center}'

    daily_page = load_shot('快捷手册-日常/默认.webp')
    assert ctx.find_area(daily_page, '快捷手册-日常', 'TAB-日常') is None, \
        '日常页上该TAB已激活（黄色），模板不应命中'


def test_close_button_on_daily_page(ctx):
    shot = load_shot('快捷手册-日常/默认.webp')
    result = ctx.find_area(shot, '快捷手册-日常', '关闭按钮')
    assert result is not None, '日常页应能找到关闭(✕)按钮'
    center = result.data.center
    assert 1721 <= center.x <= 1799 and 229 <= center.y <= 307

    world = load_shot('大世界/普通.webp')
    assert ctx.find_area(world, '快捷手册-日常', '关闭按钮') is None, '大世界不应误命中'


def test_reward_claimed_marker(ctx):
    """活跃度奖励-4 完成标记：默认截图（活跃未满/未领取）不应误报。"""
    shot = load_shot('快捷手册-日常/默认.webp')
    # 默认截图状态未知，只验证不崩溃；真正语义靠实测调优
    ctx.find_area(shot, '快捷手册-日常', '活跃度奖励-4')


def test_compendium_button_in_world(ctx):
    shot = load_shot('大世界/普通.webp')
    result = ctx.find_area(shot, '大世界', '快捷手册')
    assert result is not None
    center = result.data.center
    assert 1440 <= center.x <= 1679 and 29 <= center.y <= 113


def test_enter_button_on_title(ctx):
    shot = load_shot('打开游戏/ready.webp')
    result = ctx.find_area(shot, '打开游戏', '点击进入游戏')
    assert result is not None, '标题画面应能识别到点击进入游戏按钮'
