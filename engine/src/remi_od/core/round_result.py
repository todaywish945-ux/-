"""状态机单轮结果与整个指令的最终结果。"""

from dataclasses import dataclass
from typing import Any


class Round:

    """节点单轮结果的四种去向。"""

    RETRY = 0   # 本轮失败，重试当前节点（计入重试次数）
    SUCCESS = 1  # 本轮成功，按边转移
    WAIT = 2    # 等待，不计数不换节点（如点击后等画面跳转）
    FAIL = -1   # 失败，按失败边走或结束整个指令


@dataclass
class RoundResult:

    result: int
    status: str | None = None
    data: Any = None

    @property
    def is_success(self) -> bool:
        return self.result == Round.SUCCESS

    @property
    def is_fail(self) -> bool:
        return self.result == Round.FAIL


@dataclass
class OpResult:

    success: bool
    status: str | None = None
    data: Any = None
