"""调试 CLI：截图建档工具集。

用法（在引擎根目录）：
  python -m remi_od.tools.capture [--out 路径] [--title 窗口标题关键字]
  python -m remi_od.tools.mark 图像.png x1 y1 x2 y2 [--label 标注] [--out 输出.png]
  python -m remi_od.tools.match 图像.png <子目录/模板id> [阈值]
  python -m remi_od.tools.make_template 图像.png x1 y1 x2 y2 <子目录/模板id>
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

from remi_od.core.geometry import STANDARD_HEIGHT, STANDARD_WIDTH


def _read_image(path: str) -> np.ndarray:
    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise SystemExit(f'无法读取图像: {path}')
    return image


def _engine_root() -> Path:
    return Path(__file__).resolve().parents[3]


def cmd_capture(args) -> None:
    from remi_od.control import window as win_ctl
    from remi_od.control.screenshot import capture_window

    if args.title:
        hwnd = win_ctl.find_window_by_keyword(args.title)
        if not hwnd:
            raise SystemExit(f'按关键字未找到窗口: {args.title}')
    else:
        hwnd = win_ctl.find_window(win_ctl.GAME_WINDOW_TITLE)
        if not hwnd:
            raise SystemExit('未找到游戏窗口（标题: 绝区零）')

    image = capture_window(hwnd, STANDARD_WIDTH, STANDARD_HEIGHT)
    if image is None:
        raise SystemExit('截图失败（窗口可能最小化或无渲染内容）')
    out = Path(args.out) if args.out else Path('debug') / 'capture.png'
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode('.png', image)[1].tofile(str(out))
    size = image.shape
    print(f'已保存 {out} ({size[1]}x{size[0]})')


def cmd_mark(args) -> None:
    image = _read_image(args.image)
    x1, y1, x2, y2 = args.rect
    cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 255), 2)
    if args.label:
        cv2.putText(image, args.label, (x1, max(15, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    out = Path(args.out) if args.out else Path(args.image).with_name(
        Path(args.image).stem + '_marked.png')
    cv2.imencode('.png', image)[1].tofile(str(out))
    print(f'已保存 {out}')
    print(f'YAML 片段: rect: [{x1}, {y1}, {x2}, {y2}]')


def cmd_match(args) -> None:
    from remi_od.vision.template import TemplateStore, match_template

    image = _read_image(args.image)
    store = TemplateStore(_engine_root() / 'assets' / 'template')
    pair = store.get(args.template)
    if pair is None:
        raise SystemExit(f'模板不存在: {args.template}（应位于 assets/template/<子目录>/<id>/raw.png）')
    template, mask = pair
    hits = match_template(image, template, args.threshold, mask)
    if not hits:
        print('未命中')
        return
    best = hits[0]
    print(f'命中 {len(hits)} 处，最佳 score={best.score:.4f} center=({best.center.x},{best.center.y})')


def cmd_make_template(args) -> None:
    image = _read_image(args.image)
    x1, y1, x2, y2 = args.rect
    crop = image[y1:y2, x1:x2]
    folder = _engine_root() / 'assets' / 'template' / args.template_id
    folder.mkdir(parents=True, exist_ok=True)
    cv2.imencode('.png', crop)[1].tofile(str(folder / 'raw.png'))
    h, w = crop.shape[:2]
    print(f'已保存模板 {folder / "raw.png"} ({w}x{h})')
    print('YAML 片段（贴入对应画面的 area_list）:')
    print(f'  - area_name: <区域名>')
    print(f'    rect: [{x1}, {y1}, {x2}, {y2}]')
    print(f'    id_mark: false')
    print(f'    template: {args.template_id}')


def main() -> None:
    parser = argparse.ArgumentParser(description='小蕾米引擎调试工具')
    sub = parser.add_subparsers(dest='command', required=True)

    p_capture = sub.add_parser('capture', help='截取游戏窗口')
    p_capture.add_argument('--out', default='')
    p_capture.add_argument('--title', default='', help='窗口标题关键字（默认按游戏窗口精确标题）')
    p_capture.set_defaults(func=cmd_capture)

    p_mark = sub.add_parser('mark', help='在图上标注矩形，输出 YAML rect 片段')
    p_mark.add_argument('image')
    p_mark.add_argument('rect', nargs=4, type=int, metavar=('X1', 'Y1', 'X2', 'Y2'))
    p_mark.add_argument('--label', default='')
    p_mark.add_argument('--out', default='')
    p_mark.set_defaults(func=cmd_mark)

    p_match = sub.add_parser('match', help='对图像试配模板')
    p_match.add_argument('image')
    p_match.add_argument('template')
    p_match.add_argument('threshold', nargs='?', type=float, default=0.7)
    p_match.set_defaults(func=cmd_match)

    p_tpl = sub.add_parser('make_template', help='裁剪图像生成模板 + 输出 YAML 片段')
    p_tpl.add_argument('image')
    p_tpl.add_argument('rect', nargs=4, type=int, metavar=('X1', 'Y1', 'X2', 'Y2'))
    p_tpl.add_argument('template_id', help='模板ID，格式 <子目录>/<名字>')
    p_tpl.set_defaults(func=cmd_make_template)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    main()
