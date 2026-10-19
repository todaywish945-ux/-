"""状态机引擎：@node 声明节点、@from_node 声明边，execute() 驱动整个指令图。

节点方法返回 RoundResult：
- round_success(status)：成功，按 (from=本节点, success=True, status) 匹配边转移
- round_retry(status, wait)：本轮失败重试（计入节点重试次数，超限降级为失败）
- round_wait(status, wait)：原地等待（不计重试，常用于点击后等画面跳转）
- round_fail(status)：失败，按 (success=False) 边走或结束整个指令

边匹配规则（与原引擎语义一致）：
1. 先找 success 标志匹配（上一轮成功/失败）且 status 完全相等的边
2. 都不匹配时走 ignore_status=True 的兜底边
3. 没有可用边 → 整个指令以上一轮结果结束
"""

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from remi_od.core.geometry import Point
from remi_od.core.log import log
from remi_od.core.round_result import OpResult, Round, RoundResult


@dataclass
class NodeSpec:

    name: str
    method: Callable
    max_retry: int = 3
    timeout_s: float | None = None
    is_start: bool = False
    screenshot: bool = True


@dataclass
class EdgeSpec:

    from_name: str
    to_name: str = ''
    success: bool = True
    status: str | None = None  # None = 匹配任意 status


def node(name: str, max_retry: int = 3, timeout_s: float | None = None,
         is_start: bool = False, screenshot: bool = True) -> Callable:
    """声明一个状态机节点。"""

    def decorator(func: Callable) -> Callable:
        func._node_spec = NodeSpec(
            name=name, method=func, max_retry=max_retry, timeout_s=timeout_s,
            is_start=is_start, screenshot=screenshot,
        )
        return func

    return decorator


def from_node(from_name: str, success: bool = True,
              status: str | None = None) -> Callable:
    """声明一条入边：上一节点为 from_name 时允许进入本节点。

    不带 status → 匹配任意 status（常见用法）；
    带 status → 要求上一节点单轮结果的 status 完全相等（分支路由）。
    """

    def decorator(func: Callable) -> Callable:
        specs = getattr(func, '_edge_specs', None)
        if specs is None:
            specs = []
            func._edge_specs = specs
        specs.append(EdgeSpec(from_name=from_name, to_name='', success=success,
                              status=status))
        return func

    return decorator


@dataclass
class _NodeState:

    spec: NodeSpec
    start_time: float = 0.0
    retry_times: int = 0
    round_count: int = 0  # 节点内总轮次（含 WAIT，防自循环节点死循环）


