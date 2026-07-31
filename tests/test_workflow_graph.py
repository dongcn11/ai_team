"""Validator — trọng tâm là invariant: auto-trigger không được kích Claude trực tiếp."""

import pytest

from ai_team.workflow import graph as g


# ── Helpers ───────────────────────────────────────────────────────────────────

def wf(nodes, edges, name="t"):
    return g.parse({"name": name, "nodes": nodes, "edges": edges})


def edge(a, b):
    return {"from": a, "to": b}


LISTENER = {"id": "trig", "type": "slack_listener"}
MANUAL = {"id": "trig", "type": "manual_trigger"}
GATE = {"id": "gate", "type": "manual_gate"}
CLAUDE = {"id": "cl", "type": "task", "runtime": "claude", "prompt": "fix"}
OPENCODE = {"id": "oc", "type": "task", "runtime": "opencode", "model": "opencode/x"}
CODE = {"id": "co", "type": "task", "runtime": "code", "handler": "h"}


# ── Invariant ─────────────────────────────────────────────────────────────────

def test_claude_ngay_sau_auto_trigger_bi_chan():
    graph = wf([LISTENER, CLAUDE], [edge("trig", "cl")])
    assert g.unguarded_claude_nodes(graph) == ["cl"]
    res = g.validate(graph)
    assert not res.ok
    assert "cl" in res.bad_nodes
    assert any("Claude" in e for e in res.errors)


def test_claude_sau_gate_thi_hop_le():
    graph = wf([LISTENER, GATE, CLAUDE], [edge("trig", "gate"), edge("gate", "cl")])
    assert g.unguarded_claude_nodes(graph) == []
    assert g.validate(graph).ok


def test_claude_sau_manual_trigger_thi_hop_le():
    """manual_trigger không phải auto-trigger → BFS không bắt đầu từ đó."""
    graph = wf([MANUAL, CLAUDE], [edge("trig", "cl")])
    assert g.unguarded_claude_nodes(graph) == []
    assert g.validate(graph).ok


def test_gate_o_xa_van_chan_duoc():
    graph = wf(
        [LISTENER, CODE, GATE, OPENCODE, CLAUDE],
        [edge("trig", "co"), edge("co", "gate"), edge("gate", "oc"), edge("oc", "cl")],
    )
    assert g.unguarded_claude_nodes(graph) == []


def test_mot_duong_khong_gate_la_du_de_vi_pham():
    """Claude tới được bằng 2 đường: một qua gate, một không. Vẫn phải chặn."""
    graph = wf(
        [LISTENER, GATE, CODE, CLAUDE],
        [edge("trig", "gate"), edge("gate", "cl"),
         edge("trig", "co"), edge("co", "cl")],
    )
    assert g.unguarded_claude_nodes(graph) == ["cl"]
    assert not g.validate(graph).ok


def test_gate_sau_claude_khong_cuu_duoc():
    """Đúng lỗi trong thiết kế ban đầu: duyệt PR ở cuối không bảo vệ account."""
    graph = wf(
        [LISTENER, CLAUDE, GATE, {"id": "pr", "type": "action", "handler": "push", "outward": True}],
        [edge("trig", "cl"), edge("cl", "gate"), edge("gate", "pr")],
    )
    assert g.unguarded_claude_nodes(graph) == ["cl"]
    assert not g.validate(graph).ok


def test_opencode_sau_auto_trigger_khong_bi_chan():
    graph = wf([LISTENER, OPENCODE], [edge("trig", "oc")])
    assert g.unguarded_claude_nodes(graph) == []
    assert g.validate(graph).ok


def test_nhieu_claude_node_bao_het():
    nodes = [LISTENER,
             {"id": "c1", "type": "task", "runtime": "claude"},
             {"id": "c2", "type": "task", "runtime": "claude"}]
    graph = wf(nodes, [edge("trig", "c1"), edge("c1", "c2")])
    assert g.unguarded_claude_nodes(graph) == ["c1", "c2"]


# ── Cảnh báo (không chặn) ─────────────────────────────────────────────────────

def test_outward_action_tu_dong_chi_la_warning():
    graph = wf(
        [LISTENER, {"id": "pr", "type": "action", "handler": "push", "outward": True}],
        [edge("trig", "pr")],
    )
    res = g.validate(graph)
    assert res.ok                                   # không chặn
    assert any("ra ngoài" in w for w in res.warnings)


def test_action_khong_outward_khong_warning():
    graph = wf(
        [LISTENER, {"id": "ack", "type": "action", "handler": "ack"}],
        [edge("trig", "ack")],
    )
    res = g.validate(graph)
    assert res.ok
    assert not any("ra ngoài" in w for w in res.warnings)


