import React from "react";
import { RunSummary } from "../types";

function fmtDate(s: string): string {
  return new Date(s).toLocaleString("vi-VN", {
    month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

const STATUS_ICON: Record<string, string> = {
  running: "🔄",
  done:    "✅",
  failed:  "❌",
};

export function RunHistory({ runs, currentRunId }: { runs: RunSummary[]; currentRunId?: number }) {
  if (runs.length === 0) return null;

  return (
    <div style={{ marginTop: 28 }}>
      <h3 style={{ color: "#f3f4f6", fontSize: 13, fontWeight: 700, marginBottom: 12 }}>
        📋 Run History
      </h3>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {runs.map(run => (
          <div
            key={run.id}
            style={{
              display:      "flex",
              alignItems:   "center",
              gap:          12,
              padding:      "8px 14px",
              background:   run.id === currentRunId ? "#1e293b" : "#0f172a",
              border:       `1px solid ${run.id === currentRunId ? "#3b82f644" : "#1f2937"}`,
              borderRadius: 8,
              fontSize:     12,
            }}
          >
            <span style={{ minWidth: 16 }}>{STATUS_ICON[run.status] ?? "?"}</span>
            <span style={{ color: "#6b7280", minWidth: 36, fontFamily: "monospace" }}>#{run.id}</span>
            <span style={{ color: "#e5e7eb", flex: 1 }}>{run.client ?? "—"}</span>
            {run.profile && <span style={{ color: "#9ca3af" }}>{run.profile}</span>}
            <span style={{ color: "#6b7280" }}>{fmtDate(run.started_at)}</span>
            <span style={{ color: run.failed_tasks > 0 ? "#fca5a5" : "#9ca3af" }}>
              {run.done_tasks}/{run.total_tasks}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
