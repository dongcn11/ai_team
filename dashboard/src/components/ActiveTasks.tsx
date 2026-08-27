import React, { useState } from "react";
import { useActiveTasks } from "../hooks/useWorkflows";
import { ActiveTask } from "../types";

const TYPE_ICON: Record<string, string> = {
  "action.generate_code": "⚙️",
  "action.create_mr":     "🔀",
  "action.code_review":   "👀",
  "action.custom":        "🧩",
  "logic.condition":      "🔀",
};

function TaskRow({ task, onChanged }: { task: ActiveTask; onChanged: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [content, setContent]   = useState<string | null>(null);
  const [busy, setBusy]         = useState(false);
  const [copied, setCopied]     = useState(false);

  const toggle = async () => {
    const next = !expanded;
    setExpanded(next);
    if (next && content === null) {
      const res = await fetch(`/api/workflows/runs/${task.run_id}/nodes/${task.node_id}/file`);
      setContent(res.ok ? (await res.json()).content : "(không đọc được file)");
    }
  };

  const copyCmd = async () => {
    try {
      await navigator.clipboard.writeText(task.command);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard bị chặn — user tự bôi đen copy */ }
  };

  const isCondition = task.node_type === "logic.condition";

  const markDone = async (decision?: "true" | "false") => {
    setBusy(true);
    try {
      const qs = decision ? `?decision=${decision}` : "";
      const res = await fetch(`/api/workflows/runs/${task.run_id}/nodes/${task.node_id}/done${qs}`, { method: "POST" });
      if (res.ok) onChanged();
    } finally { setBusy(false); }
  };

  return (
    <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, padding: "10px 14px", marginBottom: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontSize: 16 }}>{TYPE_ICON[task.node_type] || "📄"}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, color: "#e2e8f0", fontWeight: 500 }}>{task.node_label}</div>
          <div style={{ fontSize: 11, color: "#6b7280" }}>
            {task.workflow_name} · run #{task.run_id}
            {task.client_folder ? ` · ${task.client_folder}` : " · độc lập"}
          </div>
        </div>
        <span style={{ fontSize: 11, color: "#fbbf24", background: "#422006", padding: "2px 8px", borderRadius: 10 }}>
          chờ chạy
        </span>
        <button className="btn-muted" style={{ fontSize: 11, padding: "3px 10px" }} onClick={toggle}>
          {expanded ? "Ẩn" : "Xem"}
        </button>
        {isCondition ? (
          <>
            <button className="btn-primary" style={{ fontSize: 11, padding: "3px 10px" }}
              disabled={busy} onClick={() => markDone("true")}>{busy ? "..." : "✔ Đúng"}</button>
            <button className="btn-danger" style={{ fontSize: 11, padding: "3px 10px" }}
              disabled={busy} onClick={() => markDone("false")}>{busy ? "..." : "✘ Sai"}</button>
          </>
        ) : (
          <button className="btn-primary" style={{ fontSize: 11, padding: "3px 10px" }} disabled={busy} onClick={() => markDone()}>
            {busy ? "..." : "✓ Đã chạy xong"}
          </button>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
        <code style={{
          flex: 1, fontSize: 11, color: "#93c5fd", background: "#0b1220",
          border: "1px solid #1e293b", borderRadius: 6, padding: "5px 9px",
          overflowX: "auto", whiteSpace: "nowrap",
        }}>
          {task.command}
        </code>
        <button className="btn-muted" style={{ fontSize: 11, padding: "3px 10px" }} onClick={copyCmd}>
          {copied ? "Đã copy" : "Copy"}
        </button>
      </div>

      {expanded && (
        <pre style={{
          marginTop: 8, marginBottom: 0, fontSize: 11, color: "#9ca3af", background: "#0b1220",
          border: "1px solid #1e293b", borderRadius: 6, padding: 10,
          maxHeight: 260, overflow: "auto", whiteSpace: "pre-wrap",
        }}>
          {content ?? "Đang tải..."}
        </pre>
      )}
    </div>
  );
}

export default function ActiveTasks() {
  const { tasks, loading, refetch } = useActiveTasks();

  if (loading) return null;

  return (
    <div style={{ marginBottom: 24 }}>
      <h4 style={{ margin: "0 0 10px", fontSize: 13, color: "#9ca3af", textTransform: "uppercase", letterSpacing: 1 }}>
        Task đang chờ bạn chạy {tasks.length > 0 && `(${tasks.length})`}
      </h4>

      {tasks.length === 0 ? (
        <div style={{ fontSize: 12, color: "#4b5563", background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, padding: "12px 14px" }}>
          Không có task nào đang chờ. Bấm ▶ Run trong một workflow để tạo task.
        </div>
      ) : (
        tasks.map(t => (
          <TaskRow key={`${t.run_id}-${t.node_id}`} task={t} onChanged={refetch} />
        ))
      )}
    </div>
  );
}
