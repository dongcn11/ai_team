import React, { useEffect, useMemo, useState } from "react";
import { useCurrentRun, useRunHistory } from "./hooks/useTasks";
import { useProjects } from "./hooks/useProjects";
import AgentQuestions from "./components/AgentQuestions";
import { TaskCard }    from "./components/TaskCard";
import { ProgressBar } from "./components/ProgressBar";
import { IssuesList }  from "./components/IssuesList";
import { RunHistory }  from "./components/RunHistory";
import Settings        from "./components/Settings";
import ProjectsPage    from "./components/Projects";
import AgentsPage      from "./components/Agents";
import SkillsPage      from "./components/Skills";
import LogsPage        from "./components/LogsPage";
import WorkflowsPage   from "./components/Workflows";
import BotsPage        from "./components/Bots";
import LlmGatewayPage  from "./components/LlmGateway";
import RunConsole      from "./components/RunConsole";
import AssistantHome   from "./components/AssistantHome";
import AccountsPage    from "./components/Accounts";
import { UserMenu, useAuth } from "./auth";
import { Tab, TAB_INFO } from "./tabs";
import "./App.css";

// Tab nằm trên URL (#projects…): nút Back trên điện thoại quay lại tab trước,
// và gửi/lưu link thẳng tới 1 tab được. Tab không có quyền → tab đầu tiên được vào.
function tabFromHash(allowed: Tab[]): Tab {
  const h = window.location.hash.slice(1) as Tab;
  return allowed.includes(h) ? h : allowed[0] ?? "dashboard";
}

import { RunSummary } from "./types";

function HomeSummary({ history, projectCount, onGoProjects }: {
  history: RunSummary[];
  projectCount: number;
  onGoProjects: () => void;
}) {
  const totalRuns   = history.length;
  const doneRuns    = history.filter(r => r.status === "done").length;
  const failedRuns  = history.filter(r => r.status === "failed").length;
  const successRate = totalRuns > 0 ? Math.round((doneRuns / totalRuns) * 100) : null;
  const recent      = history.slice(0, 5);

  const statCard = (label: string, value: string | number, sub?: string, color?: string) => (
    <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 10, padding: "16px 20px", minWidth: 120 }}>
      <div style={{ fontSize: 24, fontWeight: 700, color: color ?? "#f1f5f9" }}>{value}</div>
      <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>{label}</div>
      {sub && <div style={{ fontSize: 11, color: "#4b5563", marginTop: 4 }}>{sub}</div>}
    </div>
  );

  return (
    <div style={{ maxWidth: 860, margin: "0 auto", padding: "8px 0" }}>
      {/* Stats */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 28 }}>
        {statCard("Projects", projectCount, undefined, "#60a5fa")}
        {statCard("Total Runs", totalRuns)}
        {statCard("Completed", doneRuns, undefined, "#4ade80")}
        {statCard("Failed", failedRuns, undefined, failedRuns > 0 ? "#f87171" : "#4b5563")}
        {successRate !== null && statCard("Success Rate", `${successRate}%`, undefined, successRate >= 80 ? "#4ade80" : successRate >= 50 ? "#fbbf24" : "#f87171")}
      </div>

      {/* Quick actions */}
      <div style={{ display: "flex", gap: 10, marginBottom: 28 }}>
        <button className="btn-primary" onClick={onGoProjects} style={{ fontSize: 13 }}>
          📁 Xem Projects
        </button>
        <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, padding: "8px 14px", fontSize: 12, color: "#6b7280", fontFamily: "monospace", display: "flex", alignItems: "center" }}>
          python main.py --config clients/&lt;project&gt;/settings.toml --prd clients/&lt;project&gt;/prd.md
        </div>
      </div>

      {/* Recent runs */}
      {recent.length > 0 ? (
        <div>
          <h4 style={{ margin: "0 0 12px", fontSize: 13, color: "#9ca3af", textTransform: "uppercase", letterSpacing: 1 }}>Recent Runs</h4>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {recent.map(r => {
              const statusColor = r.status === "done" ? "#4ade80" : r.status === "failed" ? "#f87171" : "#fbbf24";
              const pct = r.total_tasks > 0 ? Math.round((r.done_tasks / r.total_tasks) * 100) : 0;
              const dt  = new Date(r.started_at).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
              return (
                <div key={r.id} style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, padding: "10px 14px", display: "flex", alignItems: "center", gap: 12 }}>
                  <span style={{ color: "#4b5563", fontSize: 12, minWidth: 36 }}>#{r.id}</span>
                  <span style={{ flex: 1, fontSize: 13, color: "#e2e8f0", fontWeight: 500 }}>{r.client ?? "—"}</span>
                  <span style={{ fontSize: 11, color: "#6b7280" }}>{r.profile ?? ""}</span>
                  <div style={{ width: 80, background: "#1e293b", borderRadius: 4, height: 6, overflow: "hidden" }}>
                    <div style={{ width: `${pct}%`, height: "100%", background: statusColor, borderRadius: 4 }} />
                  </div>
                  <span style={{ fontSize: 11, color: "#6b7280", minWidth: 60, textAlign: "right" }}>
                    {r.done_tasks}/{r.total_tasks} tasks
                  </span>
                  <span style={{ fontSize: 11, color: statusColor, minWidth: 44, textAlign: "right" }}>{r.status}</span>
                  <span style={{ fontSize: 11, color: "#4b5563", minWidth: 110, textAlign: "right" }}>{dt}</span>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div style={{ color: "#4b5563", fontSize: 13, textAlign: "center", padding: "32px 0" }}>
          Chưa có run nào. Chạy orchestrator để bắt đầu.
        </div>
      )}
    </div>
  );
}

