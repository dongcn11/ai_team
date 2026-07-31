"""
Workflow Executor
=================
Chạy trên HOST (nơi có `claude` / `opencode` CLI), không trong Docker.

Cách hoạt động: mỗi lần `advance()` được gọi, executor chạy hết những node đã
sẵn sàng, rồi **dừng lại** khi gặp `manual_gate` chưa được duyệt. State lưu ra
DB qua caller → người bấm duyệt → gọi `advance()` lại, chạy tiếp từ đúng chỗ đó.
Không có vòng lặp chờ, không có process treo qua đêm.

Node `runtime="claude"` đi qua 2 lớp chắn trước khi được gọi:

  1. `assert_claude_allowed()` — validate lại invariant trên graph (DB có thể bị
     sửa tay sau khi save) + đòi bằng chứng có người bấm và cú bấm còn tươi.
  2. `quota.claude_slot()` — tuần tự tuyệt đối + trần 5h/ngày + khoảng nghỉ.

Node `runtime="opencode"` không qua 2 lớp này — cứ để listener kích thoải mái.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from ai_team import quota
from ai_team.runner import _resolve_cmd, run_opencode, write_prompt_file
from ai_team.workflow.graph import (
    DONE,
    FAILED,
    PENDING,
    RUNNING,
    SKIPPED,
    WAITING,
    Graph,
    Node,
    descendants,
    human_checkpoints_upstream_of,
    initial_state,
    ready_nodes,
    unguarded_claude_nodes,
)

# Cú bấm duyệt cũ hơn mức này thì coi như không còn ai ngồi đó nữa.
GATE_MAX_AGE_S = int(os.getenv("CLAUDE_GATE_MAX_AGE_S", "3600"))
# Số node chạy song song. Node claude vẫn tuần tự do semaphore trong quota.
MAX_PARALLEL = int(os.getenv("WORKFLOW_MAX_PARALLEL", "2"))


class ClaudeGateError(RuntimeError):
    """Node Claude bị chặn: thiếu gate, gate chưa duyệt, hoặc duyệt đã cũ."""


class HandlerMissing(RuntimeError):
    """Node khai `handler` không có trong registry."""


# ── Handler registry (cho runtime="code" và type="action") ────────────────────

HandlerFn = Callable[[Node, "RunContext"], "str | Awaitable[str]"]
_HANDLERS: dict[str, HandlerFn] = {}


def handler(name: str):
    """Đăng ký handler cho node `code` / `action`.

        @handler("classify_mention")
        def classify(node, ctx) -> str: ...
    """
    def deco(fn: HandlerFn) -> HandlerFn:
        _HANDLERS[name] = fn
        return fn
    return deco


def registered_handlers() -> list[str]:
    return sorted(_HANDLERS)


# ── Run context ───────────────────────────────────────────────────────────────

@dataclass
class RunContext:
    work_dir: Path
    trigger_type: str = "manual_trigger"
    started_at: float = field(default_factory=time.time)
    payload: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    # gate node_id → epoch lúc người bấm duyệt
    approvals: dict[str, float] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)

    def say(self, msg: str) -> None:
        self.log.append(msg)
        print(f"  [wf] {msg}")


def render(text: str, ctx: RunContext) -> str:
    """Thay `{{outputs.NODE_ID}}` và `{{payload.KEY}}` trong prompt."""
    for nid, val in ctx.outputs.items():
        text = text.replace(f"{{{{outputs.{nid}}}}}", val)
    for key, val in ctx.payload.items():
        text = text.replace(f"{{{{payload.{key}}}}}", str(val))
    return text


# ── Claude guard ──────────────────────────────────────────────────────────────

def human_signal_age(graph: Graph, node: Node, ctx: RunContext) -> float | None:
    """Giây kể từ cú bấm gần nhất cho phép node này chạy. None = không có cú bấm nào.

    Bằng chứng chỉ đến từ `ctx.approvals` (đọc từ bảng workflow_approvals), KHÔNG
    từ `ctx.trigger_type` — trigger_type là string client gửi lên, listener khai
    "manual_trigger" là lách được ngay. Muốn Claude chạy thì phải có row approval.
    """
    stamps = [ctx.approvals[c] for c in human_checkpoints_upstream_of(graph, node.id)
              if c in ctx.approvals]
    if not stamps:
        return None
    return time.time() - max(stamps)


def assert_claude_allowed(graph: Graph, node: Node, ctx: RunContext) -> None:
    """Chặn node Claude nếu không chứng minh được là có người bấm."""
    unguarded = unguarded_claude_nodes(graph)
    if node.id in unguarded:
        raise ClaudeGateError(
            f"Node '{node.id}' là Claude nhưng auto-trigger kích được trực tiếp "
            "(không có manual_gate chắn trước). Không chạy. "
            'Chèn manual_gate, hoặc đổi node sang runtime="opencode".'
        )

    age = human_signal_age(graph, node, ctx)
    if age is None:
        raise ClaudeGateError(
            f"Node '{node.id}': không có cú bấm duyệt nào phía trên "
            f"(checkpoint: {human_checkpoints_upstream_of(graph, node.id) or 'không có'}). "
            "Bấm duyệt ở gate rồi chạy lại."
        )
    if age > GATE_MAX_AGE_S:
        raise ClaudeGateError(
            f"Node '{node.id}': cú bấm duyệt đã {int(age / 60)} phút trước "
            f"(trần {GATE_MAX_AGE_S // 60} phút) — coi như không còn ai ngồi đó. "
            "Bấm duyệt lại."
        )


# ── Node runners ──────────────────────────────────────────────────────────────

async def _run_handler(node: Node, ctx: RunContext) -> str:
    fn = _HANDLERS.get(node.handler)
    if fn is None:
        raise HandlerMissing(
            f"Node '{node.id}': handler '{node.handler}' chưa đăng ký. "
            f"Có sẵn: {registered_handlers() or '(chưa có handler nào)'}"
        )
    res = fn(node, ctx)
    if inspect.isawaitable(res):
        res = await res
    return "" if res is None else str(res)


async def _run_claude_cli(node: Node, ctx: RunContext) -> str:
    """Gọi Claude Code headless. KHÔNG có --dangerously-skip-permissions và
    KHÔNG có Bash trong allowlist — node chỉ được đọc/ghi file. Cần chạy shell
    thì tách ra một node `action` riêng để bạn thấy rõ nó làm gì."""
    work_dir = ctx.work_dir
    work_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = write_prompt_file(render(node.prompt, ctx), f"wf_{node.id}")

    cmd = _resolve_cmd("claude") + [
        "-p", f"Read the instructions at {prompt_file} and follow them exactly.",
        "--allowedTools", "Read,Write,Edit",
        "--output-format", "text",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(work_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=node.timeout_s)
    finally:
        prompt_file.unlink(missing_ok=True)

    out = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(err[:500] or out[:200] or f"claude exit {proc.returncode}")
    return out


async def run_node(graph: Graph, node: Node, ctx: RunContext) -> str:
    """Chạy 1 node, trả output. Raise nếu fail."""
    if node.is_trigger:
        return ""                          # trigger đã nổ rồi, không phải việc để chạy

    if node.type == "action":
        return await _run_handler(node, ctx)

    if node.type != "task":
        return ""

    if node.runtime == "code":
        return await _run_handler(node, ctx)

    if node.runtime == "opencode":
        return await run_opencode(
            node.model, render(node.prompt, ctx), ctx.work_dir, timeout=node.timeout_s
        )

    if node.runtime == "claude":
        assert_claude_allowed(graph, node, ctx)
        async with quota.claude_slot():
            ctx.say(f"'{node.id}' → Claude (đã qua gate, đã trừ quota)")
            return await _run_claude_cli(node, ctx)

    raise RuntimeError(f"Node '{node.id}': runtime '{node.runtime}' không chạy được")


# ── Advance ───────────────────────────────────────────────────────────────────

@dataclass
class AdvanceResult:
    status: str                                  # waiting / done / failed
    state: dict[str, str]
    outputs: dict[str, str]
    waiting_on: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)


def _overall_status(state: dict[str, str]) -> str:
    values = set(state.values())
    if WAITING in values:
        return WAITING            # còn chỗ chờ người → ưu tiên báo để bấm tiếp
    if FAILED in values:
        return FAILED
    if PENDING in values or RUNNING in values:
        return FAILED             # bí mà không ai chờ → có gì đó sai
    return DONE


async def advance(
    graph: Graph,
    state: dict[str, str] | None = None,
    ctx: RunContext | None = None,
) -> AdvanceResult:
    """Chạy tới khi hết node sẵn sàng. Gặp gate chưa duyệt → đánh dấu `waiting`
    và dừng nhánh đó. Gọi lại sau khi duyệt để chạy tiếp."""
    state = dict(state) if state else initial_state(graph)
    ctx = ctx or RunContext(work_dir=Path.cwd())
    errors: dict[str, str] = {}
    sem = asyncio.Semaphore(max(1, MAX_PARALLEL))

    def fail(node_id: str, msg: str) -> None:
        state[node_id] = FAILED
        errors[node_id] = msg
        ctx.say(f"❌ '{node_id}': {msg}")
        for d in descendants(graph, node_id):
            if state.get(d) == PENDING:
                state[d] = SKIPPED

    async def guarded(node: Node) -> None:
        async with sem:
            try:
                out = await run_node(graph, node, ctx)
                ctx.outputs[node.id] = out
                state[node.id] = DONE
            except Exception as e:
                fail(node.id, str(e) or type(e).__name__)

    while True:
        ready = ready_nodes(graph, state)
        if not ready:
            break

        batch: list[Node] = []
        for node in ready:
            if node.is_gate:
                if node.id in ctx.approvals:
                    state[node.id] = DONE
                    ctx.say(f"✅ gate '{node.id}' đã duyệt — chạy tiếp")
                else:
                    state[node.id] = WAITING
                    ctx.say(f"⏸ gate '{node.id}' — chờ bạn bấm duyệt")
                continue
            if node.is_trigger:
                state[node.id] = DONE
                continue
            batch.append(node)

        if not batch:
            continue          # vòng này chỉ xử lý gate/trigger, thử lại xem có mở ra node mới

        for node in batch:
            state[node.id] = RUNNING
        await asyncio.gather(*(guarded(n) for n in batch))

    return AdvanceResult(
        status=_overall_status(state),
        state=state,
        outputs=dict(ctx.outputs),
        waiting_on=sorted(nid for nid, st in state.items() if st == WAITING),
        errors=errors,
        log=list(ctx.log),
    )
