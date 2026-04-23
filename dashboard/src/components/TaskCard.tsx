import React from "react";
import { Task } from "../types";
import { StatusBadge } from "./StatusBadge";

function fmtDuration(s: number | null): string {
  if (!s) return "";
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

const BORDER: Record<string, string> = {
  pending: "#374151",
  running: "#3b82f6",
  done:    "#22c55e",
  failed:  "#ef4444",
};

export function TaskCard({ task }: { task: Task }) {
  const border   = BORDER[task.status] ?? BORDER.pending;
  const isRunning = task.status === "running";

  return (
    <div
      style={{
        background:   "#111827",
        border:       `1px solid ${border}${isRunning ? "" : "55"}`,
        borderRadius: 12,
        padding:      "16px 18px",
        transition:   "border-color 0.3s, box-shadow 0.3s",
        boxShadow:    isRunning ? `0 0 14px ${border}33` : "none",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
        <div style={{ fontWeight: 700, fontSize: 13, color: "#f3f4f6", fontFamily: "'JetBrains Mono', monospace" }}>
          {task.role}
        </div>
        <StatusBadge status={task.status} />
      </div>

      {task.description && (
        <div style={{ fontSize: 12, color: "#9ca3af", marginBottom: 10, lineHeight: 1.5 }}>
          {task.description}
        </div>
      )}

      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, fontSize: 11, color: "#6b7280" }}>
        {task.started_at  && <span>▶ {task.started_at}</span>}
        {task.finished_at && <span>⏹ {task.finished_at}</span>}
        {task.duration_s  && <span style={{ color: "#9ca3af" }}>⏱ {fmtDuration(task.duration_s)}</span>}
      </div>

      {task.error && (
        <div
          style={{
            marginTop:    10,
            padding:      "6px 10px",
            background:   "#ef444420",
            border:       "1px solid #ef444440",
            borderRadius: 6,
            fontSize:     11,
            color:        "#fca5a5",
            fontFamily:   "monospace",
            wordBreak:    "break-all",
          }}
        >
          {task.error}
        </div>
      )}
    </div>
  );
}