# ── Kiểm tra cấu trúc ─────────────────────────────────────────────────────────

def test_thieu_trigger():
    graph = wf([CODE], [])
    res = g.validate(graph)
    assert not res.ok
    assert any("trigger" in e for e in res.errors)


def test_chu_trinh():
    graph = wf([MANUAL, CODE, {"id": "c2", "type": "task", "runtime": "code", "handler": "h"}],
               [edge("trig", "co"), edge("co", "c2"), edge("c2", "co")])
    res = g.validate(graph)
    assert not res.ok
    assert any("chu trình" in e for e in res.errors)


def test_node_khong_toi_duoc():
    graph = wf([MANUAL, CODE, {"id": "lac", "type": "task", "runtime": "code", "handler": "h"}],
               [edge("trig", "co")])
    res = g.validate(graph)
    assert not res.ok
    assert "lac" in res.bad_nodes


def test_opencode_thieu_model():
    graph = wf([MANUAL, {"id": "oc", "type": "task", "runtime": "opencode"}],
               [edge("trig", "oc")])
    res = g.validate(graph)
    assert not res.ok
    assert any("model" in e for e in res.errors)


def test_code_thieu_handler():
    graph = wf([MANUAL, {"id": "co", "type": "task", "runtime": "code"}],
               [edge("trig", "co")])
    assert not g.validate(graph).ok


def test_runtime_khong_hop_le():
    graph = wf([MANUAL, {"id": "x", "type": "task", "runtime": "gpt"}], [edge("trig", "x")])
    assert not g.validate(graph).ok


def test_trigger_khong_duoc_co_edge_vao():
    graph = wf([MANUAL, CODE], [edge("trig", "co"), edge("co", "trig")])
    res = g.validate(graph)
    assert not res.ok


def test_edge_tro_node_khong_ton_tai():
    graph = wf([MANUAL], [edge("trig", "khong-co")])
    res = g.validate(graph)
    assert not res.ok
    assert any("không tồn tại" in e for e in res.errors)


def test_id_trung():
    graph = wf([MANUAL, CODE, dict(CODE)], [edge("trig", "co")])
    res = g.validate(graph)
    assert not res.ok
    assert any("trùng" in e for e in res.errors)


def test_parse_thieu_id():
    with pytest.raises(g.GraphError):
        g.parse({"nodes": [{"type": "manual_trigger"}], "edges": []})


def test_parse_nodes_khong_phai_list():
    with pytest.raises(g.GraphError):
        g.parse({"nodes": "abc"})


def test_round_trip_to_dict():
    nodes = [MANUAL, GATE, CLAUDE]
    edges = [edge("trig", "gate"), edge("gate", "cl")]
    graph = wf(nodes, edges, name="rt")
    again = g.parse(graph.to_dict())
    assert [n.id for n in again.nodes] == ["trig", "gate", "cl"]
    assert again.get("cl").runtime == "claude"
    assert g.validate(again).ok


# ── Checkpoint upstream ───────────────────────────────────────────────────────

def test_checkpoint_upstream_lay_gate_gan_nhat():
    graph = wf([LISTENER, GATE, OPENCODE, CLAUDE],
               [edge("trig", "gate"), edge("gate", "oc"), edge("oc", "cl")])
    assert g.human_checkpoints_upstream_of(graph, "cl") == ["gate"]


def test_checkpoint_upstream_gom_ca_manual_trigger():
    graph = wf([MANUAL, CLAUDE], [edge("trig", "cl")])
    assert g.human_checkpoints_upstream_of(graph, "cl") == ["trig"]


def test_checkpoint_upstream_rong_khi_khong_co_ai():
    graph = wf([LISTENER, CLAUDE], [edge("trig", "cl")])
    assert g.human_checkpoints_upstream_of(graph, "cl") == []


# ── ready_nodes ───────────────────────────────────────────────────────────────

def test_ready_nodes_cho_du_predecessor():
    graph = wf([MANUAL, CODE, OPENCODE],
               [edge("trig", "co"), edge("trig", "oc"), edge("co", "oc")])
    state = g.initial_state(graph)
    assert [n.id for n in g.ready_nodes(graph, state)] == ["trig"]

    state["trig"] = g.DONE
    assert [n.id for n in g.ready_nodes(graph, state)] == ["co"]   # oc còn chờ co

    state["co"] = g.DONE
    assert [n.id for n in g.ready_nodes(graph, state)] == ["oc"]


def test_descendants():
    graph = wf([MANUAL, CODE, OPENCODE], [edge("trig", "co"), edge("co", "oc")])
    assert g.descendants(graph, "trig") == ["co", "oc"]
    assert g.descendants(graph, "oc") == []
