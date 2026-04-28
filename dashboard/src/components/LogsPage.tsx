import React, { useEffect, useRef, useState, useCallback } from "react";
import { useCurrentRun, useRunHistory } from "../hooks/useTasks";
import { useProjects } from "../hooks/useProjects";

type LogEntry = { time: string; type: string; text: string; agent?: string; priority?: string };

export default function LogsPage() {
  const { run, error, loading } = useCurrentRun();
  const history = useRunHistory();
  const { projects } = useProjects();
  const logEndRef = useRef<HTMLDivElement>(null);
  const [autoScroll,   setAutoScroll]   = useState(true);
  const [filter,       setFilter]       = useState("all");
  const [projectId,    setProjectId]    = useState("");
  const [projEntries,  setProjEntries]  = useState<LogEntry[]>([]);
  const [projLoading,  setProjLoading]  = useState(false);
  const [projName,     setProjName]     = useState("");

  const fetchActivity = useCallback(async () => {
    if (!projectId) return;
    setProjLoading(true);
    try {
      const res = await fetch(`/api/projects/${projectId}/activity?limit=50`);
      if (res.ok) setProjEntries(await res.json());
    } catch { /* silent */ }
    setProjLoading(false);
  }, [projectId]);

  useEffect(() => { fetchActivity(); }, [fetchActivity]);

  useEffect(() => {
    const id = setInterval(fetchActivity, 5000);
    return () => clearInterval(id);
  }, [fetchActivity]);

  useEffect(() => {
    if (autoScroll) logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [run, projEntries, autoScroll]);

  const statusIcon: Record<string, string> = {
    pending:  "\u25CB",
    running:  "\u25CF",
    done:     "\u2713",
    failed:   "\u2717",
    task_in_progress: "\u25CF",
    task_review: "\u25C9",
    task_done: "\u2713",
    task_created: "\u25CB",
    comment:  "\u{1F4AC}",
    subtask:  "\u2611",
  };

  const entryColor = (entry: LogEntry) => {
    if (entry.type === "task_done" || entry.type === "done") return "#22c55e";
    if (entry.type === "task_failed" || entry.type === "failed") return "#ef4444";
    if (entry.type === "task_in_progress" || entry.type === "running") return "#3b82f6";
    if (entry.type === "task_review") return "#eab308";
    if (entry.type === "comment") return "#a78bfa";
    if (entry.type === "subtask") return "#60a5fa";
    return "#6b7280";
  };

  const entryIcon = (entry: LogEntry) => statusIcon[entry.type] || "\u25CF";

  const formatTime = (t: string | null) => {
    if (!t) return "--:--:--";
    if (t.includes("T")) return new Date(t).toLocaleTimeString();
    return t;
  };

  const formatDuration = (s: number | null) => {
    if (s === null) return "";
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
  };

  // Global run log entries
  const runEntries: LogEntry[] = [];
  if (run) {
    runEntries.push({
      time: new Date(run.started_at).toLocaleTimeString(),
      type: "running",
      text: `Run #${run.id} started${run.client ? ` (${run.client})` : ""}`,
    });
    run.tasks.forEach(task => {
      if (task.started_at) {
        runEntries.push({
          time: formatTime(task.started_at),
          type: "running",
          text: `[${task.role}] ${task.description || "Started"}`,
        });
      }
      if (task.status === "done") {
        runEntries.push({
          time: formatTime(task.finished_at),
          type: "done",
          text: `[${task.role}] Completed in ${formatDuration(task.duration_s)}`,
        });
      }
      if (task.status === "failed") {
        runEntries.push({
          time: formatTime(task.finished_at),
          type: "failed",
          text: `[${task.role}] FAILED: ${task.error || "Unknown error"}`,
        });
      }
      if (task.status === "pending" && !task.started_at) {
        runEntries.push({
          time: "-",
          type: "pending",
          text: `[${task.role}] Queued - ${task.description || "Waiting to start"}`,
        });
      }
      if (task.status === "running" && task.started_at) {
        runEntries.push({
          time: formatTime(task.started_at),
          type: "running",
          text: `[${task.role}] Running...${task.duration_s ? ` (${formatDuration(task.duration_s)} elapsed)` : ""}`,
        });
      }
    });
    if (run.finished_at) {
      runEntries.push({
        time: new Date(run.finished_at).toLocaleTimeString(),
        type: run.status === "done" ? "done" : "failed",
        text: `Run #${run.id} ${run.status.toUpperCase()}`,
      });
    }
  }

  const stats = run
    ? {
        total: run.tasks.length,
        running: run.tasks.filter(t => t.status === "running").length,
        done: run.tasks.filter(t => t.status === "done").length,
        failed: run.tasks.filter(t => t.status === "failed").length,
        pending: run.tasks.filter(t => t.status === "pending").length,
      }
    : { total: 0, running: 0, done: 0, failed: 0, pending: 0 };

  const isProjectView = !!projectId;
  const entries = isProjectView ? projEntries : runEntries;
  const statsCards = !isProjectView ? (
    [{ label: "Total", value: stats.total, color: "#e2e8f0" },
     { label: "Running", value: stats.running, color: "#3b82f6" },
     { label: "Done", value: stats.done, color: "#22c55e" },
     { label: "Failed", value: stats.failed, color: "#ef4444" },
     { label: "Pending", value: stats.pending, color: "#6b7280" }]
  ) : (
    [{ label: "Total", value: projEntries.length, color: "#a78bfa" }]
  );

  const filteredEntries = filter === "all"
    ? entries
    : isProjectView
      ? entries.filter(e => e.type.startsWith(filter))
      : entries.filter(e => e.type === filter);

  const handleProjectChange = (val: string) => {
    setProjectId(val);
    if (val) {
      const p = projects.find(p => String(p.id) === val);
      setProjName(p?.name || "");
    } else {
      setProjName(""); setProjEntries([]);
    }
  };

  return (
    <div className="logs-page">
      {/* Status bar */}
      <div className="logs-status-bar">
        <div className="logs-status-left">
          <span className={`logs-status-dot ${isProjectView ? "ok" : run ? (run.status === "failed" ? "err" : "ok") : "off"}`} />
          <span style={{ fontSize: 13, fontWeight: 600 }}>
            {isProjectView
              ? `Project: ${projName}`
              : loading ? "Connecting..." : error ? "Disconnected" : run ? `Run #${run.id} · ${run.status}` : "Idle"
            }
          </span>
        </div>
        <div className="logs-status-right">
          <select className="setting-select" style={{ width: 180 }} value={projectId}
            onChange={e => handleProjectChange(e.target.value)}>
            <option value="">-- Orchestrator --</option>
            {projects.filter(p => p.status === "active").map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <label className="logs-auto-scroll">
            <input type="checkbox" checked={autoScroll} onChange={e => setAutoScroll(e.target.checked)} />
            Auto-scroll
          </label>
          <select className="setting-select" style={{ width: 100 }} value={filter} onChange={e => setFilter(e.target.value)}>
            <option value="all">All</option>
            {isProjectView ? (
              <>
                <option value="task">Tasks</option>
                <option value="comment">Comments</option>
                <option value="subtask">SubTasks</option>
              </>
            ) : (
              <>
                <option value="running">Running</option>
                <option value="pending">Pending</option>
                <option value="done">Done</option>
                <option value="failed">Failed</option>
              </>
            )}
          </select>
        </div>
      </div>

      {/* Stats */}
      {!isProjectView && run && (
        <div className="logs-stats-grid">
          {statsCards.map(s => (
            <div key={s.label} className="logs-stat-card" style={{ borderColor: s.color + "44" }}>
              <span className="logs-stat-value" style={{ color: s.color }}>{s.value}</span>
              <span className="logs-stat-label">{s.label}</span>
            </div>
          ))}
        </div>
      )}

      {/* Loading / Error states */}
      {isProjectView && projLoading && <div className="state">Loading activity...</div>}
      {!isProjectView && loading && <div className="state">Connecting to orchestrator...</div>}
      {!isProjectView && error && (
        <div className="state err">
          <p>{error}</p>
          <small>Make sure the orchestrator is running: <code>docker compose up</code></small>
        </div>
      )}
      {!isProjectView && !loading && !error && !run && (
        <div className="state">
          <p>No active runs</p>
          <small>Start the orchestrator or select a project above</small>
        </div>
      )}
      {isProjectView && !projLoading && projEntries.length === 0 && (
        <div className="state">
          <p>No activity yet</p>
          <small>Create tasks and assign agents to see activity here</small>
        </div>
      )}

      {/* Log feed */}
      {(isProjectView ? projEntries.length > 0 : !!run) && (
        <div className="log-feed" onScroll={e => {
          const el = e.currentTarget;
          setAutoScroll(el.scrollHeight - el.scrollTop - el.clientHeight < 40);
        }}>
          {filteredEntries.length === 0 && (
            <div className="log-entry" style={{ color: "#6b7280", justifyContent: "center" }}>
              No entries for filter: {filter}
            </div>
          )}
          {filteredEntries.map((entry, i) => (
            <div key={i} className="log-entry" style={{ background: i % 2 === 0 ? "#0c1222" : "transparent" }}>
              <span className="log-time">
                {isProjectView ? new Date(entry.time).toLocaleString() : entry.time}
              </span>
              <span className="log-status-icon" style={{ color: entryColor(entry) }}>
                {entryIcon(entry)}
              </span>
              <span className="log-text" style={{ color: entry.type === "failed" || entry.type === "task_failed" ? "#fca5a5" : "#d1d5db" }}>
                {entry.text}
              </span>
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      )}

      {/* Run History */}
      {!isProjectView && history.length > 0 && (
        <div className="logs-history">
          <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Run History</h4>
          <div className="history-list">
            {history.map(r => (
              <div key={r.id} className="history-row">
                <span className="history-id">#{r.id}</span>
                <span className="history-meta">
                  {r.client && `${r.client} · `}{r.total_tasks} tasks
                </span>
                <div className="history-bars">
                  {r.done_tasks > 0 && <span className="history-bar done" style={{ flex: r.done_tasks }} />}
                  {r.failed_tasks > 0 && <span className="history-bar failed" style={{ flex: r.failed_tasks }} />}
                  {r.total_tasks - r.done_tasks - r.failed_tasks > 0 && (
                    <span className="history-bar pending" style={{ flex: r.total_tasks - r.done_tasks - r.failed_tasks }} />
                  )}
                </div>
                <span className={`project-status-badge status-${r.status === "running" ? "active" : r.status === "done" ? "completed" : "archived"}`}>
                  {r.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
