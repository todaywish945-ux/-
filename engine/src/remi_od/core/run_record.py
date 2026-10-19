"""运行记录：判定"今天（游戏日）是否已跑过"。游戏日 = 本地时间 - 4 小时取日期。"""

import time
from datetime import datetime, timedelta
from pathlib import Path

from remi_od.core import config

STATUS_WAIT = 0
STATUS_SUCCESS = 1
STATUS_FAIL = 2
STATUS_RUNNING = 3


def game_today(refresh_hour_offset: int = 4, now: float | None = None) -> str:
    """当前游戏日（yyyyMMdd）。国服凌晨 4 点重置 = 本地时间减 4 小时取日期。"""
    current = datetime.fromtimestamp(now if now is not None else time.time())
    shifted = current - timedelta(hours=refresh_hour_offset)
    return shifted.strftime('%Y%m%d')


class RunRecord:

    def __init__(self, path: Path, refresh_hour_offset: int = 4):
        self.path: Path = path
        self.refresh_hour_offset: int = refresh_hour_offset
        self.run_status: int = STATUS_WAIT
        self.dt: str = ''
        self.uid: str = ''  # 写入记录时的游戏账号 UID（换号防串）

    def _load(self) -> None:
        data = config.load_yaml(self.path, {}) or {}
        self.run_status = int(data.get('run_status', STATUS_WAIT))
        self.dt = str(data.get('dt', '') or '')
        self.uid = str(data.get('uid', '') or '')

    def _save(self) -> None:
        now = time.time()
        config.save_yaml(self.path, {
            'run_status': self.run_status,
            'dt': game_today(self.refresh_hour_offset, now),
            'run_time': time.strftime('%m-%d %H:%M'),
            'run_time_float': now,
            'uid': self.uid,
        })

    def check_and_update_status(self) -> None:
        """跨游戏日自动重置为未运行。"""
        self._load()
        if self.dt != game_today(self.refresh_hour_offset):
            self.run_status = STATUS_WAIT

    @property
    def is_done(self) -> bool:
        return self.run_status == STATUS_SUCCESS

    def update(self, status: int) -> None:
        self.run_status = status
        self._save()
