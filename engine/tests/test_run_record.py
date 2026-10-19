"""运行记录单测：游戏日（本地时间-4小时）重置语义。"""

from datetime import datetime
from pathlib import Path

from remi_od.core.run_record import (
    STATUS_FAIL,
    STATUS_SUCCESS,
    RunRecord,
    game_today,
)


def test_game_today_boundary():
    # 03:59 属于前一游戏日（4 点重置）；04:00 属于新游戏日
    early = datetime(2026, 9, 22, 3, 59).timestamp()
    late = datetime(2026, 9, 22, 4, 0).timestamp()
    assert game_today(4, early) == '20260921'
    assert game_today(4, late) == '20260922'


def test_record_reset_across_game_day(tmp_path: Path):
    path = tmp_path / 'app.yml'
    record = RunRecord(path, refresh_hour_offset=4)
    record.update(STATUS_SUCCESS)
    assert record.is_done

    # 手写一个昨天游戏日的记录
    from remi_od.core import config as config_mod

    config_mod.save_yaml(path, {
        'run_status': STATUS_SUCCESS, 'dt': '20200101',
        'run_time': '', 'run_time_float': 0,
    })
    stale = RunRecord(path, refresh_hour_offset=4)
    stale.check_and_update_status()
    assert not stale.is_done  # 跨日自动重置


def test_record_fail_not_done(tmp_path: Path):
    record = RunRecord(tmp_path / 'app.yml')
    record.update(STATUS_FAIL)
    record.check_and_update_status()
    assert not record.is_done