class Operation:

    """一条指令 = 一张节点图。子类用装饰器声明节点与边。"""

    op_name: str = '指令'

    def __init__(self, ctx):
        self.ctx = ctx
        self.shot: np.ndarray | None = None  # 本轮截图（1920x1080 BGR）
        self._nodes: dict[str, NodeSpec] = {}
        self._edges: list[EdgeSpec] = []
        self._current: _NodeState | None = None
        self._current_name: str = ''
        self._prev_name: str = ''
        self._prev_result: RoundResult | None = None
        self.node_status: dict[str, RoundResult] = {}  # save_status 节点的结果留档

    # ---- 子类钩子 ----

    def handle_init(self) -> None:
        """执行前初始化，子类按需覆盖。"""

    def handle_done(self, result: OpResult) -> None:
        """指令结束（无论成败）后的收尾，子类按需覆盖。"""

    # ---- 图构建 ----

    def _build_graph(self) -> None:
        self._nodes = {}
        self._edges = []
        for attr in dir(self):
            method = getattr(self, attr)
            spec = getattr(method, '_node_spec', None)
            if isinstance(spec, NodeSpec):
                self._nodes[spec.name] = spec
        for name, spec in self._nodes.items():
            for edge in getattr(spec.method, '_edge_specs', None) or []:
                self._edges.append(
                    EdgeSpec(from_name=edge.from_name, to_name=name,
                             success=edge.success, status=edge.status)
                )

    def _start_node(self) -> NodeSpec:
        starts = [s for s in self._nodes.values() if s.is_start]
        if len(starts) == 1:
            return starts[0]
        if not starts:
            # 无显式起点时取入度为 0 的节点
            no_in = [s for s in self._nodes.values()
                     if not any(e.to_name == s.name for e in self._edges)]
            if len(no_in) == 1:
                return no_in[0]
        raise ValueError(f'[{self.op_name}] 起点节点不唯一: {[s.name for s in starts]}')

    # ---- 执行主循环 ----

    def execute(self, op_timeout_s: float | None = None) -> OpResult:
        self._build_graph()
        self.handle_init()
        self.node_status = {}
        self.ctx.op_begin()  # 最外层操作清除 F10 残留标志；嵌套子操作不清
        op_start = time.time()
        self._enter_node(self._start_node())
        try:
            return self._execute_loop(op_start, op_timeout_s)
        finally:
            self.ctx.op_end()

    def _execute_loop(self, op_start: float, op_timeout_s: float | None) -> OpResult:
        while True:
            if self.ctx.is_stop_requested():
                return self._finish(OpResult(False, '人工结束'))
            if op_timeout_s is not None and time.time() - op_start > op_timeout_s:
                return self._finish(OpResult(False, '执行超时'))

            try:
                result = self._run_round()
            except Exception as e:
                log(self.op_name, f'节点[{self._current_name}] 异常: {e}')
                self._save_debug_shot()
                result = RoundResult(Round.RETRY, '异常')

            # 逐轮状态打到终端/日志（调试观测用；成功轮由节点结束日志覆盖）
            _round_names = {Round.RETRY: '重试', Round.SUCCESS: '成功',
                            Round.WAIT: '等待', Round.FAIL: '失败'}
            if result.result != Round.SUCCESS and result.status:
                log(self.op_name,
                    f'[{self._current_name}] 第{self._current.round_count}轮 '
                    f'{_round_names.get(result.result, result.result)} {result.status}')

            if result.result == Round.RETRY:
                assert self._current is not None
                self._current.retry_times += 1
                if self._current.retry_times <= self._current.spec.max_retry:
                    continue
                result = RoundResult(Round.FAIL, result.status or '重试超限')
                log(self.op_name, f'节点[{self._current_name}] 重试超限')
            elif result.result == Round.WAIT:
                continue
            elif result.result != Round.SUCCESS and result.result != Round.FAIL:
                continue

            next_name = self._pick_next(result)
            self._prev_name = self._current_name
            self._prev_result = result
            if next_name is None:
                return self._finish(OpResult(
                    success=result.result == Round.SUCCESS,
                    status=result.status, data=result.data,
                ))
            self._enter_node(self._nodes[next_name])

    def _finish(self, result: OpResult) -> OpResult:
        log(self.op_name, f'结束: {"成功" if result.success else "失败"} {result.status or ""}')
        try:
            self.handle_done(result)
        except Exception as e:
            log(self.op_name, f'收尾异常: {e}')
        return result

    def _enter_node(self, spec: NodeSpec) -> None:
        self._current = _NodeState(spec=spec, start_time=time.time())
        self._current_name = spec.name
        self.ctx.report_node(self.op_name, spec.name)

    def _reshoot(self, delay: float) -> None:
        """回合内动作后等待并重拍（提速：省一轮"干等再检查"的截图周期）。"""
        time.sleep(delay)
        shot = self.ctx.controller.screenshot()
        if shot is not None:
            self.shot = shot

    def _run_round(self) -> RoundResult:
        assert self._current is not None
        spec = self._current.spec
        self._current.round_count += 1
        # 硬上限：含 WAIT 的总轮次（WAIT 不消耗重试次数，自循环节点可能死循环）
        round_cap = max(30, spec.max_retry * 4)
        if self._current.round_count > round_cap:
            return RoundResult(Round.FAIL, '节点轮次超限')
        if spec.timeout_s is not None and time.time() - self._current.start_time > spec.timeout_s:
            return RoundResult(Round.FAIL, '节点超时')
        if spec.screenshot:
            shot = self.ctx.controller.screenshot()
            if shot is not None:
                self.shot = shot
        result = spec.method(self)
        if not isinstance(result, RoundResult):
            return RoundResult(Round.FAIL, '节点返回值类型错误')
        self.ctx.report_retry(self._current.retry_times)
        return result

    def _pick_next(self, result: RoundResult) -> str | None:
        """选边：先 status 精确匹配的边，再任意 status 的边；没有可用边 → 结束。"""
        is_success = result.result == Round.SUCCESS
        exact: EdgeSpec | None = None
        general: EdgeSpec | None = None
        for edge in self._edges:
            if edge.from_name != self._current_name:
                continue
            if edge.success != is_success:
                continue
            if edge.status is None:
                if general is None:
                    general = edge
            elif edge.status == result.status and exact is None:
                exact = edge
        chosen = exact or general
        return chosen.to_name if chosen else None

    def _save_debug_shot(self) -> None:
        try:
            if self.shot is not None:
                self.ctx.save_debug_image(f'{self._current_name}', self.shot)
        except Exception:
            pass

    # ---- 轮次结果构造 ----

    def round_success(self, status: str | None = None, data: Any = None,
                      wait: float = 0.0) -> RoundResult:
        if wait > 0:
            time.sleep(wait)
        return RoundResult(Round.SUCCESS, status, data)

    def round_retry(self, status: str | None = None, wait: float = 1.0) -> RoundResult:
        if wait > 0:
            time.sleep(wait)
        return RoundResult(Round.RETRY, status)

    def round_wait(self, status: str | None = None, wait: float = 1.0) -> RoundResult:
        if wait > 0:
            time.sleep(wait)
        return RoundResult(Round.WAIT, status)

    def round_fail(self, status: str | None = None, wait: float = 0.0) -> RoundResult:
        if wait > 0:
            time.sleep(wait)
        return RoundResult(Round.FAIL, status)

    # ---- 识别辅助（节点方法内使用） ----

    @property
    def previous_node(self) -> str:
        return self._prev_name

    @property
    def previous_status(self) -> str | None:
        return self._prev_result.status if self._prev_result else None

    def find_area(self, screen_name: str, area_name: str) -> RoundResult | None:
        """在截图里找画面区域，返回命中结果（含 data=MatchResult）或 None（未命中/区域无定义）。"""
        if self.shot is None:
            return None
        return self.ctx.find_area(self.shot, screen_name, area_name)

    def round_by_find_area(self, screen_name: str, area_name: str,
                           wait: float = 0.0) -> RoundResult:
        result = self.find_area(screen_name, area_name)
        if result is not None:
            return self.round_success(result.status, result.data)
        return self.round_retry(f'未找到 {screen_name}.{area_name}')

    def round_by_find_and_click(self, screen_name: str, area_name: str,
                                wait: float = 0.5, pre_delay: float = 0.0) -> RoundResult:
        """找区域并点击其中心；命中→成功，未命中→重试。"""
        result = self.find_area(screen_name, area_name)
        if result is not None and result.data is not None:
            if pre_delay > 0:
                time.sleep(pre_delay)
            area = self.ctx.get_area(screen_name, area_name)
            self.ctx.controller.click(result.data.center, alt=bool(area and area.alt))
            return self.round_success(result.status, wait=wait)
        return self.round_retry(f'未找到 {screen_name}.{area_name}')

    def round_by_click_area(self, screen_name: str, area_name: str,
                            wait: float = 0.5) -> RoundResult:
        """不识别直接点区域中心（用于固定 UI 按钮）。"""
        area = self.ctx.get_area(screen_name, area_name)
        if area is None:
            return self.round_fail(f'区域未建档 {screen_name}.{area_name}')
        self.ctx.controller.click(area.center, alt=area.alt)
        return self.round_success(wait=wait)

    # ---- OCR 辅助 ----

    def find_text(self, text: str, screen_name: str, area_name: str,
                  lcs: float = 0.5):
        """在指定画面的区域内 OCR 找文字。返回 OcrItem 或 None。"""
        area = self.ctx.get_area(screen_name, area_name)
        if area is None:
            raise ValueError(f'区域未建档: {screen_name}.{area_name}')
        return self.ctx.ocr.find_text(self.shot, text, area.rect, lcs)

    def round_by_ocr_and_click(self, text: str, screen_name: str, area_name: str,
                               lcs: float = 0.5, wait: float = 0.5,
                               wait_not_found: float = 1.0) -> RoundResult:
        """区域内 OCR 找文字并点击其中心；命中→成功，未命中→重试。"""
        area = self.ctx.get_area(screen_name, area_name)
        if area is None:
            return self.round_fail(f'区域未建档 {screen_name}.{area_name}')
        item = self.ctx.ocr.find_text(self.shot, text, area.rect, lcs)
        if item is not None:
            self.ctx.controller.click(item.center, alt=area.alt)
            return self.round_success(item.text, wait=wait)
        return self.round_retry(f'未找到 {text}', wait=wait_not_found)

    def round_by_ocr_find(self, text: str, screen_name: str, area_name: str,
                          lcs: float = 0.5) -> RoundResult:
        """区域内 OCR 找文字，只判断存在。"""
        item = self.find_text(text, screen_name, area_name, lcs)
        if item is not None:
            return self.round_success(item.text)
        return self.round_retry(f'未找到 {text}')
