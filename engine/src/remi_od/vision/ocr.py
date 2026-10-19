"""OCR 识别：RapidOCR 3.x + PP-OCRv6 封装（动态文字画面用，地图区域名/对话选项/按钮文案等）。

模型由 rapidocr wheel 自带（PP-OCRv6 det/rec small），无需联网下载。
"""

import difflib
import threading
from dataclasses import dataclass

import numpy as np

from remi_od.core.geometry import Point, Rect

DEFAULT_LCS = 0.5

# 帧内缓存条目上限（键含截图对象 id，持强引用防 id 复用误命中；约 8 帧内存）
_CACHE_CAP = 8


@dataclass
class OcrItem:

    text: str
    center: Point
    rect: Rect
    score: float


def _to_item(box, text: str, score: float) -> OcrItem:
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    x1, y1, x2, y2 = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
    return OcrItem(text=text, center=Point((x1 + x2) // 2, (y1 + y2) // 2),
                   rect=Rect(x1, y1, x2, y2), score=float(score))


class OcrEngine:

    """RapidOCR 惰性单例封装（带帧内缓存与预热）。

    性能（2026-10-06 本机空载实测，scripts/bench_ocr.py，旧 v3 引擎对照）：
    全图 2.0-2.6s；小裁剪 0.2-0.5s（旧 v3 小裁剪固定开销约 1s+）。
    耗时 ≈ 检测 + 每行识别 ~40ms，行数是主要变量——流程层尽量裁小区域、
    每轮单次 OCR 复用结果（游戏前台抢 CPU 时以上耗时约翻倍）。
    配置：det limit max-1920（默认 min-736 会把小裁剪放大 2.5-9 倍，又慢
    又丢字）+ 关角度分类（游戏文字永不旋转）；width_height_ratio 维持默认 8，
    过扁横条（宽高比 >8）会被检测器整图拒绝，需要时用黑边补足高度。
    """

    def __init__(self):
        self._ocr = None
        # 可重入锁：_run_uncached 持锁期间会经 self.ocr 属性再次取锁
        self._lock = threading.RLock()
        self._cache: dict[tuple, tuple[np.ndarray, list[OcrItem]]] = {}

    def warmup(self) -> None:
        """创建引擎并跑一张空图，把会话初始化与首次推理开销挪到启动期。"""
        self._run_uncached(np.zeros((64, 320, 3), dtype=np.uint8))

    @property
    def ocr(self):
        if self._ocr is None:
            with self._lock:
                if self._ocr is None:
                    from rapidocr import RapidOCR

                    self._ocr = RapidOCR(params={
                        'Det.limit_side_len': 1920,
                        'Det.limit_type': 'max',
                        'Global.use_cls': False,
                    })
        return self._ocr

    def run(self, image: np.ndarray, rect: Rect | None = None) -> list[OcrItem]:
        """OCR 全图或指定区域，返回识别项（按位置从上到下、从左到下排序）。

        同一帧（同一 image 对象）同一区域的重复查询直接走缓存——流程层
        一轮内多次 find_text/同一区域复查不再重复推理。
        """
        if image is None or image.size == 0:
            return []
        key = (id(image), rect.as_tuple() if rect is not None else None)
        hit = self._cache.get(key)
        if hit is not None and hit[0] is image:
            return hit[1]
        items = self._run_uncached(image, rect)
        if len(self._cache) >= _CACHE_CAP:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = (image, items)
        return items

    def _run_uncached(self, image: np.ndarray,
                      rect: Rect | None = None) -> list[OcrItem]:
        with self._lock:
            if rect is not None:
                x1, y1, x2, y2 = rect.as_tuple()
                part = image[max(0, y1):y2, max(0, x1):x2]
                offset = (x1, y1)
            else:
                part = image
                offset = (0, 0)
            if part.size == 0:
                return []
            result = self.ocr(part)
            items = []
            txts = result.txts if result is not None else None
            if txts:
                for box, text, score in zip(result.boxes, result.txts, result.scores):
                    item = _to_item(box, text, score)
                    items.append(OcrItem(
                        text=item.text,
                        center=Point(item.center.x + offset[0], item.center.y + offset[1]),
                        rect=Rect(item.rect.x1 + offset[0], item.rect.y1 + offset[1],
                                  item.rect.x2 + offset[0], item.rect.y2 + offset[1]),
                        score=item.score,
                    ))
            items.sort(key=lambda i: (i.rect.y1, i.rect.x1))
            return items

    def find_text(self, image: np.ndarray, target: str,
                  rect: Rect | None = None, lcs: float = DEFAULT_LCS) -> OcrItem | None:
        """在区域中找与 target 模糊匹配的文字（精确包含 或 相似度达标）。"""
        if not target:
            return None
        best: tuple[float, OcrItem] | None = None
        for item in self.run(image, rect):
            if target in item.text:
                return item
            ratio = difflib.SequenceMatcher(None, target, item.text).ratio()
            if ratio >= lcs and (best is None or ratio > best[0]):
                best = (ratio, item)
        return best[1] if best else None
