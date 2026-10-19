"""OCR 基准测试：新旧引擎在 debug 真实截图上的速度与识别对比（离线，不碰游戏）。

旧引擎：rapidocr_onnxruntime 1.2.3 + PP-OCRv3（assets/ocr_config.yaml）；
新引擎：rapidocr 3.x + PP-OCRv6（wheel 自带模型），参数对齐旧配置的关键行为：
det limit max-1920（小裁剪不放大）、width_height_ratio 8（扁横条拒绝语义不变）、关角度分类。

用法：python scripts/bench_ocr.py
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import cv2
import numpy as np

DEBUG_DIR = ROOT / 'debug'

# 代表性场景：全图（地图页 OCR 最重）、签到下半屏、日程任务卡区域、对话区
CASES = [
    ('全图-地图页', '082609_transport_选区域.png', None),
    ('签到下半屏', '082641_bakery_collect.png', (0, 400, 1920, 1080)),
    ('日程任务卡', '083405_schedule_找前往.png', (300, 380, 1750, 1010)),
    ('对话区域', '083628_engagement_F2诊断.png', (400, 860, 1500, 1060)),
]

# 各场景应能识别到的关键词（识别质量抽查，两边都应命中）
MUST_HAVE = {
    '全图-地图页': [],
    '签到下半屏': [],
    '日程任务卡': ['前往'],
    '对话区域': [],
}

NEW_PARAMS = {
    'Det.limit_side_len': 1920,
    'Det.limit_type': 'max',
    'Global.use_cls': False,
}


def load_image(name: str) -> np.ndarray:
    img = cv2.imdecode(np.fromfile(str(DEBUG_DIR / name), dtype=np.uint8),
                       cv2.IMREAD_COLOR)
    assert img is not None, f'读图失败: {name}'
    return img


def run_old(img: np.ndarray, rect):
    from rapidocr_onnxruntime import RapidOCR

    engine = run_old._engine  # type: ignore[attr-defined]
    part = img
    if rect is not None:
        x1, y1, x2, y2 = rect
        part = img[y1:y2, x1:x2]
    result, _ = engine(part)
    return [(r[1], float(r[2])) for r in result or []]


def run_new(img: np.ndarray, rect):
    engine = run_new._engine  # type: ignore[attr-defined]
    part = img
    if rect is not None:
        x1, y1, x2, y2 = rect
        part = img[y1:y2, x1:x2]
    result = engine(part)
    if result is None or result.txts is None:
        return []
    return [(t, float(s)) for t, s in zip(result.txts, result.scores)]


def bench(label: str, fn, img: np.ndarray, rect, rounds: int = 2) -> tuple[float, list]:
    fn(img, rect)  # 预热（首次含会话初始化）
    times = []
    texts: list = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        texts = fn(img, rect)
        times.append(time.perf_counter() - t0)
    print(f'    {label}: {min(times):.2f}s（{len(texts)} 行）')
    return min(times), texts


def main() -> int:
    # 引擎惰性单例挂到函数属性上，两边各自只初始化一次
    from pathlib import Path as _P

    from rapidocr import RapidOCR as NewOCR

    run_new._engine = NewOCR(params=NEW_PARAMS)  # type: ignore[attr-defined]

    old_cfg = ROOT / 'assets' / 'ocr_config.yaml'
    from rapidocr_onnxruntime import RapidOCR as OldOCR

    run_old._engine = (OldOCR(config_path=str(old_cfg))  # type: ignore[attr-defined]
                       if old_cfg.exists() else OldOCR())

    print(f'{"场景":<10} {"区域":<8} {"旧v3":>8} {"新v6":>8} {"提速":>6}')
    total_old = total_new = 0.0
    for name, png, rect in CASES:
        img = load_image(png)
        t_old, texts_old = bench('旧', run_old, img, rect)
        t_new, texts_new = bench('新', run_new, img, rect)
        total_old += t_old
        total_new += t_new
        speedup = t_old / t_new if t_new > 0 else 0
        print(f'  {name:<10} {"全图" if rect is None else "裁剪":<8} '
              f'{t_old:>7.2f}s {t_new:>7.2f}s {speedup:>5.1f}x')
        # 关键词抽查
        for kw in MUST_HAVE.get(name, []):
            old_hit = any(kw in t for t, _ in texts_old)
            new_hit = any(kw in t for t, _ in texts_new)
            mark = 'OK' if old_hit and new_hit else ('!!新引擎丢失' if old_hit else '两者皆无')
            print(f'    关键词[{kw}]: 旧={old_hit} 新={new_hit} {mark}')
        # 新引擎识别文本抽样（前 8 行，人工核对用）
        sample = [t for t, _ in texts_new][:8]
        print(f'    新引擎文本: {sample}')
    print(f'\n合计: 旧 {total_old:.2f}s → 新 {total_new:.2f}s '
          f'({total_old / total_new:.1f}x)' if total_new else '')
    return 0


if __name__ == '__main__':
    sys.exit(main())
