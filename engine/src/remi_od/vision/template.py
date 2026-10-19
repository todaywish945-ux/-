"""模板匹配：模板图存放在 assets/template/<子目录>/<模板id>/raw.png。"""

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from remi_od.core.geometry import Point, Rect

DEFAULT_THRESHOLD = 0.7


@dataclass
class MatchResult:

    score: float
    center: Point
    rect: Rect


FLAT_TEMPLATE_TOLERANCE = 10.0  # 纯色模板的像素容差（0-255）


def _is_spatially_flat(arr: np.ndarray, tolerance: float = 2.0) -> bool:
    """空间平坦（无纹理）：所有像素与左上角像素几乎相同。

    不能用整体 std 判断——纯色块各通道值不同（如 BGR 60,60,220）时
    元素 std 并不为 0，那是通道间差异不是纹理。
    """
    if arr.size == 0:
        return False
    diff = np.abs(arr.astype(np.int16) - arr[0, 0].astype(np.int16))
    return float(diff.max()) <= tolerance


def match_template(
    source: np.ndarray,
    template: np.ndarray,
    threshold: float = DEFAULT_THRESHOLD,
    mask: np.ndarray | None = None,
) -> list[MatchResult]:
    """在 source（BGR）中找 template，返回过阈值的命中（按分数降序）。

    两种匹配策略：
    - 模板有纹理：TM_CCOEFF_NORMED（threshold 即相关系数阈值）。
      注意 NCC 在零方差（纯色平）源区域会给出虚假 ~1.0 分，
      对这类命中追加像素级比对，差异大则丢弃。
    - 模板本身纯色（std≈0，NCC 无定义）：TM_SQDIFF，按平均像素差 < 10 判命中，
      命中分数换算为 1 - 平均差/255。
    """
    th, tw = template.shape[:2]
    sh, sw = source.shape[:2]
    if th > sh or tw > sw:
        return []

    if _is_spatially_flat(template):
        return _match_flat_template(source, template)

    result = cv2.matchTemplate(source, template, cv2.TM_CCOEFF_NORMED, mask=mask)
    ys, xs = np.where(result >= threshold)
    candidates = sorted(
        (float(result[y, x]), int(x), int(y)) for x, y in zip(xs, ys)
    )
    candidates.reverse()  # 分数降序
    hits: list[MatchResult] = []
    for score, x, y in candidates[:200]:  # 上限保护，防大面积平坦误报
        patch = source[y:y + th, x:x + tw]
        if patch.size == 0:
            continue
        if _is_spatially_flat(patch, tolerance=12.0):
            # 零方差区域的 NCC 分数无意义：改用像素级比对，差异大即丢弃
            diff = cv2.absdiff(patch, template)
            if float(diff.max()) > 12 or float(diff.mean()) > 6:
                continue
        hits.append(MatchResult(
            score=score,
            center=Point(x + tw // 2, y + th // 2),
            rect=Rect(x, y, x + tw, y + th),
        ))
    return hits


def _match_flat_template(source: np.ndarray, template: np.ndarray) -> list[MatchResult]:
    """纯色模板：平方差匹配，平均像素差小于容差的区域都算命中。"""
    th, tw = template.shape[:2]
    sqdiff = cv2.matchTemplate(source, template, cv2.TM_SQDIFF)
    per_pixel = sqdiff / float(th * tw * source.shape[2])
    tol_sq = FLAT_TEMPLATE_TOLERANCE ** 2
    ys, xs = np.where(per_pixel <= tol_sq)
    hits = []
    for x, y in zip(xs, ys):
        mean_diff = float(per_pixel[y, x]) ** 0.5
        hits.append(MatchResult(
            score=1.0 - mean_diff / 255.0,
            center=Point(int(x) + tw // 2, int(y) + th // 2),
            rect=Rect(int(x), int(y), int(x) + tw, int(y) + th),
        ))
    hits.sort(key=lambda m: (m.score, -m.center.y, -m.center.x), reverse=True)
    return hits[:10]


class TemplateStore:

    """按 '<子目录>/<模板id>' 加载并缓存模板图（可选 mask.png）。"""

    def __init__(self, template_dir: Path):
        self.template_dir: Path = template_dir
        self._cache: dict[str, tuple[np.ndarray, np.ndarray | None]] = {}

    def get(self, template_id: str) -> tuple[np.ndarray, np.ndarray | None] | None:
        if template_id in self._cache:
            return self._cache[template_id]
        folder = self.template_dir / template_id
        raw_file = folder / 'raw.png'
        if not raw_file.exists():
            return None
        template = cv2.imdecode(np.fromfile(str(raw_file), dtype=np.uint8), cv2.IMREAD_COLOR)
        if template is None:
            return None
        mask = None
        mask_file = folder / 'mask.png'
        if mask_file.exists():
            mask = cv2.imdecode(np.fromfile(str(mask_file), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        self._cache[template_id] = (template, mask)
        return (template, mask)
