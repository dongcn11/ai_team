import React from "react";
import { Issue, Severity } from "../types";

const SEV_COLOR: Record<Severity, string> = {
  high:   "#ef4444",
  medium: "#f59e0b",
  low:    "#6b7280",
};

export function IssuesList({ issues }: { issues: Issue[] }) {
  if (issues.length === 0) return null;

  return (
    <div style={{ marginTop: 28 }}>
      <h3 style={{ color: "#f3f4f6", fontSize: 13, fontWeight: 700, marginBottom: 12 }}>
        ⚠️ Issues ({issues.length})
      </h3>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {issues.map(issue => {
          const color = SEV_COLOR[issue.severity] ?? SEV_COLOR.low;
          return (
            <div
              key={issue.id}
              style={{
                padding:      "10px 14px",
                background:   "#111827",
                border:       `1px solid ${color}33`,
                borderLeft:   `3px solid ${color}`,
                borderRadius: 8,
              }}
            >
              <div style={{ display: "flex", gap: 8, marginBottom: 4, alignItems: "center" }}>
                <span style={{ fontSize: 11, fontWeight: 700, color, textTransform: "uppercase" }}>
                  {issue.severity}
                </span>
                <span style={{ fontSize: 12, color: "#9ca3af" }}>{issue.role}</span>
              </div>
              <p style={{ fontSize: 12, color: "#e5e7eb", margin: "0 0 4px 0" }}>{issue.description}</p>
              {issue.suggestion && (
                <p style={{ fontSize: 11, color: "#9ca3af", margin: 0 }}>💡 {issue.suggestion}</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
