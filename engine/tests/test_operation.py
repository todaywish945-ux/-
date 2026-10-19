"""状态机引擎单测：重试/WAIT/分支边/超时/停止/异常。"""

import time
from types import SimpleNamespace

from remi_od.core.operation import Operation, from_node, node
from remi_od.core.round_result import Round


class FakeCtx:

    def __init__(self):
        self.stop_flag = False
        self.nodes: list[str] = []
        self.controller = SimpleNamespace(screenshot=lambda: None)

    def is_stop_requested(self) -> bool:
        return self.stop_flag

    def op_begin(self) -> None:
        pass

    def op_end(self) -> None:
        pass

    def report_node(self, op_name: str, node_name: str) -> None:
        self.nodes.append(node_name)

    def report_retry(self, retry_times: int) -> None:
        pass

    def save_debug_image(self, tag, image):
        pass


def test_retry_then_success():
    class Op(Operation):
        calls = 0

        @node('A', is_start=True, max_retry=5)
        def a(self) -> Round:
            Op.calls += 1
            if Op.calls < 3:
                return self.round_retry('还没好')
            return self.round_success('好了')

        @from_node('A')
        @node('B')
        def b(self) -> Round:
            return self.round_success('B完成')

    ctx = FakeCtx()
    result = Op(ctx).execute()
    assert result.success and result.status == 'B完成'
    assert Op.calls == 3


def test_retry_exceeded_fails():
    class Op(Operation):
        @node('A', is_start=True, max_retry=2)
        def a(self) -> Round:
            return self.round_retry('一直不行')

    result = Op(FakeCtx()).execute()
    assert not result.success
    assert result.status == '一直不行'


def test_wait_stays_on_node():
    class Op(Operation):
        waits = 0

        @node('A', is_start=True, max_retry=1)
        def a(self) -> Round:
            Op.waits += 1
            if Op.waits < 3:
                return self.round_wait('等一下', wait=0.01)
            return self.round_success('终于好了')

        @from_node('A')
        @node('B')
        def b(self) -> Round:
            return self.round_success('B')

    result = Op(FakeCtx()).execute()
    assert result.success and result.status == 'B'
    assert Op.waits == 3  # WAIT 不计重试，max_retry=1 也走满 3 轮


def test_status_edge_branching():
    class Op(Operation):
        @node('A', is_start=True)
        def a(self) -> Round:
            return self.round_success('分支二')

        @from_node('A', status='分支一')
        @node('B1')
        def b1(self) -> Round:
            return self.round_success('走了B1')

        @from_node('A', status='分支二')
        @node('B2')
        def b2(self) -> Round:
            return self.round_success('走了B2')

    result = Op(FakeCtx()).execute()
    assert result.status == '走了B2'


def test_fail_edge():
    class Op(Operation):
        @node('A', is_start=True)
        def a(self) -> Round:
            return self.round_fail('出错了')

        @from_node('A', success=False)
        @node('恢复')
        def recover(self) -> Round:
            return self.round_success('已恢复')

    result = Op(FakeCtx()).execute()
    assert result.success and result.status == '已恢复'


def test_exact_status_preferred_over_general():
    """status 精确边优先于任意 status 边。"""

    class Op(Operation):
        @node('A', is_start=True)
        def a(self) -> Round:
            return self.round_success('预期状态')

        @from_node('A', status='预期状态')
        @node('精确分支')
        def exact(self) -> Round:
            return self.round_success('精确')

        @from_node('A')
        @node('任意分支')
        def general(self) -> Round:
            return self.round_success('任意')

    result = Op(FakeCtx()).execute()
    assert result.status == '精确'


def test_general_edge_matches_any_status():
    """不带 status 的边匹配任意 status（常见用法）。"""

    class Op(Operation):
        @node('A', is_start=True)
        def a(self) -> Round:
            return self.round_success('意料之外的状态')

        @from_node('A')
        @node('任意分支')
        def general(self) -> Round:
            return self.round_success('任意')

    result = Op(FakeCtx()).execute()
    assert result.status == '任意'


def test_no_edge_ends_op():
    class Op(Operation):
        @node('A', is_start=True)
        def a(self) -> Round:
            return self.round_success('终态')

    result = Op(FakeCtx()).execute()
    assert result.success and result.status == '终态'


def test_node_timeout():
    """节点超时按轮次间检查：WAIT 循环累计超过 timeout_s 后下一轮触发。"""

    class Op(Operation):
        @node('A', is_start=True, timeout_s=0.3, max_retry=999)
        def a(self) -> Round:
            return self.round_wait('慢慢来', wait=0.1)

    result = Op(FakeCtx()).execute()
    assert not result.success
    assert result.status == '节点超时'


def test_op_timeout():
    class Op(Operation):
        @node('A', is_start=True, max_retry=999)
        def a(self) -> Round:
            return self.round_retry(wait=0.1)

    result = Op(FakeCtx()).execute(op_timeout_s=0.5)
    assert not result.success
    assert result.status == '执行超时'


def test_stop_flag():
    ctx = FakeCtx()

    class Op(Operation):
        @node('A', is_start=True, max_retry=999)
        def a(self) -> Round:
            ctx.stop_flag = True
            return self.round_retry(wait=0.05)

    result = Op(ctx).execute()
    assert not result.success
    assert result.status == '人工结束'


def test_exception_becomes_retry():
    class Op(Operation):
        calls = 0

        @node('A', is_start=True, max_retry=5)
        def a(self) -> Round:
            Op.calls += 1
            if Op.calls == 1:
                raise RuntimeError('炸了')
            return self.round_success('恢复成功')

        @from_node('A')
        @node('B')
        def b(self) -> Round:
            return self.round_success('B')

    result = Op(FakeCtx()).execute()
    assert result.success and result.status == 'B'
    assert Op.calls == 2


def test_start_node_inference():
    """无显式起点时取入度 0 的节点。"""

    class Op(Operation):
        @node('A')
        def a(self) -> Round:
            return self.round_success('A')

        @from_node('A')
        @node('B')
        def b(self) -> Round:
            return self.round_success('B')

    result = Op(FakeCtx()).execute()
    assert result.status == 'B'


def test_wait_loop_terminated_by_round_cap():
    """回归：自循环节点（round_wait 不消耗重试）必须被轮次硬上限终止，不得死循环。"""

    class Op(Operation):
        rounds = 0

        @node('A', is_start=True, max_retry=3)
        def a(self) -> Round:
            Op.rounds += 1
            return self.round_wait('永远等待', wait=0)

    result = Op(FakeCtx()).execute(op_timeout_s=10)
    assert not result.success
    assert result.status == '节点轮次超限'
    assert Op.rounds <= 35  # max(30, 3*4)+少量余量
