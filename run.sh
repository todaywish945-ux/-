#!/usr/bin/env bash
# 小蕾米AI助理 Linux 启动脚本：./run.sh
# 首次运行会自动创建虚拟环境并安装依赖（需要 python3-venv）
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi
. .venv/bin/activate
python -m pip install -q -r requirements.txt
exec python pet.py
