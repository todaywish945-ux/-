"""标准 1920x1080 坐标系下的基础几何类型。"""

from dataclasses import dataclass

STANDARD_WIDTH = 1920
STANDARD_HEIGHT = 1080


@dataclass(frozen=True)
class Point:

    x: int
    y: int

    def __add__(self, other: 'Point') -> 'Point':
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other: 'Point') -> 'Point':
        return Point(self.x - other.x, self.y - other.y)

    def as_tuple(self) -> tuple[int, int]:
        return (self.x, self.y)


@dataclass(frozen=True)
class Rect:

    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def left_top(self) -> Point:
        return Point(self.x1, self.y1)

    @property
    def center(self) -> Point:
        return Point((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)

    def contains(self, p: Point) -> bool:
        return self.x1 <= p.x < self.x2 and self.y1 <= p.y < self.y2

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.x1, self.y1, self.x2, self.y2)
