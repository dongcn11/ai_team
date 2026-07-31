import { useCallback, useEffect, useState } from "react";
import {
  WfGraph, WfValidation, WorkflowDetail, WorkflowRun, WorkflowSummary, NodeStatus,
} from "../types";

/** Mẫu có sẵn: đúng luồng trong thiết kế, nhưng gate đặt TRƯỚC node Claude.
 *  Draft chạy tự động bằng OpenCode; Claude chỉ chạy sau khi bạn bấm duyệt. */
const STARTER: WfGraph = {
  nodes: [
    { id: "listener", type: "slack_listener", label: "Listener nghe @tag" },
    { id: "classify", type: "task", runtime: "code", handler: "classify_mention",
      label: "Phân loại mention (bug/support/reply)" },
    { id: "rank", type: "task", runtime: "code", handler: "dedupe_and_rank",
      label: "Gộp + xếp ưu tiên" },
    { id: "draft", type: "task", runtime: "opencode", model: "opencode-go/qwen3.5-plus",
      label: "Draft fix — tự động, không cần người",
      prompt: "Đọc mô tả bug sau và đề xuất fix:\n{{outputs.rank}}" },
    { id: "gate_run", type: "manual_gate", label: "⏸ Bạn bấm duyệt để Claude chạy" },
    { id: "fix", type: "task", runtime: "claude",
      label: "Claude sửa code + test",
      prompt: "Sửa bug theo draft sau, viết test:\n{{outputs.draft}}" },
    { id: "gate_pr", type: "manual_gate", label: "⏸ Review diff trước khi push" },
    { id: "pr", type: "action", handler: "push_pr", outward: true,
      label: "Push PR + báo Slack" },
  ],
  edges: [
    { from: "listener", to: "classify" },
    { from: "classify", to: "rank" },
    { from: "rank", to: "draft" },
    { from: "draft", to: "gate_run" },
    { from: "gate_run", to: "fix" },
    { from: "fix", to: "gate_pr" },
    { from: "gate_pr", to: "pr" },
  ],
};

const PANEL = { background: "#0f172a", border: "1px solid #1e293b", borderRadius: 10 };

const STATUS_COLOR: Record<NodeStatus | string, string> = {
  pending: "#4b5563", running: "#fbbf24", done: "#4ade80",
  failed: "#f87171", waiting: "#60a5fa", skipped: "#374151",
};

function runtimeBadge(node: { type: string; runtime?: string; outward?: boolean }) {
  if (node.runtime === "claude") return { text: "claude", color: "#c084fc", title: "Cần manual_gate chắn trước — đã kiểm lúc lưu" };
  if (node.runtime === "opencode") return { text: "opencode", color: "#4ade80", title: "Chạy tự động thoải mái" };
  if (node.runtime === "code") return { text: "code", color: "#60a5fa", title: "Không gọi model" };
  if (node.type === "manual_gate") return { text: "gate", color: "#fbbf24", title: "Chờ người bấm duyệt" };
  if (node.type === "action") return { text: node.outward ? "action ↗" : "action", color: node.outward ? "#fb923c" : "#9ca3af", title: node.outward ? "Tác động ra ngoài" : "Tác động nội bộ" };
  return { text: node.type, color: "#6b7280", title: "Trigger" };
}

