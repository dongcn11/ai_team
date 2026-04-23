import React from "react";
import { Task } from "../types";

export function ProgressBar({ tasks }: { tasks: Task[] }) {
  const total   = tasks.length;
  if (total === 0) return null;

  const done    = tasks.filter(t => t.status === "done").length;
  const failed  = tasks.filter(t => t.status === "failed").length;
  const running = tasks.filter(t => t.status === "running").length;
  const pct     = Math.round(((done + failed) / total) * 100);
  const color   = failed > 0 ? "#ef4444" : "#22c55e";

  return (
    <div style={{ marginBottom: 28 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, fontSize: 13, color: "#9ca3af" }}>
        <span style={{ fontWeight: 600 }}>Overall Progress</span>
        <span>{pct}% &nbsp;({done + failed}/{total} done)</span>
      </div>

      <div style={{ background: "#1f2937", borderRadius: 8, height: 10, overflow: "hidden" }}>
        <div
          style={{
            height:     "100%",
            width:      `${pct}%`,
            background: color,
            borderRadius: 8,
            transition: "width 0.6s ease",
          }}
        />
      </div>

      <div style={{ display: "flex", gap: 20, marginTop: 8, fontSize: 12 }}>
        <span style={{ color: "#22c55e" }}>✅ {done} done</span>
        <span style={{ color: "#3b82f6" }}>🔄 {running} running</span>
        <span style={{ color: "#6b7280" }}>⏳ {total - done - failed - running} pending</span>
        {failed > 0 && <span style={{ color: "#ef4444" }}>❌ {failed} failed</span>}
      </div>
    </div>
  );
}