export default function App() {
  const { user } = useAuth();
  // Màn hình được vào: admin thấy hết + Tài khoản; còn lại theo quyền (mặc định Dashboard).
  const allowed = useMemo(() => TAB_INFO.map(t => t.key).filter(k =>
    k === "accounts" ? user.is_admin : user.is_admin || user.permissions.includes(k)), [user]);
  const allowedKey = allowed.join(",");
  const [tab, setTabState] = useState<Tab>(() => tabFromHash(allowed));
  useEffect(() => {
    const onHash = () => setTabState(tabFromHash(allowed));
    onHash();                                  // quyền đổi (admin sửa) → kéo về tab hợp lệ
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allowedKey]);
  const setTab = (t: Tab) => {
    if (t !== tab) window.location.hash = t;
    setTabState(t);
  };
  const { run, error, loading } = useCurrentRun();
  const history                 = useRunHistory();
  const { projects }            = useProjects();

  return (
    <div className={tab === "dashboard" ? "app app-fill" : "app"}>
      <header className="header">
        <div className="header-left">
          <h1>🤖 AI Team Dashboard</h1>
          <nav className="header-nav">
            {TAB_INFO.filter(t => allowed.includes(t.key)).map(t => (
              <button key={t.key} className={`nav-tab ${tab === t.key ? "active" : ""}`}
                onClick={() => setTab(t.key)} title={t.title}>
                {t.label}
              </button>
            ))}
          </nav>
          {tab === "pipeline" && run && (
            <div className="run-meta">
              <span className="badge">Run #{run.id}</span>
              {run.client  && <span className="badge muted">{run.client}</span>}
              {run.profile && <span className="badge muted">{run.profile}</span>}
            </div>
          )}
        </div>
        <div className="header-right">
          <span style={{ fontSize: 12, color: "#6b7280" }}>
            {error ? error : run ? `${run.status}` : "no run"}
          </span>
          <div className={`dot ${error ? "error" : "ok"}`} title={error ?? "Connected"} />
          <UserMenu />
        </div>
      </header>

      <main className={tab === "dashboard" ? "main-full" : "main"}>
        {/* Việc agent chờ dev chốt. Màn hình chạy có thẻ hỏi/đáp riêng ngay cạnh
            bước đang bị chặn nên không lặp lại banner ở đó. */}
        {tab !== "runs" && tab !== "accounts" && <AgentQuestions />}

        {tab === "dashboard" && <AssistantHome onOpenProject={() => setTab("projects")} />}

        {tab === "projects"  && <ProjectsPage />}
        {tab === "agents"    && <AgentsPage />}
        {tab === "skills"    && <SkillsPage />}
        {tab === "workflows" && <WorkflowsPage />}
        {tab === "runs"      && <RunConsole />}
        {tab === "bots"      && <BotsPage />}
        {tab === "api"       && <LlmGatewayPage />}
        {tab === "logs"      && <LogsPage />}
        {tab === "settings"  && <Settings />}
        {tab === "accounts"  && <AccountsPage />}

        {tab === "pipeline" && (
          <>
            {loading && <div className="state">Connecting to API...</div>}

            {!loading && error && (
              <div className="state err">
                {error}
                <br />
                <small style={{ color: "#6b7280", marginTop: 8, display: "block" }}>
                  Make sure the API is running: <code>docker compose up</code>
                </small>
              </div>
            )}

            {!loading && !error && !run && (
              <HomeSummary
                history={history}
                projectCount={projects.length}
                onGoProjects={() => setTab("projects")}
              />
            )}

            {run && (
              <>
                <ProgressBar tasks={run.tasks} />

                <div className="task-grid">
                  {run.tasks.map(task => (
                    <TaskCard key={task.id} task={task} />
                  ))}
                </div>

                <IssuesList issues={run.issues} />
              </>
            )}

            <RunHistory runs={history} currentRunId={run?.id} />
          </>
        )}
      </main>
    </div>
  );
}
