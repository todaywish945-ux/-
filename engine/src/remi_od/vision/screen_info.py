"""画面-区域体系：加载 assets/screen_info 下的 YAML 建档，提供区域查询与画面路由。

YAML 格式（每个文件一个画面）::

    screen_name: 咖啡店        # 画面名（查询 key，全局唯一）
    app_id: coffee            # 归属应用；空字符串表示全局画面
    area_list:
      - area_name: 点单        # 区域名（画面内唯一）
        rect: [1702, 880, 1914, 1020]   # 1920x1080 标准坐标 x1,y1,x2,y2
        id_mark: true          # 是否画面判定区域（全部命中才算该画面）
        template: 咖啡店/点单按钮   # 模板 <子目录>/<模板id>；与 ocr_text 二选一
        threshold: 0.7         # 模板匹配阈值（默认 0.7）
        ocr_text: ''           # OCR 文本（预留，未接 OCR）
        goto: []               # 点击该区域后可能到达的画面名列表（路由边）
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from remi_od.core.geometry import Point, Rect


@dataclass
class ScreenArea:

    screen_name: str
    area_name: str
    rect: Rect
    id_mark: bool = False
    template: str = ''
    threshold: float = 0.7
    ocr_text: str = ''
    goto: list[str] = field(default_factory=list)
    alt: bool = False  # 点击前需按住 ALT 解锁光标（大世界等锁鼠标画面）
    lcs: float = 0.5  # OCR 文字匹配相似度阈值

    @property
    def key(self) -> str:
        return f'{self.screen_name}.{self.area_name}'

    @property
    def left_top(self) -> Point:
        return self.rect.left_top

    @property
    def center(self) -> Point:
        return self.rect.center

    @property
    def is_template_area(self) -> bool:
        return self.template != ''

    @property
    def is_text_area(self) -> bool:
        return self.ocr_text != ''


@dataclass
class Screen:

    screen_name: str
    app_id: str = ''
    area_list: list[ScreenArea] = field(default_factory=list)

    @property
    def id_marks(self) -> list[ScreenArea]:
        return [a for a in self.area_list if a.id_mark]


def _parse_area(screen_name: str, raw: dict) -> ScreenArea:
    rect_raw = raw.get('rect') or [0, 0, 0, 0]
    return ScreenArea(
        screen_name=screen_name,
        area_name=raw.get('area_name', ''),
        rect=Rect(*[int(v) for v in rect_raw]),
        id_mark=bool(raw.get('id_mark', False)),
        template=raw.get('template', ''),
        threshold=float(raw.get('threshold', 0.7)),
        ocr_text=raw.get('ocr_text', ''),
        goto=list(raw.get('goto') or []),
        alt=bool(raw.get('alt', False)),
        lcs=float(raw.get('lcs', 0.5)),
    )


class ScreenBook:

    """全部画面建档的内存索引。"""

    def __init__(self, screen_dir: Path):
        self.screen_dir: Path = screen_dir
        self.screens: dict[str, Screen] = {}
        self._area_map: dict[str, ScreenArea] = {}
        self.reload()

    def reload(self) -> None:
        self.screens = {}
        self._area_map = {}
        if not self.screen_dir.exists():
            return
        for file in sorted(self.screen_dir.glob('*.yml')):
            if file.name.startswith('_'):
                continue
            try:
                raw = yaml.safe_load(file.read_text(encoding='utf-8')) or {}
            except yaml.YAMLError:
                continue
            name = raw.get('screen_name')
            if not name:
                continue
            screen = Screen(
                screen_name=name,
                app_id=raw.get('app_id', '') or '',
                area_list=[_parse_area(name, a) for a in raw.get('area_list') or []],
            )
            self.screens[name] = screen
            for area in screen.area_list:
                self._area_map[area.key] = area

    def get_area(self, screen_name: str, area_name: str) -> ScreenArea | None:
        return self._area_map.get(f'{screen_name}.{area_name}')

    def screen_names(self, app_id: str = '') -> list[str]:
        """app_id 为空返回全部；否则返回全局画面 + 该应用画面。"""
        names = [s.screen_name for s in self.screens.values() if not s.app_id]
        if app_id:
            names += [s.screen_name for s in self.screens.values() if s.app_id == app_id]
        return names

    def route(self, from_screen: str, to_screen: str) -> list[ScreenArea] | None:
        """BFS 找从 from_screen 到 to_screen 的点击序列；不可达返回 None。"""
        if from_screen == to_screen:
            return []
        visited = {from_screen}
        queue: list[tuple[str, list[ScreenArea]]] = [(from_screen, [])]
        while queue:
            current, path = queue.pop(0)
            screen = self.screens.get(current)
            if screen is None:
                continue
            for area in screen.area_list:
                for nxt in area.goto:
                    if nxt in visited:
                        continue
                    new_path = path + [area]
                    if nxt == to_screen:
                        return new_path
                    visited.add(nxt)
                    queue.append((nxt, new_path))
        return None
