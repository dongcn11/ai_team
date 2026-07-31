"""
Workflow Graph — model + validator
==================================
Thuần logic, không DB, không I/O. Dùng được ở cả 2 nơi:

  * API (`dashboard/api/routers/workflows.py`) — validate lúc save, từ chối lưu
    workflow vi phạm và trả về đúng node nào sai để canvas tô đỏ.
  * Executor (`ai_team/workflow/executor.py`) — validate lại lúc sắp chạy node
    (defense in depth: DB có thể bị sửa tay sau khi save).

Invariant quan trọng nhất: `unguarded_claude_nodes()` — xem docstring package.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

# ── Vocabulary ────────────────────────────────────────────────────────────────

# Trigger tự động: hệ thống tự kích, không có người ngồi đó.
AUTO_TRIGGERS = {"slack_listener", "cron", "webhook"}
# Trigger do người bấm → bản thân nó đã là bằng chứng có người.
MANUAL_TRIGGERS = {"manual_trigger"}
TRIGGER_TYPES = AUTO_TRIGGERS | MANUAL_TRIGGERS

NODE_TYPES = TRIGGER_TYPES | {"task", "manual_gate", "action"}

RUNTIMES = {"code", "opencode", "claude"}
# Runtime bắt buộc có manual_gate chắn trước nếu đứng sau auto-trigger.
GATED_RUNTIMES = {"claude"}

# Node mà một cú bấm của người tạo ra bằng chứng "có người ngồi đây".
# Bằng chứng nằm ở bảng approval (DB), KHÔNG suy ra từ trigger_type mà client
# gửi lên — nếu không, listener chỉ cần khai "manual_trigger" là lách được gate.
HUMAN_CHECKPOINTS = MANUAL_TRIGGERS | {"manual_gate"}

# Trạng thái node trong một lần chạy.
PENDING, RUNNING, DONE, FAILED, WAITING, SKIPPED = (
    "pending", "running", "done", "failed", "waiting", "skipped",
)
TERMINAL_STATUSES = {DONE, FAILED, SKIPPED}


class GraphError(ValueError):
    """Raw dict không dựng nổi thành Graph (sai kiểu, thiếu id)."""


@dataclass(frozen=True)
class Node:
    id: str
    type: str
    label: str = ""
    runtime: str = ""          # chỉ với type="task"
    model: str = ""            # chỉ với runtime="opencode"
    prompt: str = ""           # task
    handler: str = ""          # code / action → tên hàm trong registry
    outward: bool = False      # action có tác động ra ngoài (push PR, gửi Slack)
    timeout_s: int = 600
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def is_trigger(self) -> bool:
        return self.type in TRIGGER_TYPES

    @property
    def is_gate(self) -> bool:
        return self.type == "manual_gate"


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    label: str = ""


@dataclass
class Graph:
    name: str
    nodes: list[Node]
    edges: list[Edge]

    def __post_init__(self):
        self._by_id: dict[str, Node] = {}
        for n in self.nodes:
            self._by_id.setdefault(n.id, n)   # id trùng → validate() sẽ báo
        self._out: dict[str, list[str]] = {n.id: [] for n in self.nodes}
        self._in: dict[str, list[str]] = {n.id: [] for n in self.nodes}
        for e in self.edges:
            if e.src in self._out:
                self._out[e.src].append(e.dst)
            if e.dst in self._in:
                self._in[e.dst].append(e.src)

    def get(self, node_id: str) -> Node | None:
        return self._by_id.get(node_id)

    def successors(self, node_id: str) -> list[str]:
        return list(self._out.get(node_id, []))

    def predecessors(self, node_id: str) -> list[str]:
        return list(self._in.get(node_id, []))

    def triggers(self, types: Iterable[str] | None = None) -> list[Node]:
        allowed = set(types) if types is not None else TRIGGER_TYPES
        return [n for n in self.nodes if n.type in allowed]

    def to_dict(self) -> dict:
        """Round-trip được với `parse()`. Bỏ field rỗng cho JSON gọn."""
        def node_dict(n: Node) -> dict:
            d = {"id": n.id, "type": n.type}
            for key in ("label", "runtime", "model", "prompt", "handler"):
                if getattr(n, key):
                    d[key] = getattr(n, key)
            if n.outward:
                d["outward"] = True
            if n.timeout_s != 600:
                d["timeout_s"] = n.timeout_s
            if n.config:
                d["config"] = n.config
            return d

        return {
            "name": self.name,
            "nodes": [node_dict(n) for n in self.nodes],
            "edges": [{"from": e.src, "to": e.dst, **({"label": e.label} if e.label else {})}
                      for e in self.edges],
        }


# ── Parse ─────────────────────────────────────────────────────────────────────

def parse(raw: dict) -> Graph:
    """dict (từ JSON/TOML) → Graph. Chỉ raise khi không dựng nổi object;
    mọi lỗi ngữ nghĩa để `validate()` báo cho gọn một chỗ."""
    if not isinstance(raw, dict):
        raise GraphError("Workflow phải là object")

    raw_nodes = raw.get("nodes")
    raw_edges = raw.get("edges", [])
    if not isinstance(raw_nodes, list):
        raise GraphError("`nodes` phải là list")
    if not isinstance(raw_edges, list):
        raise GraphError("`edges` phải là list")

    nodes: list[Node] = []
    for i, rn in enumerate(raw_nodes):
        if not isinstance(rn, dict):
            raise GraphError(f"nodes[{i}] phải là object")
        nid = str(rn.get("id", "")).strip()
        if not nid:
            raise GraphError(f"nodes[{i}] thiếu `id`")
        nodes.append(Node(
            id=nid,
            type=str(rn.get("type", "")).strip(),
            label=str(rn.get("label", "")),
            runtime=str(rn.get("runtime", "")).strip(),
            model=str(rn.get("model", "")).strip(),
            prompt=str(rn.get("prompt", "")),
            handler=str(rn.get("handler", "")).strip(),
            outward=bool(rn.get("outward", False)),
            timeout_s=int(rn.get("timeout_s", 600)),
            config=dict(rn.get("config", {}) or {}),
        ))

    edges: list[Edge] = []
    for i, re_ in enumerate(raw_edges):
        if not isinstance(re_, dict):
            raise GraphError(f"edges[{i}] phải là object")
        src = str(re_.get("from", re_.get("src", ""))).strip()
        dst = str(re_.get("to", re_.get("dst", ""))).strip()
        if not src or not dst:
            raise GraphError(f"edges[{i}] thiếu `from`/`to`")
        edges.append(Edge(src=src, dst=dst, label=str(re_.get("label", ""))))

    return Graph(name=str(raw.get("name", "")).strip() or "untitled",
                 nodes=nodes, edges=edges)


# ── Invariant: claude phải có gate chắn trước ─────────────────────────────────

def unguarded_claude_nodes(graph: Graph) -> list[str]:
    """BFS từ mọi auto-trigger, **dừng lại ở manual_gate**.

    Node `runtime="claude"` nào còn chạm tới được = chưa có người chắn trước nó
    → listener có thể tự kích Claude → khoá account. Trả về list node id vi phạm
    (đã sort để thông báo lỗi ổn định).

    Node claude nằm sau `manual_trigger`, hoặc sau một `manual_gate`, thì hợp lệ:
    lời gọi Claude khi đó là hệ quả trực tiếp của một cú bấm.
    """
    offenders: set[str] = set()
    seen: set[str] = set()
    frontier = [n.id for n in graph.nodes if n.type in AUTO_TRIGGERS]

    while frontier:
        nid = frontier.pop()
        if nid in seen:
            continue
        seen.add(nid)

        node = graph.get(nid)
        if node is None:
            continue
        if node.is_gate:
            continue                                    # gate chắn — không đi tiếp
        if node.runtime in GATED_RUNTIMES:
            offenders.add(nid)
        frontier.extend(graph.successors(nid))

    return sorted(offenders)


def unguarded_outward_actions(graph: Graph) -> list[str]:
    """Cùng BFS, nhưng cho `action` có `outward=True` (push PR, gửi Slack).
    Đây là cảnh báo chứ không phải lỗi — auto-ack một tin Slack là chuyện hợp lý."""
    offenders: set[str] = set()
    seen: set[str] = set()
    frontier = [n.id for n in graph.nodes if n.type in AUTO_TRIGGERS]

    while frontier:
        nid = frontier.pop()
        if nid in seen:
            continue
        seen.add(nid)
        node = graph.get(nid)
        if node is None or node.is_gate:
            continue
        if node.type == "action" and node.outward:
            offenders.add(nid)
        frontier.extend(graph.successors(nid))

    return sorted(offenders)


def human_checkpoints_upstream_of(graph: Graph, node_id: str) -> list[str]:
    """`manual_gate` / `manual_trigger` có thể đi tới `node_id`.

    Executor đối chiếu list này với bảng approval để biết node có được một cú bấm
    của người cho phép chạy hay không, và cú bấm đó còn tươi hay đã cũ.
    Reverse BFS, dừng ở checkpoint gần nhất — checkpoint xa hơn không thêm nghĩa gì.
    """
    found: set[str] = set()
    seen: set[str] = set()
    frontier = list(graph.predecessors(node_id))
    while frontier:
        nid = frontier.pop()
        if nid in seen:
            continue
        seen.add(nid)
        node = graph.get(nid)
        if node is None:
            continue
        if node.type in HUMAN_CHECKPOINTS:
            found.add(nid)
            continue
        frontier.extend(graph.predecessors(nid))
    return sorted(found)


# ── Validate ──────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    bad_nodes: list[str] = field(default_factory=list)   # để canvas tô đỏ

    @property
    def ok(self) -> bool:
        return not self.errors


def _find_cycle(graph: Graph) -> list[str]:
    """Kahn — trả về các node còn lại trong chu trình (rỗng nếu là DAG)."""
    indeg = {n.id: 0 for n in graph.nodes}
    for e in graph.edges:
        if e.dst in indeg and e.src in indeg:
            indeg[e.dst] += 1

    queue = [nid for nid, d in indeg.items() if d == 0]
    visited = 0
    while queue:
        nid = queue.pop()
        visited += 1
        for succ in graph.successors(nid):
            if succ in indeg:
                indeg[succ] -= 1
                if indeg[succ] == 0:
                    queue.append(succ)

    if visited == len(graph.nodes):
        return []
    return sorted(nid for nid, d in indeg.items() if d > 0)


def _reachable_from_triggers(graph: Graph) -> set[str]:
    seen: set[str] = set()
    frontier = [n.id for n in graph.triggers()]
    while frontier:
        nid = frontier.pop()
        if nid in seen:
            continue
        seen.add(nid)
        frontier.extend(graph.successors(nid))
    return seen


def validate(graph: Graph) -> ValidationResult:
    res = ValidationResult()
    bad: set[str] = set()

    if not graph.nodes:
        res.errors.append("Workflow chưa có node nào")
        return res

    # ids
    seen_ids: set[str] = set()
    for n in graph.nodes:
        if n.id in seen_ids:
            res.errors.append(f"Node id trùng: '{n.id}'")
            bad.add(n.id)
        seen_ids.add(n.id)

    # types + fields
    for n in graph.nodes:
        if n.type not in NODE_TYPES:
            res.errors.append(f"Node '{n.id}': type '{n.type}' không hợp lệ "
                              f"(hợp lệ: {sorted(NODE_TYPES)})")
            bad.add(n.id)
            continue

        if n.type == "task":
            if n.runtime not in RUNTIMES:
                res.errors.append(f"Node '{n.id}': task cần runtime hợp lệ "
                                  f"({sorted(RUNTIMES)}), đang là '{n.runtime}'")
                bad.add(n.id)
            elif n.runtime == "opencode" and not n.model:
                res.errors.append(f"Node '{n.id}': runtime opencode phải khai `model`")
                bad.add(n.id)
            elif n.runtime == "code" and not n.handler:
                res.errors.append(f"Node '{n.id}': runtime code phải khai `handler`")
                bad.add(n.id)
        elif n.runtime:
            res.errors.append(f"Node '{n.id}': type '{n.type}' không được có `runtime`")
            bad.add(n.id)

        if n.type == "action" and not n.handler:
            res.errors.append(f"Node '{n.id}': action phải khai `handler`")
            bad.add(n.id)

    # edges
    for e in graph.edges:
        if graph.get(e.src) is None:
            res.errors.append(f"Edge trỏ tới node không tồn tại: '{e.src}' → '{e.dst}'")
        if graph.get(e.dst) is None:
            res.errors.append(f"Edge trỏ tới node không tồn tại: '{e.src}' → '{e.dst}'")
        if e.src == e.dst:
            res.errors.append(f"Edge tự trỏ vào chính nó: '{e.src}'")
            bad.add(e.src)

    # triggers
    if not graph.triggers():
        res.errors.append(
            f"Workflow phải có ít nhất 1 trigger node ({sorted(TRIGGER_TYPES)})"
        )
    for n in graph.nodes:
        if n.is_trigger and graph.predecessors(n.id):
            res.errors.append(f"Node '{n.id}': trigger không được có edge đi vào")
            bad.add(n.id)

    # DAG
    cycle = _find_cycle(graph)
    if cycle:
        res.errors.append(f"Workflow có chu trình, phải là DAG: {', '.join(cycle)}")
        bad.update(cycle)

    # reachability
    reachable = _reachable_from_triggers(graph)
    orphans = sorted(n.id for n in graph.nodes if n.id not in reachable)
    if orphans:
        res.errors.append(f"Node không tới được từ trigger nào: {', '.join(orphans)}")
        bad.update(orphans)

    # gate rỗng nghĩa
    for n in graph.nodes:
        if n.is_gate and not graph.successors(n.id):
            res.warnings.append(f"Node '{n.id}': manual_gate không có node nào phía sau")

    # ── INVARIANT: claude phải có manual_gate chắn trước ──
    unguarded = unguarded_claude_nodes(graph)
    if unguarded:
        res.errors.append(
            "Node Claude bị auto-trigger kích trực tiếp: "
            f"{', '.join(unguarded)}. "
            "Chèn một `manual_gate` vào giữa — subscription Claude không được "
            "gọi tự động (khoá account). Cần chạy tự động thì đổi node sang "
            'runtime "opencode".'
        )
        bad.update(unguarded)

    outward = unguarded_outward_actions(graph)
    if outward:
        res.warnings.append(
            f"Action tác động ra ngoài chạy tự động không qua duyệt: {', '.join(outward)}. "
            "Cân nhắc chèn manual_gate nếu nó push PR / gửi tin ra ngoài."
        )

    res.bad_nodes = sorted(bad)
    return res


# ── Execution helpers ─────────────────────────────────────────────────────────

def ready_nodes(graph: Graph, state: dict[str, str]) -> list[Node]:
    """Node `pending` mà mọi predecessor đã `done`. Trigger không có
    predecessor nên luôn ready ở lượt đầu."""
    out = []
    for n in graph.nodes:
        if state.get(n.id, PENDING) != PENDING:
            continue
        preds = graph.predecessors(n.id)
        if all(state.get(p) == DONE for p in preds):
            out.append(n)
    return out


def descendants(graph: Graph, node_id: str) -> list[str]:
    """Mọi node phía sau `node_id` (không gồm chính nó)."""
    seen: set[str] = set()
    frontier = graph.successors(node_id)
    while frontier:
        nid = frontier.pop()
        if nid in seen:
            continue
        seen.add(nid)
        frontier.extend(graph.successors(nid))
    seen.discard(node_id)
    return sorted(seen)


def initial_state(graph: Graph) -> dict[str, str]:
    return {n.id: PENDING for n in graph.nodes}
