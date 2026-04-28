import React, { useState } from "react";
import { useCurrentRun, useRunHistory } from "./hooks/useTasks";
import { TaskCard }    from "./components/TaskCard";
import { ProgressBar } from "./components/ProgressBar";
import { IssuesList }  from "./components/IssuesList";
import { RunHistory }  from "./components/RunHistory";
import Settings        from "./components/Settings";
import ProjectsPage    from "./components/Projects";
import AgentsPage      from "./components/Agents";
import LogsPage        from "./components/LogsPage";
import "./App.css";

type Tab = "dashboard" | "projects" | "agents" | "logs" | "settings";

export default function App() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const { run, error, loading } = useCurrentRun();
  const history                 = useRunHistory();

  return (
    <div className="app">
      <header className="header">
        <div className="header-left">
          <h1>🤖 AI Team Dashboard</h1>
          <nav className="header-nav">
            <button className={`nav-tab ${tab === "dashboard" ? "active" : ""}`} onClick={() => setTab("dashboard")}>
              Dashboard
            </button>
            <button className={`nav-tab ${tab === "projects" ? "active" : ""}`} onClick={() => setTab("projects")}>
              Projects
            </button>
            <button className={`nav-tab ${tab === "agents" ? "active" : ""}`} onClick={() => setTab("agents")}>
              Agents
            </button>
            <button className={`nav-tab ${tab === "logs" ? "active" : ""}`} onClick={() => setTab("logs")}>
              Logs
            </button>
            <button className={`nav-tab ${tab === "settings" ? "active" : ""}`} onClick={() => setTab("settings")}>
              Settings
            </button>
          </nav>
          {tab === "dashboard" && run && (
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
        </div>
      </header>

      <main className="main">
        {tab === "projects"  && <ProjectsPage />}
        {tab === "agents"    && <AgentsPage />}
        {tab === "logs"      && <LogsPage />}
        {tab === "settings"  && <Settings />}

        {tab === "dashboard" && (
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
              <div className="state">
                No runs found.
                <br />
                <small style={{ color: "#6b7280", marginTop: 8, display: "block" }}>
                  Start the orchestrator to create the first run.
                </small>
              </div>
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
