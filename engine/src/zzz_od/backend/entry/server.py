"""兼容入口：桌宠按 `python -m zzz_od.backend.entry.server --host --port` 启动引擎，
此 shim 让小蕾米引擎零改动接入桌宠（桌宠以 src\\zzz_od 目录存在性判断"已安装"）。

路径无关：直接以脚本方式运行时自动把 src 加入 sys.path。
"""

import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[3])
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from remi_od.server.main import main

if __name__ == '__main__':
    main()
