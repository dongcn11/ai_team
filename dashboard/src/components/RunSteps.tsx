import React, { useCallback, useEffect, useState } from "react";
import { RunDetail, RunStep, WorkflowRun, NodeRunStatus } from "../types";

const STATUS_META: Record<NodeRunStatus, { color: string; bg: string; label: string; dot: string }> = {
  pending: { color: "#6b7280", bg: "#111827", label: "chưa tới",  dot: "○" },
  running: { color: "#fbbf24", bg: "#422006", label: "chờ chạy",  dot: "◐" },
  ok:      { color: "#4ade80", bg: "#052e16", label: "xong",      dot: "●" },
  error:   { color: "#f87171", bg: "#450a0a", label: "lỗi",       dot: "✕" },
  skipped: { color: "#64748b", bg: "#0f172a", label: "bỏ qua",    dot: "⊘" },
};

const TYPE_ICON: Record<string, string> = {
  "trigger.slack_mention": "💬",
  "action.generate_code":  "⚙️",
  "action.create_mr":      "🔀",
  "action.code_review":    "👀",
  "action.custom":         "🧩",
  "logic.condition":       "🔀",
};

function fmtTime(iso: string | null) {
  return iso ? new Date(iso).toLocaleTimeString("vi-VN") : "—";
}

function StepRow({ step, runId, onChanged }: { step: RunStep; runId: number; onChanged: () => void }) {
  const [busy, setBusy]       = useState(false);
  const [copied, setCopied]   = useState(false);
  const meta = STATUS_META[step.status] ?? STATUS_META.pending;

  const copyCmd = async () => {
    if (!step.command) return;
    try {
      await navigator.clipboard.writeText(step.command);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard bị chặn */ }
  };

  const markDone = async (decision?: "true" | "false") => {
    setBusy(true);
    try {
      const qs = decision ? `?decision=${decision}` : "";
      const res = await fetch(`/api/workflows/runs/${runId}/nodes/${step.node_id}/done${qs}`, { method: "POST" });
      if (res.ok) onChanged();
    } finally { setBusy(false); }
  };

  return (
    <div style={{ display: "flex", gap: 10, marginBottom: 4 }}>
      {/* Timeline gutter */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 20, paddingTop: 12 }}>
        <span style={{ color: meta.color, fontSize: 13, lineHeight: 1 }}>{meta.dot}</span>
        <div style={{ flex: 1, width: 1, background: "#1e293b", marginTop: 4 }} />
      </div>

      <div style={{ flex: 1, background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, padding: "9px 12px", marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, color: "#4b5563", minWidth: 18 }}>{step.order}.</span>
          <span>{TYPE_ICON[step.node_type] || "📄"}</span>
          <span style={{ fontSize: 13, color: "#e2e8f0", fontWeight: 500, flex: 1 }}>{step.label}</span>

          {step.skills.length > 0 && (
            <span style={{ fontSize: 10, color: "#93c5fd" }}>{step.skills.join("+")}</span>
          )}
          <span style={{ fontSize: 10, color: meta.color, background: meta.bg, padding: "2px 8px", borderRadius: 10 }}>
            {meta.label}
          </span>
          {step.branch && (
            <span style={{
              fontSize: 10, padding: "2px 8px", borderRadius: 10,
              color: step.branch === "true" ? "#4ade80" : "#f87171",
              background: step.branch === "true" ? "#052e16" : "#450a0a",
            }}>
              → nhánh {step.branch === "true" ? "Đúng" : "Sai"}
            </span>
          )}
          {step.status === "running" && step.is_condition && (
            <>
              <button className="btn-primary" style={{ fontSize: 10, padding: "2px 8px" }}
                disabled={busy} onClick={() => markDone("true")}>{busy ? "..." : "✔ Đúng"}</button>
              <button className="btn-danger" style={{ fontSize: 10, padding: "2px 8px" }}
                disabled={busy} onClick={() => markDone("false")}>{busy ? "..." : "✘ Sai"}</button>
            </>
          )}
          {step.status === "running" && !step.is_condition && (
            <button className="btn-primary" style={{ fontSize: 10, padding: "2px 8px" }} disabled={busy} onClick={() => markDone()}>
              {busy ? "..." : "✓ Xong"}
            </button>
          )}
        </div>

        <div style={{ fontSize: 10, color: "#4b5563", marginTop: 3, marginLeft: 26 }}>
          {step.started_at && <>bắt đầu {fmtTime(step.started_at)}</>}
          {step.finished_at && <> · xong {fmtTime(step.finished_at)}</>}
          {step.duration_s !== null && <> · {step.duration_s}s</>}
        </div>

        {step.command && step.status !== "pending" && (
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6, marginLeft: 26 }}>
            <code style={{
              flex: 1, fontSize: 10, color: "#93c5fd", background: "#0b1220",
              border: "1px solid #1e293b", borderRadius: 5, padding: "4px 8px",
              overflowX: "auto", whiteSpace: "nowrap",
            }}>{step.command}</code>
            <button className="btn-muted" style={{ fontSize: 10, padding: "2px 8px" }} onClick={copyCmd}>
              {copied ? "✓" : "Copy"}
            </button>
          </div>
        )}

        {step.result && (
          <div style={{ marginTop: 6, marginLeft: 26 }}>
            <div style={{ fontSize: 10, color: "#4ade80", marginBottom: 3 }}>Kết quả:</div>
            <pre style={{
              margin: 0, fontSize: 11, color: "#cbd5e1", background: "#0b1220",
              border: "1px solid #1e293b", borderRadius: 5, padding: 8,
              maxHeight: 140, overflow: "auto", whiteSpace: "pre-wrap",
            }}>{step.result}</pre>
          </div>
        )}
      </div>
    </div>
  );
}

