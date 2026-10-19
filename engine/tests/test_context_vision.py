"""EngineContext 识别链路集成测试：画面 YAML + 模板图 → find_area / is_screen / which_screen。"""

from pathlib import Path

import cv2
import numpy as np

from remi_od.core.context import EngineContext


def _make_shot_with_button() -> np.ndarray:
    """深灰底图，在 (800, 900) 附近放一个亮红块当"按钮"。"""
    shot = np.full((1080, 1920, 3), 40, dtype=np.uint8)
    shot[880:920, 780:830] = (60, 60, 220)  # BGR 红
    return shot


def _setup_engine(tmp_path: Path, shot: np.ndarray) -> EngineContext:
    engine = tmp_path
    # 模板 = 按钮本体
    tpl_dir = engine / 'assets' / 'template' / 'menu' / '按钮'
    tpl_dir.mkdir(parents=True)
    patch = shot[880:920, 780:830].copy()
    cv2.imencode('.png', patch)[1].tofile(str(tpl_dir / 'raw.png'))
    # 画面建档
    screen_dir = engine / 'assets' / 'screen_info'
    screen_dir.mkdir(parents=True)
    (screen_dir / '主界面.yml').write_text("""
screen_name: 主界面
app_id: ''
area_list:
  - area_name: 菜单按钮
    rect: [700, 850, 900, 950]
    id_mark: true
    template: menu/按钮
""", encoding='utf-8')
    ctx = EngineContext(engine)
    return ctx


def test_find_area_hit(tmp_path):
    shot = _make_shot_with_button()
    ctx = _setup_engine(tmp_path, shot)
    result = ctx.find_area(shot, '主界面', '菜单按钮')
    assert result is not None
    center = result.data.center
    # 模板在裁剪区域内匹配，命中中心应为按钮中心 (805, 900)
    assert abs(center.x - 805) <= 2 and abs(center.y - 900) <= 2


def test_find_area_miss(tmp_path):
    shot = _make_shot_with_button()
    ctx = _setup_engine(tmp_path, shot)
    blank = np.full((1080, 1920, 3), 40, dtype=np.uint8)
    assert ctx.find_area(blank, '主界面', '菜单按钮') is None


def test_is_screen_and_which(tmp_path):
    shot = _make_shot_with_button()
    ctx = _setup_engine(tmp_path, shot)
    assert ctx.is_screen(shot, '主界面')
    assert ctx.which_screen(shot) == '主界面'
    blank = np.full((1080, 1920, 3), 40, dtype=np.uint8)
    assert not ctx.is_screen(blank, '主界面')
    assert ctx.which_screen(blank) is None


def test_undefined_area_raises(tmp_path):
    shot = _make_shot_with_button()
    ctx = _setup_engine(tmp_path, shot)
    import pytest

    with pytest.raises(ValueError):
        ctx.find_area(shot, '主界面', '没这个区域')


def test_plain_rect_area_always_hits(tmp_path):
    """无模板无文本的纯坐标区域：视为命中（固定点击位）。"""
    engine = tmp_path
    screen_dir = engine / 'assets' / 'screen_info'
    screen_dir.mkdir(parents=True)
    (screen_dir / '纯坐标.yml').write_text("""
screen_name: 纯坐标画面
app_id: ''
area_list:
  - area_name: 固定按钮
    rect: [100, 100, 200, 200]
""", encoding='utf-8')
    ctx = EngineContext(engine)
    shot = np.zeros((1080, 1920, 3), dtype=np.uint8)
    result = ctx.find_area(shot, '纯坐标画面', '固定按钮')
    assert result is not None
    assert (result.data.center.x, result.data.center.y) == (150, 150)
