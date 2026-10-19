"""模板匹配单测（合成图）。"""

import numpy as np

from remi_od.vision.template import match_template


def _synthetic() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(42)
    source = rng.integers(0, 255, size=(400, 600, 3), dtype=np.uint8)
    patch = rng.integers(0, 255, size=(30, 50, 3), dtype=np.uint8)
    source[110:140, 320:370] = patch  # 贴在 (320, 110)
    return source, patch


def test_exact_match_location():
    source, patch = _synthetic()
    hits = match_template(source, patch, threshold=0.9)
    assert hits, '精确贴片必须命中'
    best = hits[0]
    assert best.score > 0.99
    assert abs(best.center.x - 345) <= 1 and abs(best.center.y - 125) <= 1


def test_no_match():
    rng = np.random.default_rng(7)
    source = rng.integers(0, 255, size=(100, 100, 3), dtype=np.uint8)
    other = rng.integers(0, 255, size=(20, 20, 3), dtype=np.uint8)
    assert match_template(source, other, threshold=0.95) == []


def test_template_larger_than_source():
    rng = np.random.default_rng(1)
    source = rng.integers(0, 255, size=(50, 50, 3), dtype=np.uint8)
    big = rng.integers(0, 255, size=(100, 100, 3), dtype=np.uint8)
    assert match_template(source, big) == []