export default function WorkflowsPage() {
  const [list, setList] = useState<WorkflowSummary[]>([]);
  const [selected, setSelected] = useState<WorkflowDetail | null>(null);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Form tạo mới
  const [showNew, setShowNew] = useState(false);
  const [newName, setNewName] = useState("");
  const [newJson, setNewJson] = useState(JSON.stringify(STARTER, null, 2));
  const [validation, setValidation] = useState<WfValidation | null>(null);

  const loadList = useCallback(async () => {
    const r = await fetch("/api/workflows");
    if (r.ok) setList(await r.json());
    else setErr(`GET /api/workflows → ${r.status}`);
  }, []);

  const loadRuns = useCallback(async (id: number) => {
    const r = await fetch(`/api/workflows/${id}/runs?limit=10`);
    if (r.ok) setRuns(await r.json());
  }, []);

  const select = useCallback(async (id: number) => {
    const r = await fetch(`/api/workflows/${id}`);
    if (r.ok) {
      setSelected(await r.json());
      await loadRuns(id);
    }
  }, [loadRuns]);

  useEffect(() => { loadList(); }, [loadList]);

  // Poll runs khi đang có run chạy/chờ
  useEffect(() => {
    if (!selected) return;
    const t = setInterval(() => loadRuns(selected.id), 4000);
    return () => clearInterval(t);
  }, [selected, loadRuns]);

  const parseJson = (): WfGraph | null => {
    try {
      const g = JSON.parse(newJson);
      if (!g || typeof g !== "object" || !Array.isArray(g.nodes)) {
        setValidation({ ok: false, errors: ["JSON phải có `nodes` là array"], warnings: [], bad_nodes: [] });
        return null;
      }
      return g;
    } catch (e) {
      setValidation({ ok: false, errors: [`JSON không parse được: ${String(e)}`], warnings: [], bad_nodes: [] });
      return null;
    }
  };

  const doValidate = async () => {
    const g = parseJson();
    if (!g) return;
    setBusy(true);
    const r = await fetch("/api/workflows/validate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newName || "draft", nodes: g.nodes, edges: g.edges ?? [] }),
    });
    setValidation(r.ok ? await r.json()
      : { ok: false, errors: [`POST /validate → ${r.status}`], warnings: [], bad_nodes: [] });
    setBusy(false);
  };

  const doCreate = async () => {
    const g = parseJson();
    if (!g || !newName.trim()) {
      if (!newName.trim()) setValidation({ ok: false, errors: ["Cần đặt tên workflow"], warnings: [], bad_nodes: [] });
      return;
    }
    setBusy(true);
    const r = await fetch("/api/workflows", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: newName.trim(),
        graph: { name: newName.trim(), nodes: g.nodes, edges: g.edges ?? [] },
      }),
    });
    if (r.ok) {
      setShowNew(false);
      setValidation(null);
      setNewName("");
      await loadList();
    } else {
      const body = await r.json().catch(() => null);
      const d = body?.detail;
      setValidation({
        ok: false,
        errors: d?.errors ?? [typeof d === "string" ? d : `POST → ${r.status}`],
        warnings: d?.warnings ?? [],
        bad_nodes: d?.bad_nodes ?? [],
      });
    }
    setBusy(false);
  };

  const startRun = async (triggerType: string) => {
    if (!selected) return;
    setBusy(true);
    const r = await fetch(`/api/workflows/${selected.id}/runs`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trigger_type: triggerType, payload: { started_by: "dashboard" } }),
    });
    if (!r.ok) {
      const b = await r.json().catch(() => null);
      setErr(typeof b?.detail === "string" ? b.detail : `Start → ${r.status}`);
    } else {
      setErr(null);
      await loadRuns(selected.id);
    }
    setBusy(false);
  };

  const approve = async (runId: number, nodeId: string) => {
    setBusy(true);
    const r = await fetch(`/api/workflows/runs/${runId}/approve`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ node_id: nodeId, approved_by: "dashboard" }),
    });
    if (!r.ok) {
      const b = await r.json().catch(() => null);
      setErr(typeof b?.detail === "string" ? b.detail : `Approve → ${r.status}`);
    } else {
      setErr(null);
      if (selected) await loadRuns(selected.id);
    }
    setBusy(false);
  };

  const deleteWf = async (id: number) => {
    setBusy(true);
    const r = await fetch(`/api/workflows/${id}`, { method: "DELETE" });
    if (!r.ok) {
      const b = await r.json().catch(() => null);
      setErr(typeof b?.detail === "string" ? b.detail : `Delete → ${r.status}`);
    } else {
      if (selected?.id === id) { setSelected(null); setRuns([]); }
      await loadList();
    }
    setBusy(false);
  };

  const triggerTypes = selected
    ? Array.from(new Set(selected.graph.nodes
        .filter(n => ["slack_listener", "cron", "webhook", "manual_trigger"].includes(n.type))
        .map(n => n.type)))
    : [];

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto" }}>
      {/* Giải thích luật — lý do tồn tại của gate */}
      <div style={{ ...PANEL, padding: "12px 16px", marginBottom: 16, borderLeft: "3px solid #c084fc" }}>
        <div style={{ fontSize: 13, color: "#e2e8f0", fontWeight: 600, marginBottom: 4 }}>
          Luật của engine
        </div>
        <div style={{ fontSize: 12, color: "#9ca3af", lineHeight: 1.6 }}>
          Mọi đường từ auto-trigger (<code>slack_listener</code> / <code>cron</code> / <code>webhook</code>) tới node{" "}
          <code style={{ color: "#c084fc" }}>runtime: "claude"</code> phải đi qua ít nhất một{" "}
          <code style={{ color: "#fbbf24" }}>manual_gate</code>. Graph vi phạm <b>không lưu được</b> — API trả 400 kèm node sai.
          <br />
          Gate đặt <i>sau</i> node Claude (duyệt PR) bảo vệ repo nhưng không bảo vệ account: lời gọi model
          vẫn do listener kích. Cần chạy tự động thì để node đó là <code style={{ color: "#4ade80" }}>opencode</code>.
        </div>
      </div>

      {err && (
        <div style={{ ...PANEL, padding: "10px 14px", marginBottom: 12, borderColor: "#7f1d1d", color: "#f87171", fontSize: 12 }}>
          {err}
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: 15 }}>Workflows ({list.length})</h3>
        <button className="btn-primary" style={{ fontSize: 12, padding: "5px 12px" }}
          onClick={() => { setShowNew(v => !v); setValidation(null); }}>
          {showNew ? "Đóng" : "+ Workflow mới"}
        </button>
      </div>

      {/* Tạo mới */}
      {showNew && (
        <div style={{ ...PANEL, padding: 16, marginBottom: 16 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 10, flexWrap: "wrap" }}>
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Tên</label>
              <input className="setting-input" style={{ width: 260 }} value={newName}
                onChange={e => setNewName(e.target.value)} placeholder="slack-triage" />
            </div>
            <button className="btn-muted" style={{ fontSize: 12 }} disabled={busy} onClick={doValidate}>
              Validate (không lưu)
            </button>
            <button className="btn-primary" style={{ fontSize: 12 }} disabled={busy} onClick={doCreate}>
              {busy ? "Đang xử lý..." : "Lưu workflow"}
            </button>
            <button className="btn-muted" style={{ fontSize: 12 }}
              onClick={() => { setNewJson(JSON.stringify(STARTER, null, 2)); setValidation(null); }}>
              ↺ Mẫu
            </button>
          </div>

          <textarea value={newJson} onChange={e => { setNewJson(e.target.value); setValidation(null); }}
            spellCheck={false}
            style={{ width: "100%", minHeight: 320, background: "#0b1120", color: "#cbd5e1",
              border: "1px solid #1e293b", borderRadius: 6, padding: 12,
              fontFamily: "'JetBrains Mono', monospace", fontSize: 12, lineHeight: 1.5 }} />

          {validation && (
            <div style={{ marginTop: 10, fontSize: 12 }}>
              {validation.ok ? (
                <div style={{ color: "#4ade80" }}>✅ Graph hợp lệ — lưu được</div>
              ) : (
                <div>
                  <div style={{ color: "#f87171", fontWeight: 600, marginBottom: 4 }}>
                    ⛔ Không lưu được ({validation.errors.length} lỗi)
                  </div>
                  <ul style={{ margin: "0 0 8px 18px", color: "#fca5a5", lineHeight: 1.6 }}>
                    {validation.errors.map((e, i) => <li key={i}>{e}</li>)}
                  </ul>
                  {validation.bad_nodes.length > 0 && (
                    <div style={{ color: "#9ca3af" }}>
                      Node sai:{" "}
                      {validation.bad_nodes.map(n => (
                        <code key={n} style={{ background: "#7f1d1d", color: "#fecaca",
                          padding: "1px 6px", borderRadius: 4, marginRight: 4 }}>{n}</code>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {validation.warnings.length > 0 && (
                <ul style={{ margin: "8px 0 0 18px", color: "#fbbf24", lineHeight: 1.6 }}>
                  {validation.warnings.map((w, i) => <li key={i}>⚠️ {w}</li>)}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      {/* Danh sách */}
      {list.length === 0 ? (
        <div style={{ ...PANEL, padding: 24, textAlign: "center", color: "#6b7280", fontSize: 13 }}>
          Chưa có workflow nào. Bấm <b>+ Workflow mới</b> — mẫu có sẵn đúng luồng Slack → triage → duyệt → Claude → PR.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 20 }}>
          {list.map(w => (
            <div key={w.id} style={{ ...PANEL, padding: "10px 14px", display: "flex",
              alignItems: "center", gap: 12, cursor: "pointer",
              borderColor: selected?.id === w.id ? "#3b82f6" : "#1e293b" }}
              onClick={() => select(w.id)}>
              <span style={{ color: "#4b5563", fontSize: 12, minWidth: 30 }}>#{w.id}</span>
              <span style={{ flex: 1, fontSize: 13, color: "#e2e8f0", fontWeight: 500 }}>{w.name}</span>
              <span style={{ fontSize: 11, color: "#6b7280" }}>{w.node_count} node</span>
              {w.claude_nodes.length > 0 && (
                <span style={{ fontSize: 11, color: "#c084fc" }}
                  title={`Node Claude: ${w.claude_nodes.join(", ")} — đều đã có gate chắn trước`}>
                  {w.claude_nodes.length} claude 🔒
                </span>
              )}
              {!w.enabled && <span style={{ fontSize: 11, color: "#6b7280" }}>disabled</span>}
              <button className="btn-danger" style={{ fontSize: 11, padding: "2px 8px" }}
                disabled={busy}
                onClick={e => { e.stopPropagation(); deleteWf(w.id); }}>🗑</button>
            </div>
          ))}
        </div>
      )}

      {/* Chi tiết */}
      {selected && (
        <div style={{ ...PANEL, padding: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <h4 style={{ margin: 0, fontSize: 14 }}>{selected.name}</h4>
            <div style={{ display: "flex", gap: 6 }}>
              {triggerTypes.map(t => (
                <button key={t} className="btn-primary" style={{ fontSize: 12, padding: "4px 12px" }}
                  disabled={busy} onClick={() => startRun(t)}
                  title={t === "manual_trigger"
                    ? "Cú bấm này được ghi làm approval — mở quyền chạy node Claude phía sau"
                    : "Mô phỏng trigger tự động; node Claude vẫn phải chờ bạn duyệt ở gate"}>
                  ▶ Run ({t})
                </button>
              ))}
            </div>
          </div>

          {/* Node */}
          <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 18 }}>
            {selected.graph.nodes.map(n => {
              const b = runtimeBadge(n);
              const latest = runs[0];
              const st = latest?.state?.[n.id];
              return (
                <div key={n.id} style={{ display: "flex", alignItems: "center", gap: 10,
                  padding: "6px 10px", background: "#0b1120", borderRadius: 6,
                  border: `1px solid ${n.runtime === "claude" ? "#4c1d95" : "#1e293b"}` }}>
                  {st && <span style={{ width: 8, height: 8, borderRadius: 4,
                    background: STATUS_COLOR[st] ?? "#4b5563" }} title={st} />}
                  <code style={{ fontSize: 11, color: "#6b7280", minWidth: 80 }}>{n.id}</code>
                  <span style={{ flex: 1, fontSize: 12, color: "#cbd5e1" }}>{n.label || n.type}</span>
                  {n.model && <code style={{ fontSize: 10, color: "#4b5563" }}>{n.model}</code>}
                  <span style={{ fontSize: 10, color: b.color, fontWeight: 600 }} title={b.title}>
                    {b.text}
                  </span>
                  {st && <span style={{ fontSize: 10, color: STATUS_COLOR[st] ?? "#4b5563", minWidth: 52, textAlign: "right" }}>{st}</span>}
                </div>
              );
            })}
          </div>

          {/* Runs */}
          <h5 style={{ margin: "0 0 8px", fontSize: 12, color: "#9ca3af",
            textTransform: "uppercase", letterSpacing: 1 }}>Runs</h5>
          {runs.length === 0 ? (
            <div style={{ color: "#4b5563", fontSize: 12 }}>Chưa có run nào.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {runs.map(r => (
                <div key={r.id} style={{ background: "#0b1120", border: "1px solid #1e293b",
                  borderRadius: 6, padding: "8px 12px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ color: "#4b5563", fontSize: 11, minWidth: 30 }}>#{r.id}</span>
                    <span style={{ fontSize: 11, color: "#6b7280" }}>{r.trigger_type}</span>
                    <span style={{ flex: 1 }} />
                    <span style={{ fontSize: 11, color: STATUS_COLOR[r.status] ?? "#9ca3af", fontWeight: 600 }}>
                      {r.status}
                    </span>
                  </div>

                  {r.waiting_on.length > 0 && (
                    <div style={{ marginTop: 8, display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                      <span style={{ fontSize: 11, color: "#60a5fa" }}>⏸ chờ duyệt:</span>
                      {r.waiting_on.map(nid => (
                        <button key={nid} className="btn-primary" style={{ fontSize: 11, padding: "3px 10px" }}
                          disabled={busy} onClick={() => approve(r.id, nid)}
                          title="Ghi approval → executor được phép chạy node phía sau (kể cả Claude)">
                          ✅ Duyệt {nid}
                        </button>
                      ))}
                    </div>
                  )}

                  {r.approvals.length > 0 && (
                    <div style={{ marginTop: 6, fontSize: 10, color: "#4b5563" }}>
                      đã duyệt: {r.approvals.map(a =>
                        `${a.node_id}${a.approved_at ? ` (${new Date(a.approved_at).toLocaleTimeString("vi-VN")})` : ""}`
                      ).join(", ")}
                    </div>
                  )}

                  {r.error && (
                    <div style={{ marginTop: 6, fontSize: 11, color: "#f87171",
                      fontFamily: "monospace", whiteSpace: "pre-wrap" }}>{r.error}</div>
                  )}
                </div>
              ))}
            </div>
          )}

          <div style={{ marginTop: 14, fontSize: 11, color: "#4b5563", lineHeight: 1.6 }}>
            Run cần <b>executor chạy trên host</b> để thực thi node (poll <code>POST /api/workflows/claim</code>) —
            phần đó chưa viết, nên run sẽ nằm ở <code>queued</code>. Node <code>code</code>/<code>action</code> cũng
            cần handler đăng ký trong <code>ai_team/workflow/executor.py</code>.
          </div>
        </div>
      )}
    </div>
  );
}
