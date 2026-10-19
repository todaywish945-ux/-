"""应用基类与注册表：日常功能都做成 App（带运行记录与游戏日重置）。"""

from dataclasses import dataclass
from typing import Callable

from remi_od.core.config import EnginePaths
from remi_od.core.log import log
from remi_od.core.operation import Operation
from remi_od.core.round_result import OpResult, Round
from remi_od.core.run_record import STATUS_FAIL, STATUS_RUNNING, STATUS_SUCCESS, RunRecord


@dataclass
class AppInfo:

    app_id: str
    app_name: str
    description: str = ''
    standalone: bool = True  # 是否出现在独立应用列表
    factory: Callable = None  # ctx -> App 实例


class App(Operation):

    """带运行记录的应用：跑完记录成败，跨游戏日自动重置。"""

    def __init__(self, ctx, app_id: str, app_name: str, description: str = ''):
        Operation.__init__(self, ctx)
        self.app_id: str = app_id
        self.app_name: str = app_name
        self.description: str = description
        self.run_record: RunRecord = RunRecord(
            ctx.paths.run_record_dir / f'{app_id}.yml',
            refresh_hour_offset=_refresh_offset(ctx),
        )

    @property
    def op_name(self) -> str:  # 覆盖类属性为实例属性
        return self.app_name

    def handle_init(self) -> None:
        self.run_record.check_and_update_status()
        self.run_record.uid = getattr(self.ctx, 'uid', '')  # 账号标记防换号串记录
        self.run_record.update(STATUS_RUNNING)
        self.ctx.enter_scope(self.app_id)

    def handle_done(self, result: OpResult) -> None:
        self.ctx.exit_scope()
        self.run_record.update(STATUS_SUCCESS if result.success else STATUS_FAIL)


class OneDragonApp(App):

    """一条龙编排应用：按 _group.yml 顺序执行启用的应用，跳过当日已成功的。

    实际编排在 apps/one_dragon.py 的 OneDragonOp；本类只做运行记录语义
    （一条龙本身不写记录，由各业务应用各自记录）。
    """

    def handle_init(self) -> None:
        self.ctx.enter_scope('')

    def handle_done(self, result: OpResult) -> None:
        self.ctx.exit_scope()


def _refresh_offset(ctx) -> int:
    from remi_od.core import config as config_mod

    account = config_mod.game_account(ctx.paths)
    try:
        return int(account.get('refresh_hour_offset', 4))
    except (TypeError, ValueError):
        return 4


def build_run_record(ctx, app_id: str) -> RunRecord:
    return RunRecord(ctx.paths.run_record_dir / f'{app_id}.yml',
                     refresh_hour_offset=_refresh_offset(ctx))


def is_app_done_today(ctx, app_id: str) -> bool:
    """某应用今天（游戏日）是否已成功跑过。

    记录带 UID 时比对当前账号：换号（如借号测试）后记录不串号。
    """
    record = build_run_record(ctx, app_id)
    record.check_and_update_status()
    if record.is_done and record.uid and getattr(ctx, 'uid', '') \
            and record.uid != ctx.uid:
        return False
    return record.is_done
