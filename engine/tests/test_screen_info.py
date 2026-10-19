"""画面-区域体系单测。"""

from pathlib import Path

from remi_od.vision.screen_info import ScreenBook

YAML_A = """
screen_name: 主菜单
app_id: ''
area_list:
  - area_name: 设置按钮
    rect: [100, 200, 160, 260]
    id_mark: true
    template: menu/设置
    goto: [设置页]
"""

YAML_B = """
screen_name: 设置页
app_id: ''
area_list:
  - area_name: 返回
    rect: [10, 10, 60, 60]
    id_mark: true
    template: menu/返回
    goto: [主菜单]
  - area_name: 滚动区
    rect: [300, 100, 900, 800]
    id_mark: false
"""


def _make_book(tmp_path: Path, files: dict[str, str]) -> ScreenBook:
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding='utf-8')
    return ScreenBook(tmp_path)


def test_load_and_lookup(tmp_path):
    book = _make_book(tmp_path, {'a.yml': YAML_A, 'b.yml': YAML_B})
    assert set(book.screens) == {'主菜单', '设置页'}
    area = book.get_area('主菜单', '设置按钮')
    assert area is not None
    assert area.rect.as_tuple() == (100, 200, 160, 260)
    assert area.center.x == 130 and area.center.y == 230
    assert area.is_template_area and area.template == 'menu/设置'
    assert book.get_area('主菜单', '不存在') is None


def test_missing_dir(tmp_path):
    book = ScreenBook(tmp_path / 'nope')
    assert book.screens == {}


def test_route_bfs(tmp_path):
    book = _make_book(tmp_path, {'a.yml': YAML_A, 'b.yml': YAML_B})
    route = book.route('主菜单', '设置页')
    assert route is not None and len(route) == 1
    assert route[0].area_name == '设置按钮'
    # 同画面 → 空路径；不可达 → None
    assert book.route('主菜单', '主菜单') == []
    assert book.route('设置页', '不存在的画面') is None


def test_app_scope(tmp_path):
    global_yaml = "screen_name: 全局画面\napp_id: ''\narea_list: []\n"
    app_yaml = "screen_name: 应用画面\napp_id: coffee\narea_list: []\n"
    book = _make_book(tmp_path, {'g.yml': global_yaml, 'c.yml': app_yaml})
    assert '全局画面' in book.screen_names('')
    assert '应用画面' not in book.screen_names('')
    assert '应用画面' in book.screen_names('coffee')
