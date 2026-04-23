import React from "react";
import { TaskStatus } from "../types";

const CFG: Record<TaskStatus, { icon: string; color: string; label: string }> = {
  pending: { icon: "⏳", color: "#6b7280", label: "pending" },
  running: { icon: "🔄", color: "#3b82f6", label: "running" },
  done:    { icon: "✅", color: "#22c55e", label: "done"    },
  failed:  { icon: "❌", color: "#ef4444", label: "failed"  },
};

export function StatusBadge({ status }: { status: TaskStatus }) {
  const c = CFG[status] ?? CFG.pending;
  return (
    <span
      style={{
        display:     "inline-flex",
        alignItems:  "center",
        gap:         4,
        padding:     "2px 10px",
        borderRadius: 12,
        fontSize:    12,
        fontWeight:  600,
        color:       c.color,
        background:  `${c.color}22`,
        border:      `1px solid ${c.color}44`,
        animation:   status === "running" ? "spin 1.5s linear infinite" : undefined,
      }}
    >
      {c.icon} {c.label}
    </span>
  );
}