export default function RunSteps({ workflowId, runId, onRunChange }: {
  workflowId: number;
  runId: number | null;
  onRunChange: (id: number) => void;
}) {
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [runs, setRuns]     = useState<WorkflowRun[]>([]);

  const loadRuns = useCallback(async () => {
    const res = await fetch(`/api/workflows/${workflowId}/runs?limit=20`);
    if (res.ok) setRuns(await res.json());
  }, [workflowId]);

  const loadDetail = useCallback(async () => {
    if (runId === null) { setDetail(null); return; }
    const res = await fetch(`/api/workflows/runs/${runId}/steps`);
    if (res.ok) setDetail(await res.json());
  }, [runId]);

  useEffect(() => { loadRuns(); }, [loadRuns]);
  useEffect(() => { loadDetail(); }, [loadDetail]);

  // poll khi run chưa kết thúc
  useEffect(() => {
    if (!detail || detail.status !== "running") return;
    const id = setInterval(loadDetail, 4000);
    return () => clearInterval(id);
  }, [detail, loadDetail]);

  const refresh = () => { loadDetail(); loadRuns(); };

  if (runId === null) {
    return (
      <div style={{ padding: "10px 14px", fontSize: 12, color: "#4b5563", borderTop: "1px solid #1e293b" }}>
        Chưa có lần chạy nào. Bấm ▶ Run để bắt đầu.
      </div>
    );
  }

  const pct = detail && detail.total_steps > 0 ? Math.round((detail.done_steps / detail.total_steps) * 100) : 0;

  return (
    <div style={{ borderTop: "1px solid #1e293b", maxHeight: 320, overflowY: "auto", padding: "10px 14px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <strong style={{ fontSize: 12, color: "#9ca3af" }}>Lần chạy</strong>
        <select className="setting-select" style={{ width: 240, fontSize: 11 }}
          value={runId} onChange={e => onRunChange(Number(e.target.value))}>
          {runs.map(r => (
            <option key={r.id} value={r.id}>
              #{r.id} · {r.status} · {new Date(r.created_at).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" })}
            </option>
          ))}
        </select>

        {detail && (
          <>
            <div style={{ flex: 1, maxWidth: 160, background: "#1e293b", borderRadius: 4, height: 6, overflow: "hidden" }}>
              <div style={{
                width: `${pct}%`, height: "100%", borderRadius: 4,
                background: detail.status === "done" ? "#4ade80" : "#fbbf24",
              }} />
            </div>
            <span style={{ fontSize: 11, color: "#6b7280" }}>
              {detail.done_steps}/{detail.total_steps} bước
            </span>
            <span style={{ fontSize: 11, color: detail.status === "done" ? "#4ade80" : "#fbbf24" }}>
              {detail.status === "done" ? "hoàn thành" : "đang chạy"}
            </span>
          </>
        )}
        <div style={{ flex: 1 }} />
        <button className="btn-muted" style={{ fontSize: 11, padding: "3px 10px" }} onClick={refresh}>🔄 Làm mới</button>
      </div>

      {detail?.steps.map(s => (
        <StepRow key={s.node_id} step={s} runId={detail.run_id} onChanged={refresh} />
      ))}
    </div>
  );
}
