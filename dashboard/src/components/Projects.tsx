import React, { useState, useCallback, useEffect } from "react";
import { useProjects } from "../hooks/useProjects";
import { useProjectWorkflows } from "../hooks/useWorkflows";
import ProjectWorkflows from "./ProjectWorkflows";
import RunConsole from "./RunConsole";
import { Project, AgentFS, RunSummary, TaskRunSummary } from "../types";

const VALID_KEYS = ["pm","scrum","analyst","be1","be2","fe1","fe2","fs1","fs2","leader"];
// Chỉ opencode. Claude Code bị chặn trong pipeline tự động (rủi ro khoá account
// — subscription cá nhân không dùng cho automation chạy nền). Xem ai_team/runner.py.
const DEFAULT_MODELS: Record<string,string> = { opencode: "opencode-go/qwen3.5-plus" };
const OPENCODE_GO_MODELS = [
  { value: "opencode-go/qwen3.5-plus",    label: "qwen3.5-plus   (Go plan)"  },
  { value: "opencode-go/qwen3.6-plus",    label: "qwen3.6-plus   (Go plan)"  },
  { value: "opencode-go/minimax-m2.7",    label: "minimax-m2.7   (Go plan)"  },
  { value: "opencode-go/deepseek-v4-pro", label: "deepseek-v4-pro (Go plan)" },
  { value: "opencode-go/glm-5.1",         label: "glm-5.1        (Go plan)"  },
  { value: "opencode-go/mimo-v2.5-pro",   label: "mimo-v2.5-pro  (Go plan)"  },
  { value: "opencode/qwen3.5-plus",       label: "⚠️ qwen3.5-plus   (pay-per-use)" },
  { value: "opencode/qwen3.6-plus",       label: "⚠️ qwen3.6-plus   (pay-per-use)" },
  { value: "opencode/minimax-m2.7",       label: "⚠️ minimax-m2.7   (pay-per-use)" },
  { value: "other",                       label: "Nhập tay..."   },
];

export default function ProjectsPage() {
  const { projects, loading, error, refetch } = useProjects();
  const [selected,    setSelected]    = useState<Project | null>(null);
  const [projRuns,    setProjRuns]    = useState<RunSummary[]>([]);
  const [activeTab,   setActiveTab]   = useState<"features" | "workflows" | "agents" | "prd" | "runs" | "docs">("features");

  // Danh sách workflow của RIÊNG project đang mở — dùng cho tab Workflows và
  // cho dropdown "Workflow" ở từng task bên tab Features.
  const { workflows: projectWorkflows, refetch: refetchProjectWorkflows } =
    useProjectWorkflows(selected?.id ?? null);

  // Run queue (▶ Run button → POST /api/run-jobs; worker.py chạy tuần tự)
  type RunJob = {
    id: number; client_folder: string; status: string;
    error: string | null; created_at: string;
    started_at: string | null; finished_at: string | null;
  };
  const [queue,      setQueue]      = useState<RunJob[]>([]);
  const [triggering, setTriggering] = useState(false);
  // Xem chi tiết / huỷ lần chạy của 1 task ngay tại danh sách Features
  const [runDetail, setRunDetail] = useState<{ workflowId: number | null; runId: number } | null>(null);
  const [cancellingRun, setCancellingRun] = useState<number | null>(null);

  // Delete project
  const [showDeleteProject,  setShowDeleteProject]  = useState(false);
  const [deleteProjecting,   setDeleteProjecting]   = useState(false);
  const [deleteStep,         setDeleteStep]         = useState<"confirm"|"done">("confirm");

  // Inline-editable project header fields
  type EditableField = "name" | "backend" | "frontend" | "output_dir" | "profile";
  const [editingField, setEditingField] = useState<EditableField | null>(null);
  const [editDraft,    setEditDraft]    = useState("");
  const [editSaving,   setEditSaving]   = useState(false);

  // Remove agent confirm dialog
  const AGENTS_WITH_WORKSPACE = ["be1","be2","fe1","fe2","fs1","fs2"];
  const [removeAgentKey,      setRemoveAgentKey]      = useState<string | null>(null);
  const [removeWithCleanup,   setRemoveWithCleanup]   = useState(false);
  const [removedWorkspaceMsg, setRemovedWorkspaceMsg] = useState<string | null>(null);

  // New project form
  const [showNewProject,   setShowNewProject]   = useState(false);
  const [npFolderName,     setNpFolderName]     = useState("");
  const [npProfile,        setNpProfile]        = useState("fullstack");
  const [npTool,           setNpTool]           = useState("opencode");
  const [npBackend,        setNpBackend]        = useState("");
  const [npFrontend,       setNpFrontend]       = useState("");
  const [npSaving,         setNpSaving]         = useState(false);
  const [npError,          setNpError]          = useState("");

  // Profiles list — load từ /api/projects/profiles (đọc từ profiles.yaml)
  type ProfileInfo = { name: string; label: string; agents: string[]; stages_disabled: string[]; display: string };
  const [profilesList, setProfilesList] = useState<ProfileInfo[]>([]);
  useEffect(() => {
    fetch("/api/projects/profiles")
      .then(r => r.ok ? r.json() : [])
      .then((data: ProfileInfo[]) => setProfilesList(data))
      .catch(() => setProfilesList([]));
  }, []);

  // Agent management
  const [settingsAgents, setSettingsAgents] = useState<AgentFS[]>([]);
  const [showAddAgent,   setShowAddAgent]   = useState(false);
  const [addKey,         setAddKey]         = useState("be1");
  const [addTool,        setAddTool]        = useState("opencode");
  const [addModel,       setAddModel]       = useState("opencode-go/qwen3.5-plus");
  const [addSaving,      setAddSaving]      = useState(false);

  // PRD
  const [prdContent,  setPrdContent]  = useState<string | null>(null);
  const [prdExists,   setPrdExists]   = useState(false);
  const [prdEditing,  setPrdEditing]  = useState(false);
  const [prdDraft,    setPrdDraft]    = useState("");
  const [prdSaving,   setPrdSaving]   = useState(false);

  // Features
  type FeatureFile = {
    id: number; filename: string; original_filename: string;
    description: string; size: number; content_type: string; uploaded_at: string;
  };
  type Feature = {
    id: number; name: string; description: string | null;
    status: string; priority: string; created_at: string;
    acceptance_criteria?: string; files?: FeatureFile[];
    /** Workflow task này chạy theo (null = chưa chọn) */
    workflow_id?: number | null;
    workflow_name?: string | null;
    /** Lần chạy workflow gần nhất của task */
    latest_run?: TaskRunSummary | null;
  };
  // Pending attachment chosen *before* the feature exists (uploaded after create).
  type PendingFile = { id: string; file: File; description: string };
  const [features,        setFeatures]        = useState<Feature[]>([]);
  const [featuresLoaded,  setFeaturesLoaded]  = useState(false);
  const [showAddFeature,  setShowAddFeature]  = useState(false);
  const [featureName,     setFeatureName]     = useState("");
  const [featureDesc,     setFeatureDesc]     = useState("");
  const [featurePriority, setFeaturePriority] = useState("medium");
  const [featureAccept,   setFeatureAccept]   = useState("");
  const [pendingFiles,    setPendingFiles]    = useState<PendingFile[]>([]);
  const [featureSaving,   setFeatureSaving]   = useState(false);
  const [featureError,    setFeatureError]    = useState("");
  const [featureWorkflowId, setFeatureWorkflowId] = useState("");   // workflow chọn trong form tạo
  const [runningFeatureId,  setRunningFeatureId]  = useState<number | null>(null);
  const [featureRunError,   setFeatureRunError]   = useState<Record<number, string>>({});

  // Docs
  const [docFiles,    setDocFiles]    = useState<{path: string; name: string; size: number}[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [docContent,  setDocContent]  = useState<string | null>(null);
  const [docLoading,  setDocLoading]  = useState(false);

  const openProject = useCallback(async (id: string) => {
    const res = await fetch(`/api/projects/${id}`);
    if (res.ok) {
      const proj = await res.json();
      setSelected(proj);
      setActiveTab("features");
      loadFeatures(proj.id);
      setPrdContent(null); setPrdEditing(false);
      setDocFiles([]); setSelectedDoc(null); setDocContent(null);
      setShowAddAgent(false);
      setFeatures([]); setFeaturesLoaded(false); setShowAddFeature(false);
    }
  }, []);

  const loadSettingsAgents = useCallback(async (id: string) => {
    const res = await fetch(`/api/projects/${id}/settings-agents`);
    if (res.ok) setSettingsAgents(await res.json());
  }, []);

  useEffect(() => {
    if (selected) loadSettingsAgents(selected.id);
  }, [selected, loadSettingsAgents]);

  const loadRunsAndQueue = useCallback(async (id: string) => {
    const [runsRes, queueRes] = await Promise.all([
      fetch(`/api/runs?client=${id}&limit=10`),
      fetch(`/api/run-jobs?client_folder=${id}&limit=10`),
    ]);
    if (runsRes.ok)  setProjRuns(await runsRes.json());
    if (queueRes.ok) setQueue(await queueRes.json());
  }, []);

  useEffect(() => {
    if (!selected) return;
    const id = selected.id;
    loadRunsAndQueue(id);
    // Poll trong khi còn job đang chạy/chờ để cập nhật trạng thái
    const t = setInterval(() => loadRunsAndQueue(id), 4000);
    return () => clearInterval(t);
  }, [selected, loadRunsAndQueue]);

  const triggerRun = useCallback(async () => {
    if (!selected) return;
    setTriggering(true);
    try {
      const res = await fetch(`/api/run-jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ client_folder: selected.id }),
      });
      if (res.ok) {
        await loadRunsAndQueue(selected.id);
      } else {
        const err = await res.json().catch(() => ({}));
        alert(`Không xếp được hàng đợi: ${err.detail || res.status}`);
      }
    } finally {
      setTriggering(false);
    }
  }, [selected, loadRunsAndQueue]);

  const cancelJob = useCallback(async (jobId: number) => {
    if (!selected) return;
    const res = await fetch(`/api/run-jobs/${jobId}/cancel`, { method: "POST" });
    if (res.ok) await loadRunsAndQueue(selected.id);
  }, [selected, loadRunsAndQueue]);

  const handleAddAgent = async () => {
    if (!selected) return;
    setAddSaving(true);
    const res = await fetch(`/api/projects/${selected.id}/settings-agents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: addKey, tool: addTool, model: addModel }),
    });
    if (res.ok) { setSettingsAgents(await res.json()); setShowAddAgent(false); }
    setAddSaving(false);
  };

  const confirmRemoveAgent = (key: string) => {
    setRemoveAgentKey(key);
    setRemoveWithCleanup(false);
    setRemovedWorkspaceMsg(null);
  };

  const handleRemoveAgent = async () => {
    if (!selected || !removeAgentKey) return;
    const url = `/api/projects/${selected.id}/settings-agents/${removeAgentKey}?cleanup=${removeWithCleanup}`;
    const res = await fetch(url, { method: "DELETE" });
    if (res.ok) {
      const data = await res.json();
      setSettingsAgents(data.agents);
      setRemovedWorkspaceMsg(data.deleted_workspace
        ? `Đã xóa workspace: ${data.deleted_workspace}`
        : null);
    }
    setRemoveAgentKey(null);
  };

  const loadPrd = useCallback(async (id: string) => {
    const res = await fetch(`/api/projects/${id}/prd`);
    if (res.ok) {
      const data = await res.json();
      setPrdExists(data.exists);
      setPrdContent(data.content);
      setPrdDraft(data.content);
    }
  }, []);

  const savePrd = async () => {
    if (!selected) return;
    setPrdSaving(true);
    const res = await fetch(`/api/projects/${selected.id}/prd`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: prdDraft }),
    });
    if (res.ok) { setPrdContent(prdDraft); setPrdExists(true); setPrdEditing(false); }
    setPrdSaving(false);
  };

  const deletePrd = async () => {
    if (!selected || !window.confirm("Xóa prd.md?")) return;
    const res = await fetch(`/api/projects/${selected.id}/prd`, { method: "DELETE" });
    if (res.ok) { setPrdContent(""); setPrdExists(false); setPrdEditing(false); }
  };

  const loadFeatures = useCallback(async (id: string) => {
    const res = await fetch(`/api/projects/${id}/features`);
    if (res.ok) { setFeatures(await res.json()); setFeaturesLoaded(true); }
  }, []);

  const resetFeatureForm = () => {
    setFeatureName(""); setFeatureDesc("");
    setFeaturePriority("medium"); setFeatureAccept("");
    setPendingFiles([]); setFeatureError(""); setFeatureWorkflowId("");
  };

  const closeAddFeatureModal = () => {
    setShowAddFeature(false);
    resetFeatureForm();
  };

  const addPendingFiles = (fl: FileList | null) => {
    if (!fl || fl.length === 0) return;
    const next: PendingFile[] = Array.from(fl).map(f => ({
      id: `${f.name}-${f.size}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      file: f,
      description: "",
    }));
    setPendingFiles(prev => [...prev, ...next]);
  };

  const updatePendingDesc = (id: string, desc: string) =>
    setPendingFiles(prev => prev.map(p => p.id === id ? { ...p, description: desc } : p));

  const removePendingFile = (id: string) =>
    setPendingFiles(prev => prev.filter(p => p.id !== id));

  const addFeature = async () => {
    if (!selected || !featureName.trim()) return;
    setFeatureSaving(true); setFeatureError("");
    const res = await fetch(`/api/projects/${selected.id}/features`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: featureName.trim(),
        description: featureDesc.trim(),
        priority: featurePriority,
        acceptance_criteria: featureAccept.trim(),
        workflow_id: featureWorkflowId ? Number(featureWorkflowId) : null,
      }),
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      setFeatureError(d.detail || "Lỗi tạo feature");
      setFeatureSaving(false);
      return;
    }
    const created: Feature = await res.json();

    // Upload pending files sequentially (small lists, simpler error reporting).
    const uploaded: FeatureFile[] = [...(created.files || [])];
    for (const p of pendingFiles) {
      const fd = new FormData();
      fd.append("file", p.file);
      fd.append("description", p.description);
      const up = await fetch(`/api/projects/${selected.id}/features/${created.id}/files`, {
        method: "POST",
        body: fd,
      });
      if (up.ok) uploaded.push(await up.json());
      else {
        const d = await up.json().catch(() => ({}));
        setFeatureError(`Upload "${p.file.name}" lỗi: ${d.detail || up.status}`);
      }
    }
    setFeatures(prev => [...prev, { ...created, files: uploaded }]);
    closeAddFeatureModal();
    setFeatureSaving(false);
  };

  const deleteFeature = async (id: number) => {
    if (!selected || !window.confirm("Xóa feature này (kèm files đính kèm)?")) return;
    const res = await fetch(`/api/projects/${selected.id}/features/${id}`, { method: "DELETE" });
    if (res.ok) setFeatures(prev => prev.filter(f => f.id !== id));
  };

  const deleteFeatureFile = async (featureId: number, fileId: number) => {
    if (!selected || !window.confirm("Xóa file đính kèm này?")) return;
    const res = await fetch(`/api/projects/${selected.id}/features/${featureId}/files/${fileId}`, { method: "DELETE" });
    if (res.ok) {
      setFeatures(prev => prev.map(f => f.id === featureId
        ? { ...f, files: (f.files || []).filter(x => x.id !== fileId) }
        : f));
    }
  };

  const updateFeatureStatus = async (id: number, status: string) => {
    if (!selected) return;
    const res = await fetch(`/api/projects/${selected.id}/features/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (res.ok) {
      const updated = await res.json();
      setFeatures(prev => prev.map(f => f.id === id ? updated : f));
    }
  };

  const markFeatureDone = (id: number) => updateFeatureStatus(id, "done");

  /** Gán workflow cho 1 task (null = bỏ chọn). */
  const setFeatureWorkflow = async (id: number, workflowId: number | null) => {
    if (!selected) return;
    const res = await fetch(`/api/projects/${selected.id}/features/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workflow_id: workflowId }),
    });
    if (res.ok) {
      const updated: Feature = await res.json();
      setFeatures(prev => prev.map(f => f.id === id ? updated : f));
    }
  };

  /**
   * Chạy workflow đã chọn cho task này. Backend chỉ GHI FILE .md cho bước đầu
   * tiên vào clients/<project>/_tasks/task<id>/ — không tự gọi Claude/opencode.
   * Bấm lại khi đang chạy sẽ tiếp tục run cũ, không tạo run trùng.
   */
  const runFeatureWorkflow = async (f: Feature) => {
    if (!selected || !f.workflow_id) return;
    setRunningFeatureId(f.id);
    setFeatureRunError(prev => ({ ...prev, [f.id]: "" }));
    try {
      const res = await fetch(`/api/workflows/${f.workflow_id}/run?task_id=${f.id}`, { method: "POST" });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setFeatureRunError(prev => ({ ...prev, [f.id]: d.detail || `Lỗi ${res.status}` }));
        return;
      }
      await loadFeatures(selected.id);
    } finally {
      setRunningFeatureId(null);
    }
  };

  const runStatusColor = (status: string) =>
    status === "done" ? "#4ade80"
    : status === "failed" ? "#f87171"
    : status === "cancelled" ? "#6b7280"
    : "#fbbf24";

  /** Huỷ lần chạy đang dở của 1 task. Hệ thống chỉ ngừng chờ — file task đã ghi
   *  vẫn còn trên đĩa, bấm ▶ lần nữa sẽ tạo run mới. */
  const cancelFeatureRun = async (f: Feature) => {
    const runId = f.latest_run?.id;
    if (!runId) return;
    if (!window.confirm(
      `Huỷ run #${runId} của task "${f.name}"?

` +
      "Các bước đang chờ bạn chạy sẽ bị bỏ qua. File task đã ghi vẫn giữ nguyên; " +
      "bấm ▶ Chạy workflow lần nữa sẽ tạo lần chạy mới."
    )) return;
    setCancellingRun(runId);
    setFeatureRunError(prev => ({ ...prev, [f.id]: "" }));
    try {
      const res = await fetch(`/api/workflows/runs/${runId}/cancel`, { method: "POST" });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setFeatureRunError(prev => ({ ...prev, [f.id]: d.detail || `Lỗi ${res.status}` }));
        return;
      }
      if (selected) await loadFeatures(selected.id);
    } finally {
      setCancellingRun(null);
    }
  };

  // Người dùng chạy Claude ngoài terminal rồi sửa file task → backend poll file
  // mỗi 5s. Khi còn task đang chạy thì tab Features cũng nạp lại để badge tiến độ
  // không đứng yên; hết task chạy là dừng poll.
  const hasRunningWorkflow = features.some(f => f.latest_run?.status === "running");
  useEffect(() => {
    if (!selected || activeTab !== "features" || !hasRunningWorkflow) return;
    const id = setInterval(() => loadFeatures(selected.id), 6000);
    return () => clearInterval(id);
  }, [selected, activeTab, hasRunningWorkflow, loadFeatures]);

  const startEditField = (field: EditableField, current: string) => {
    setEditingField(field);
    setEditDraft(current || "");
  };

  const cancelEditField = () => {
    setEditingField(null);
    setEditDraft("");
  };

  const saveEditField = async () => {
    if (!selected || !editingField) return;
    setEditSaving(true);
    const body: Record<string, string> = {};
    if (editingField === "name")       body.name       = editDraft;
    if (editingField === "backend")    body.backend    = editDraft;
    if (editingField === "frontend")   body.frontend   = editDraft;
    if (editingField === "output_dir") body.output_dir = editDraft;
    if (editingField === "profile")    body.profile    = editDraft;

    const res = await fetch(`/api/projects/${selected.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.ok) {
      const updated: Project = await res.json();
      setSelected(prev => prev ? { ...prev, ...updated } : prev);
      refetch();
      cancelEditField();
    }
    setEditSaving(false);
  };

  const loadDocs = useCallback(async (id: string) => {
    const res = await fetch(`/api/projects/${id}/docs`);
    if (res.ok) setDocFiles(await res.json());
  }, []);

  const loadDocContent = async (id: string, path: string, source: string = "code") => {
    setDocLoading(true);
    setSelectedDoc(path);
    const res = await fetch(`/api/projects/${id}/docs/content?path=${encodeURIComponent(path)}&source=${source}`);
    if (res.ok) { const d = await res.json(); setDocContent(d.content); }
    setDocLoading(false);
  };

  const availableKeys = VALID_KEYS.filter(k => !settingsAgents.find(a => a.key === k));

  const createProject = async () => {
    if (!npFolderName.trim()) return;
    setNpSaving(true); setNpError("");
    const res = await fetch("/api/projects/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        folder_name: npFolderName.trim(),
        profile:     npProfile,
        default_tool: npTool,
        backend:     npBackend.trim(),
        frontend:    npFrontend.trim(),
      }),
    });
    if (res.ok) {
      setShowNewProject(false);
      setNpFolderName(""); setNpBackend(""); setNpFrontend("");
      await refetch();
    } else {
      const d = await res.json().catch(() => ({}));
      setNpError(d.detail || "Lỗi tạo project");
    }
    setNpSaving(false);
  };

  const handleDeleteProject = async () => {
    if (!selected) return;
    setDeleteProjecting(true);
    const res = await fetch(`/api/projects/${selected.id}`, { method: "DELETE" });
    if (res.ok) {
      setDeleteStep("done");
      await refetch();
      setTimeout(() => {
        setSelected(null);
        setShowDeleteProject(false);
        setDeleteStep("confirm");
      }, 1500);
    }
    setDeleteProjecting(false);
  };

  if (loading) return <div className="state">Loading projects...</div>;
  if (error)   return <div className="state err">{error}</div>;

  return (
    <div className="projects-page">
      <div className="page-header">
        <h2>Projects</h2>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn-primary" onClick={() => { setShowNewProject(v => !v); setNpError(""); }}>+ New Project</button>
          <button className="btn-muted"   onClick={refetch}>↻ Refresh</button>
        </div>
      </div>

      {showNewProject && (
        <div className="card" style={{ marginBottom: 20 }}>
          <h4 style={{ marginTop: 0, marginBottom: 16 }}>Tạo Project mới</h4>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Tên folder (slug) *</label>
              <input className="setting-input" placeholder="vd: my_project"
                value={npFolderName} onChange={e => setNpFolderName(e.target.value.toLowerCase().replace(/\s+/g, "_"))}
                onKeyDown={e => e.key === "Enter" && createProject()} />
              <div style={{ fontSize: 11, color: "#4b5563", marginTop: 4 }}>
                → clients/<strong>{npFolderName || "folder_name"}</strong>/
              </div>
            </div>
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Profile</label>
              <select className="setting-select" value={npProfile} onChange={e => setNpProfile(e.target.value)}>
                {profilesList.length === 0 ? (
                  <>
                    <option value="fullstack">fullstack — PM+Scrum+Analyst+BE1+BE2+FE1+FE2+Leader</option>
                    <option value="dual_fullstack">dual_fullstack — PM+Scrum+Analyst+FS1+FS2+Leader</option>
                    <option value="backend_only">backend_only — PM+Scrum+Analyst+BE1+BE2+Leader</option>
                  </>
                ) : (
                  profilesList.map(p => (
                    <option key={p.name} value={p.name}>
                      {p.name} — {p.agents.map(a => a.toUpperCase()).join("+")}
                      {p.stages_disabled.length > 0 ? ` · skip:${p.stages_disabled.join(",")}` : ""}
                    </option>
                  ))
                )}
              </select>
              {profilesList.find(p => p.name === npProfile)?.label && (
                <div style={{ fontSize: 11, color: "#6b7280", marginTop: 4 }}>
                  {profilesList.find(p => p.name === npProfile)?.label}
                </div>
              )}
            </div>
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Default tool</label>
              <select className="setting-select" value={npTool} onChange={e => setNpTool(e.target.value)}>
                <option value="opencode">opencode</option>
              </select>
              <div style={{ fontSize: 11, color: "#6b7280", marginTop: 4 }}>
                Claude Code không dùng trong pipeline tự động
              </div>
            </div>
            <div />
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Backend tech stack</label>
              <input className="setting-input" placeholder="Python FastAPI + SQLModel + SQLite"
                value={npBackend} onChange={e => setNpBackend(e.target.value)} />
            </div>
            {npProfile !== "backend_only" && (
              <div>
                <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Frontend tech stack</label>
                <input className="setting-input" placeholder="React + TypeScript + Vite + TailwindCSS"
                  value={npFrontend} onChange={e => setNpFrontend(e.target.value)} />
              </div>
            )}
          </div>
          {npError && <p style={{ color: "#ef4444", fontSize: 13, marginTop: 8 }}>{npError}</p>}
          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <button className="btn-primary" disabled={npSaving || !npFolderName.trim()} onClick={createProject}>
              {npSaving ? "Đang tạo..." : "Tạo Project"}
            </button>
            <button className="btn-muted" onClick={() => { setShowNewProject(false); setNpError(""); }}>Huỷ</button>
          </div>
        </div>
      )}

      {selected && (
        <div className="card" style={{ marginBottom: 20 }}>
          {/* Header */}
          <div className="project-detail-header">
            <div style={{ minWidth: 0, flex: 1 }}>
              {editingField === "name" ? (
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <input className="setting-input" value={editDraft} autoFocus
                    onChange={e => setEditDraft(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === "Enter") saveEditField();
                      if (e.key === "Escape") cancelEditField();
                    }}
                    style={{ width: 320, fontSize: 18, fontWeight: 600, boxSizing: "border-box" }} />
                  <button onClick={saveEditField} disabled={editSaving}
                    style={{ background: "#14532d", border: "none", color: "#86efac", cursor: "pointer", fontSize: 14, padding: "4px 10px", borderRadius: 4 }}
                    title="Lưu (Enter)">✓</button>
                  <button onClick={cancelEditField} disabled={editSaving}
                    style={{ background: "#1e293b", border: "1px solid #374151", color: "#9ca3af", cursor: "pointer", fontSize: 14, padding: "4px 10px", borderRadius: 4 }}
                    title="Huỷ (Esc)">✕</button>
                </div>
              ) : (
                <h3 style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                  {selected.name}
                  <button onClick={() => startEditField("name", selected.name)}
                    style={{ background: "none", border: "none", color: "#6b7280", cursor: "pointer", fontSize: 13, padding: 0 }}
                    title="Đổi tên hiển thị">✏️</button>
                </h3>
              )}
              <div className="project-meta-links">
                <span className="project-link" style={{ background: "#172554", borderColor: "#3b82f655" }}
                  title="Folder slug — không sửa được">
                  <span className="project-link-icon">&#x1f4c1;</span> clients/{selected.id}
                </span>

                {/* Profile */}
                {editingField === "profile" ? (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                    <select className="setting-select" value={editDraft}
                      onChange={e => setEditDraft(e.target.value)}
                      style={{ width: 220, fontSize: 11, padding: "2px 6px", boxSizing: "border-box" }}>
                      {profilesList.length === 0 ? (
                        <>
                          <option value="fullstack">fullstack</option>
                          <option value="dual_fullstack">dual_fullstack</option>
                          <option value="backend_only">backend_only</option>
                        </>
                      ) : profilesList.map(p => (
                        <option key={p.name} value={p.name}>{p.name}</option>
                      ))}
                    </select>
                    <button onClick={saveEditField} disabled={editSaving}
                      style={{ background: "none", border: "none", color: "#86efac", cursor: "pointer", fontSize: 13 }}
                      title="Lưu">✓</button>
                    <button onClick={cancelEditField} disabled={editSaving}
                      style={{ background: "none", border: "none", color: "#9ca3af", cursor: "pointer", fontSize: 13 }}
                      title="Huỷ">✕</button>
                  </span>
                ) : (
                  <span className="project-link"
                    style={{ background: "#172554", borderColor: "#3b82f655", cursor: "pointer" }}
                    onClick={() => startEditField("profile", selected.profile || "")}
                    title="Click để đổi profile">
                    🧩 {selected.profile || "—"} <span style={{ color: "#6b7280", fontSize: 9 }}>✏️</span>
                  </span>
                )}

                {/* Backend */}
                {editingField === "backend" ? (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                    <input className="setting-input" value={editDraft} autoFocus
                      onChange={e => setEditDraft(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === "Enter") saveEditField();
                        if (e.key === "Escape") cancelEditField();
                      }}
                      style={{ width: 280, fontSize: 11, padding: "2px 6px", boxSizing: "border-box" }} />
                    <button onClick={saveEditField} disabled={editSaving}
                      style={{ background: "none", border: "none", color: "#86efac", cursor: "pointer", fontSize: 13 }}>✓</button>
                    <button onClick={cancelEditField} disabled={editSaving}
                      style={{ background: "none", border: "none", color: "#9ca3af", cursor: "pointer", fontSize: 13 }}>✕</button>
                  </span>
                ) : (
                  <span className="project-link"
                    style={{ background: "#1a2e1a", borderColor: "#22c55e55", cursor: "pointer" }}
                    onClick={() => startEditField("backend", selected.tech_stack?.backend || "")}
                    title="Click để sửa BE stack">
                    BE: {selected.tech_stack?.backend || "—"} <span style={{ color: "#6b7280", fontSize: 9 }}>✏️</span>
                  </span>
                )}

                {/* Frontend */}
                {editingField === "frontend" ? (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                    <input className="setting-input" value={editDraft} autoFocus
                      onChange={e => setEditDraft(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === "Enter") saveEditField();
                        if (e.key === "Escape") cancelEditField();
                      }}
                      style={{ width: 280, fontSize: 11, padding: "2px 6px", boxSizing: "border-box" }} />
                    <button onClick={saveEditField} disabled={editSaving}
                      style={{ background: "none", border: "none", color: "#86efac", cursor: "pointer", fontSize: 13 }}>✓</button>
                    <button onClick={cancelEditField} disabled={editSaving}
                      style={{ background: "none", border: "none", color: "#9ca3af", cursor: "pointer", fontSize: 13 }}>✕</button>
                  </span>
                ) : (
                  <span className="project-link"
                    style={{ background: "#1e1a2e", borderColor: "#a855f755", cursor: "pointer" }}
                    onClick={() => startEditField("frontend", selected.tech_stack?.frontend || "")}
                    title="Click để sửa FE stack">
                    FE: {selected.tech_stack?.frontend || "—"} <span style={{ color: "#6b7280", fontSize: 9 }}>✏️</span>
                  </span>
                )}

                {/* Output dir */}
                {editingField === "output_dir" ? (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                    <input className="setting-input" value={editDraft} autoFocus
                      onChange={e => setEditDraft(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === "Enter") saveEditField();
                        if (e.key === "Escape") cancelEditField();
                      }}
                      style={{ width: 320, fontSize: 11, padding: "2px 6px", boxSizing: "border-box" }} />
                    <button onClick={saveEditField} disabled={editSaving}
                      style={{ background: "none", border: "none", color: "#86efac", cursor: "pointer", fontSize: 13 }}>✓</button>
                    <button onClick={cancelEditField} disabled={editSaving}
                      style={{ background: "none", border: "none", color: "#9ca3af", cursor: "pointer", fontSize: 13 }}>✕</button>
                  </span>
                ) : (
                  <span className="project-link"
                    style={{ background: "#1a1a1a", borderColor: "#374151", fontSize: 10, cursor: "pointer" }}
                    onClick={() => startEditField("output_dir", selected.output_dir)}
                    title="Click để sửa output directory">
                    📂 {selected.output_dir} <span style={{ color: "#6b7280", fontSize: 9 }}>✏️</span>
                  </span>
                )}
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              {(() => {
                const active = queue.filter(j => j.status === "queued" || j.status === "running");
                const running = active.some(j => j.status === "running");
                return (
                  <>
                    {active.length > 0 && (
                      <span style={{ fontSize: 11, color: running ? "#22c55e" : "#eab308" }}>
                        {running ? "🔄 đang chạy" : `⏳ chờ (${active.length})`}
                      </span>
                    )}
                    <button className="btn-primary" style={{ fontSize: 13, padding: "6px 16px" }}
                      disabled={triggering} onClick={triggerRun}
                      title="Xếp project vào hàng đợi; worker.py chạy pipeline tuần tự">
                      {triggering ? "Đang xếp..." : "▶ Run"}
                    </button>
                  </>
                );
              })()}
              <button className="btn-danger" style={{ fontSize: 12, padding: "4px 10px" }}
                onClick={() => { setShowDeleteProject(true); setDeleteStep("confirm"); }}>
                🗑 Delete Project
              </button>
              <button className="btn-muted" onClick={() => { setSelected(null); setShowAddAgent(false); setPrdEditing(false); }}>Close</button>
            </div>
          </div>

          {/* Tabs */}
          <div style={{ display: "flex", gap: 4, marginTop: 16, borderBottom: "1px solid #1e293b" }}>
            {(["features","workflows","agents","prd","runs","docs"] as const).map(tab => (
              <button key={tab}
                onClick={() => {
                  setActiveTab(tab as typeof activeTab);
                  if (tab === "prd" && prdContent === null) loadPrd(selected.id);
                  if (tab === "docs" && docFiles.length === 0) loadDocs(selected.id);
                  if (tab === "features" && !featuresLoaded) loadFeatures(selected.id);
                }}
                style={{ padding: "6px 16px", background: activeTab === tab ? "#1e293b" : "none", border: "none",
                  borderRadius: "6px 6px 0 0", color: activeTab === tab ? "#f1f5f9" : "#6b7280",
                  cursor: "pointer", fontSize: 13, fontWeight: activeTab === tab ? 600 : 400 }}>
                {tab === "features" ? `Features (${features.length})`
                  : tab === "workflows" ? `Workflows (${projectWorkflows.length})`
                  : tab === "agents" ? `Agents (${settingsAgents.length})`
                  : tab === "prd" ? "PRD"
                  : tab === "runs" ? `Runs (${projRuns.length})`
                  : `Docs${docFiles.length > 0 ? ` (${docFiles.length})` : ""}`}
              </button>
            ))}
          </div>

          {/* Workflows tab — danh sách workflow của riêng project này */}
          {activeTab === "workflows" && (
            <ProjectWorkflows
              clientFolder={selected.id}
              onChanged={() => { refetchProjectWorkflows(); loadFeatures(selected.id); }}
            />
          )}

          {/* Features tab */}
          {activeTab === "features" && (
            <div style={{ marginTop: 16 }}>
              <div className="task-manager-header">
                <h4>Features / Ý tưởng ({features.length})</h4>
                <button className="btn-primary" style={{ fontSize: 12, padding: "4px 10px" }}
                  onClick={() => { resetFeatureForm(); setShowAddFeature(true); }}>
                  + Add Feature
                </button>
              </div>

              {features.length === 0 ? (
                <p style={{ color: "#6b7280", fontSize: 13, marginTop: 12 }}>
                  Chưa có feature nào. Bấm "+ Add Feature" để thêm ý tưởng.
                </p>
              ) : (
                <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
                  {features.map(f => {
                    const statusColor = f.status === "done" ? "#14532d" : f.status === "in_progress" ? "#92400e" : f.status === "todo" ? "#1e293b" : "#7f1d1d";
                    const statusLabel = f.status === "done" ? "✅ done" : f.status === "in_progress" ? "⏳ running" : f.status === "todo" ? "📋 todo" : "❌ failed";
                    const priorityColor = f.priority === "high" ? "#ef4444" : f.priority === "medium" ? "#f59e0b" : "#6b7280";
                    return (
                      <div key={f.id} style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, padding: "10px 14px", display: "flex", alignItems: "flex-start", gap: 10 }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                            <span style={{ fontWeight: 600, fontSize: 13, color: "#f1f5f9" }}>{f.name}</span>
                            <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 99, background: statusColor, color: "#e2e8f0" }}>{statusLabel}</span>
                            <span style={{ fontSize: 10, color: priorityColor }}>{f.priority}</span>
                            {(f.files?.length ?? 0) > 0 && (
                              <span style={{ fontSize: 10, color: "#60a5fa" }} title="Số file đính kèm">
                                📎 {f.files!.length}
                              </span>
                            )}
                          </div>
                          {f.description && (
                            <p style={{ margin: "4px 0 0", fontSize: 12, color: "#9ca3af", lineHeight: 1.5 }}>{f.description}</p>
                          )}
                          {f.acceptance_criteria && (
                            <pre style={{
                              margin: "6px 0 0", fontSize: 11, color: "#cbd5e1", lineHeight: 1.5,
                              background: "#0b1220", border: "1px solid #1e293b", borderRadius: 6,
                              padding: "6px 8px", whiteSpace: "pre-wrap", fontFamily: "inherit",
                            }}>{f.acceptance_criteria}</pre>
                          )}
                          {(f.files?.length ?? 0) > 0 && (
                            <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 4 }}>
                              {f.files!.map(file => (
                                <div key={file.id} style={{
                                  display: "flex", alignItems: "center", gap: 8,
                                  fontSize: 11, color: "#cbd5e1",
                                  background: "#0b1220", border: "1px solid #1e293b",
                                  borderRadius: 6, padding: "4px 8px",
                                }}>
                                  <span style={{ flexShrink: 0 }}>📄</span>
                                  <a
                                    href={`/api/projects/${selected.id}/features/${f.id}/files/${file.id}/download`}
                                    target="_blank" rel="noreferrer"
                                    style={{ color: "#93c5fd", textDecoration: "none", flexShrink: 0 }}
                                    title="Tải về"
                                  >{file.original_filename}</a>
                                  <span style={{ color: "#6b7280", fontSize: 10, flexShrink: 0 }}>
                                    {(file.size / 1024).toFixed(1)} KB
                                  </span>
                                  {file.description && (
                                    <span style={{ color: "#9ca3af", fontStyle: "italic", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                      — {file.description}
                                    </span>
                                  )}
                                  <button onClick={() => deleteFeatureFile(f.id, file.id)}
                                    style={{ marginLeft: "auto", background: "none", border: "none", color: "#ef4444", cursor: "pointer", fontSize: 12, padding: "0 4px" }}
                                    title="Xóa file">✕</button>
                                </div>
                              ))}
                            </div>
                          )}

                          {/* Workflow của task: chọn quy trình rồi chạy */}
                          <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                            <span style={{ fontSize: 11, color: "#6b7280" }}>Workflow</span>
                            <select className="setting-select"
                              style={{ width: 210, fontSize: 11, padding: "2px 6px" }}
                              value={f.workflow_id ?? ""}
                              onChange={e => setFeatureWorkflow(f.id, e.target.value ? Number(e.target.value) : null)}
                              title="Quy trình task này chạy theo — quản lý ở tab Workflows của project">
                              <option value="">— chưa chọn —</option>
                              {projectWorkflows.map(w => (
                                <option key={w.id} value={w.id}>{w.name}{w.is_active ? "" : " (tắt)"}</option>
                              ))}
                            </select>
                            <button
                              disabled={!f.workflow_id || runningFeatureId === f.id}
                              onClick={() => runFeatureWorkflow(f)}
                              style={{
                                background: f.workflow_id ? "#1e3a8a" : "#1e293b",
                                border: "1px solid #334155",
                                color: f.workflow_id ? "#bfdbfe" : "#4b5563",
                                cursor: f.workflow_id ? "pointer" : "not-allowed",
                                fontSize: 11, padding: "3px 8px", borderRadius: 4,
                              }}
                              title={f.workflow_id
                                ? "Ghi file task cho bước kế tiếp — bạn tự chạy Claude trong terminal"
                                : "Chọn workflow trước"}>
                              {runningFeatureId === f.id ? "Đang xử lý..." : "▶ Chạy workflow"}
                            </button>
                            {f.latest_run && (
                              <button
                                onClick={() => setRunDetail({ workflowId: f.workflow_id ?? null, runId: f.latest_run!.id })}
                                title="Mở màn hình chạy: lệnh cần chạy, file task và tiến độ từng bước"
                                style={{
                                  background: "none", border: "none", padding: 0, cursor: "pointer",
                                  fontSize: 11, color: runStatusColor(f.latest_run.status),
                                  textDecoration: "underline", textDecorationStyle: "dotted",
                                }}>
                                run #{f.latest_run.id} · {f.latest_run.done_steps}/{f.latest_run.total_steps} bước · {f.latest_run.status} ↗
                              </button>
                            )}
                            {f.latest_run?.status === "running" && (
                              <button
                                disabled={cancellingRun === f.latest_run.id}
                                onClick={() => cancelFeatureRun(f)}
                                title="Ngừng chờ lần chạy này — các bước đang chờ bạn sẽ bị bỏ qua"
                                style={{
                                  background: "#3f1d1d", border: "1px solid #7f1d1d", color: "#fca5a5",
                                  cursor: cancellingRun === f.latest_run.id ? "wait" : "pointer",
                                  fontSize: 11, padding: "3px 8px", borderRadius: 4,
                                }}>
                                {cancellingRun === f.latest_run.id ? "Đang huỷ..." : "⛔ Huỷ"}
                              </button>
                            )}
                            {projectWorkflows.length === 0 && (
                              <button onClick={() => setActiveTab("workflows")}
                                style={{ background: "none", border: "none", color: "#60a5fa", cursor: "pointer", fontSize: 11, padding: 0 }}>
                                Chưa có workflow — tạo ở tab Workflows →
                              </button>
                            )}
                            {featureRunError[f.id] && (
                              <span style={{ fontSize: 11, color: "#f87171" }}>{featureRunError[f.id]}</span>
                            )}
                          </div>
                        </div>
                        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                          {f.status !== "done" ? (
                            <button onClick={() => markFeatureDone(f.id)}
                              style={{ background: "#14532d", border: "none", color: "#86efac", cursor: "pointer", fontSize: 11, padding: "3px 8px", borderRadius: 4 }}
                              title="Đánh dấu hoàn thành">✓ Done</button>
                          ) : (
                            <button onClick={() => updateFeatureStatus(f.id, "todo")}
                              style={{ background: "#1e293b", border: "1px solid #374151", color: "#9ca3af", cursor: "pointer", fontSize: 11, padding: "3px 8px", borderRadius: 4 }}
                              title="Reopen">↩ Reopen</button>
                          )}
                          {f.status !== "done" && (
                            <button onClick={() => deleteFeature(f.id)}
                              style={{ background: "none", border: "none", color: "#ef4444", cursor: "pointer", fontSize: 14, padding: "0 4px" }}
                              title="Xóa">✕</button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {showAddFeature && (
                <div
                  onClick={e => { if (e.target === e.currentTarget && !featureSaving) closeAddFeatureModal(); }}
                  style={{
                    position: "fixed", inset: 0, background: "rgba(2,6,23,0.75)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    padding: 16, zIndex: 1000,
                  }}
                >
                  <div style={{
                    background: "#0f172a", border: "1px solid #1e293b", borderRadius: 12,
                    width: "min(720px, 100%)", maxHeight: "calc(100vh - 32px)",
                    display: "flex", flexDirection: "column",
                    boxShadow: "0 20px 50px rgba(0,0,0,0.6)",
                  }}>
                    <div style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      padding: "14px 20px", borderBottom: "1px solid #1e293b", flexShrink: 0,
                    }}>
                      <h3 style={{ margin: 0, fontSize: 16, color: "#f1f5f9" }}>✨ Thêm Feature mới</h3>
                      <button onClick={closeAddFeatureModal} disabled={featureSaving}
                        style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer", fontSize: 20, lineHeight: 1, padding: 0 }}
                        title="Đóng">✕</button>
                    </div>

                    {/* Scrollable body */}
                    <div style={{
                      padding: 20, display: "flex", flexDirection: "column", gap: 14,
                      overflowY: "auto", overflowX: "hidden", flex: 1, minHeight: 0,
                    }}>

                    {/* Row 1: name + priority */}
                    <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 140px", gap: 10 }}>
                      <div style={{ minWidth: 0 }}>
                        <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Tên feature *</label>
                        <input className="setting-input" placeholder="VD: Chức năng đăng nhập bằng Google"
                          value={featureName} onChange={e => setFeatureName(e.target.value)} autoFocus
                          style={{ width: "100%", boxSizing: "border-box" }} />
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Priority</label>
                        <select className="setting-select" value={featurePriority}
                          onChange={e => setFeaturePriority(e.target.value)}
                          style={{ width: "100%", boxSizing: "border-box" }}>
                          <option value="high">🔴 High</option>
                          <option value="medium">🟡 Medium</option>
                          <option value="low">⚪ Low</option>
                        </select>
                      </div>
                    </div>

                    {/* Workflow áp dụng cho task */}
                    <div>
                      <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>
                        Workflow
                        <span style={{ fontWeight: 400, color: "#6b7280", marginLeft: 6, fontSize: 11 }}>
                          (quy trình task này chạy theo — có thể đổi sau)
                        </span>
                      </label>
                      <select className="setting-select" value={featureWorkflowId}
                        onChange={e => setFeatureWorkflowId(e.target.value)}
                        style={{ width: "100%", boxSizing: "border-box" }}>
                        <option value="">— chưa chọn —</option>
                        {projectWorkflows.map(w => (
                          <option key={w.id} value={w.id}>{w.name}{w.is_active ? "" : " (tắt)"}</option>
                        ))}
                      </select>
                      {projectWorkflows.length === 0 && (
                        <p style={{ fontSize: 11, color: "#6b7280", margin: "4px 0 0" }}>
                          Project chưa có workflow nào — tạo ở tab <b>Workflows</b>.
                        </p>
                      )}
                    </div>

                    {/* Description */}
                    <div>
                      <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Mô tả</label>
                      <textarea className="setting-input" placeholder="Feature này làm gì, ai dùng, dùng khi nào..."
                        value={featureDesc} onChange={e => setFeatureDesc(e.target.value)}
                        rows={3} style={{ resize: "vertical", fontFamily: "inherit", width: "100%", boxSizing: "border-box" }} />
                    </div>

                    {/* Acceptance criteria */}
                    <div>
                      <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>
                        Acceptance criteria / Checklist
                        <span style={{ fontWeight: 400, color: "#6b7280", marginLeft: 6, fontSize: 11 }}>
                          (mỗi dòng 1 ý — viết "- [ ] ..." hoặc gạch đầu dòng tuỳ ý)
                        </span>
                      </label>
                      <textarea className="setting-input"
                        placeholder={"- [ ] User bấm nút \"Đăng nhập với Google\"\n- [ ] Lưu token vào session\n- [ ] Redirect về dashboard"}
                        value={featureAccept} onChange={e => setFeatureAccept(e.target.value)}
                        rows={4} style={{ resize: "vertical", fontFamily: "monospace", fontSize: 12, width: "100%", boxSizing: "border-box" }} />
                    </div>

                    {/* File attachments */}
                    <div>
                      <label className="setting-label" style={{ display: "block", marginBottom: 6 }}>
                        File đính kèm
                        <span style={{ fontWeight: 400, color: "#6b7280", marginLeft: 6, fontSize: 11 }}>
                          (mockup, spec, screenshot... — tối đa 20 MB/file)
                        </span>
                      </label>
                      <label style={{
                        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
                        gap: 4, padding: "16px 12px", border: "1px dashed #334155", borderRadius: 8,
                        background: "#0b1220", cursor: "pointer", color: "#94a3b8", fontSize: 12,
                      }}>
                        <span style={{ fontSize: 22 }}>📎</span>
                        <span>Bấm để chọn file (nhiều file cùng lúc)</span>
                        <input type="file" multiple style={{ display: "none" }}
                          onChange={e => { addPendingFiles(e.target.files); e.target.value = ""; }} />
                      </label>
                      {pendingFiles.length > 0 && (
                        <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
                          {pendingFiles.map(p => (
                            <div key={p.id} style={{
                              display: "grid", gridTemplateColumns: "minmax(0, 180px) minmax(0, 1fr) auto",
                              alignItems: "center", gap: 8,
                              background: "#0b1220", border: "1px solid #1e293b",
                              borderRadius: 6, padding: "6px 10px",
                            }}>
                              <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#cbd5e1", minWidth: 0 }} title={p.file.name}>
                                <span style={{ flexShrink: 0 }}>📄</span>
                                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                                  {p.file.name}
                                </span>
                                <span style={{ color: "#6b7280", fontSize: 10, flexShrink: 0 }}>
                                  {(p.file.size / 1024).toFixed(1)} KB
                                </span>
                              </div>
                              <input className="setting-input" placeholder="Mô tả file (vd: mockup trang login)"
                                value={p.description} onChange={e => updatePendingDesc(p.id, e.target.value)}
                                style={{ fontSize: 12, minWidth: 0, width: "100%", boxSizing: "border-box" }} />
                              <button onClick={() => removePendingFile(p.id)}
                                style={{ background: "none", border: "none", color: "#ef4444", cursor: "pointer", fontSize: 14 }}
                                title="Bỏ file này">✕</button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {featureError && (
                      <p style={{ color: "#ef4444", fontSize: 12, margin: 0 }}>{featureError}</p>
                    )}

                    </div>
                    {/* /scrollable body */}

                    <div style={{
                      display: "flex", gap: 8, justifyContent: "flex-end",
                      borderTop: "1px solid #1e293b", padding: "12px 20px", flexShrink: 0,
                    }}>
                      <button className="btn-muted" onClick={closeAddFeatureModal} disabled={featureSaving}>Huỷ</button>
                      <button className="btn-primary" disabled={featureSaving || !featureName.trim()} onClick={addFeature}>
                        {featureSaving
                          ? (pendingFiles.length > 0 ? "Đang upload..." : "Đang lưu...")
                          : `+ Thêm feature${pendingFiles.length > 0 ? ` (& ${pendingFiles.length} file)` : ""}`}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Agents tab */}
          {activeTab === "agents" && (
            <div style={{ marginTop: 16 }}>
              <div className="task-manager-header">
                <h4>Agents ({settingsAgents.length})</h4>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span style={{ fontSize: 11, color: "#4b5563" }}>
                    <code style={{ background: "#1e293b", padding: "2px 6px", borderRadius: 4 }}>
                      clients/{selected.id}/settings.toml
                    </code>
                  </span>
                  {availableKeys.length > 0 && (
                    <button className="btn-primary" style={{ fontSize: 12, padding: "4px 10px" }}
                      onClick={() => { setAddKey(availableKeys[0]); setShowAddAgent(v => !v); }}>
                      + Add Agent
                    </button>
                  )}
                </div>
              </div>

              {showAddAgent && (
                <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, padding: 12, marginTop: 8, display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
                  <div>
                    <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Key</label>
                    <select className="setting-select" value={addKey} onChange={e => setAddKey(e.target.value)}>
                      {availableKeys.map(k => <option key={k} value={k}>{k}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Tool</label>
                    <select className="setting-select" value={addTool}
                      onChange={e => { setAddTool(e.target.value); setAddModel(DEFAULT_MODELS[e.target.value] ?? ""); }}>
                      <option value="opencode">opencode</option>
                    </select>
                  </div>
                  <div>
                    <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Model</label>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      <select className="setting-select" style={{ width: 260 }}
                        value={OPENCODE_GO_MODELS.find(m => m.value === addModel) ? addModel : "other"}
                        onChange={e => { if (e.target.value !== "other") setAddModel(e.target.value); else setAddModel(""); }}>
                        {OPENCODE_GO_MODELS.map(m => (
                          <option key={m.value} value={m.value}>{m.label}</option>
                        ))}
                      </select>
                      {(!OPENCODE_GO_MODELS.find(m => m.value === addModel && m.value !== "other") || addModel === "") && (
                        <input className="setting-input" style={{ width: 260 }} value={addModel}
                          onChange={e => setAddModel(e.target.value)} placeholder="vd: opencode-go/model-name" />
                      )}
                    </div>
                  </div>
                  <button className="btn-primary" disabled={addSaving || !addModel.trim()} onClick={handleAddAgent}>
                    {addSaving ? "Saving..." : "Add"}
                  </button>
                  <button className="btn-muted" onClick={() => setShowAddAgent(false)}>Cancel</button>
                </div>
              )}

              {settingsAgents.length === 0
                ? <p style={{ color: "#6b7280", fontSize: 13, marginTop: 8 }}>No agents in settings.toml</p>
                : (
                  <div className="agent-chip-list" style={{ marginTop: 8 }}>
                    {settingsAgents.map(a => (
                      <div key={a.key} className="agent-chip" style={{ position: "relative", paddingRight: 28 }}>
                        <span>{a.name}</span>
                        <span className="agent-chip-role">{a.key}</span>
                        <span style={{ fontSize: 10, color: "#6b7280" }}>{a.tool} · {a.model}</span>
                        <button onClick={() => confirmRemoveAgent(a.key)}
                          style={{ position: "absolute", right: 6, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: "#ef4444", cursor: "pointer", fontSize: 14, lineHeight: 1 }}
                          title="Remove">✕</button>
                      </div>
                    ))}
                  </div>
                )
              }
            </div>
          )}

          {/* PRD tab */}
          {activeTab === "prd" && (
            <div style={{ marginTop: 16 }}>
              <div className="task-manager-header">
                <h4>PRD — <code style={{ fontSize: 12, background: "#1e293b", padding: "2px 6px", borderRadius: 4 }}>clients/{selected.id}/prd.md</code></h4>
                <div style={{ display: "flex", gap: 8 }}>
                  {prdExists && !prdEditing && (
                    <>
                      <button className="btn-primary" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => { setPrdDraft(prdContent ?? ""); setPrdEditing(true); }}>✏️ Edit</button>
                      <button className="btn-danger"  style={{ fontSize: 12, padding: "4px 10px" }} onClick={deletePrd}>Delete</button>
                    </>
                  )}
                  {prdEditing && (
                    <>
                      <button className="btn-primary" style={{ fontSize: 12, padding: "4px 10px" }} disabled={prdSaving} onClick={savePrd}>{prdSaving ? "Saving..." : "💾 Save"}</button>
                      <button className="btn-muted"   style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => setPrdEditing(false)}>Cancel</button>
                    </>
                  )}
                  {!prdExists && !prdEditing && (
                    <button className="btn-primary" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => { setPrdDraft("# PRD\n\n## Tổng quan\n\n"); setPrdEditing(true); }}>+ Tạo PRD</button>
                  )}
                </div>
              </div>
              {prdEditing ? (
                <textarea value={prdDraft} onChange={e => setPrdDraft(e.target.value)}
                  style={{ width: "100%", minHeight: 500, marginTop: 12, background: "#0f172a", color: "#e2e8f0", border: "1px solid #1e293b", borderRadius: 8, padding: 16, fontFamily: "monospace", fontSize: 13, lineHeight: 1.6, resize: "vertical", boxSizing: "border-box" }} />
              ) : prdExists && prdContent ? (
                <pre style={{ marginTop: 12, background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, padding: 16, fontFamily: "monospace", fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-word", color: "#e2e8f0", maxHeight: 600, overflowY: "auto" }}>
                  {prdContent}
                </pre>
              ) : (
                <p style={{ color: "#6b7280", fontSize: 13, marginTop: 12 }}>Chưa có prd.md. Bấm "+ Tạo PRD" để bắt đầu.</p>
              )}
            </div>
          )}

          {/* Runs tab */}
          {activeTab === "runs" && (
            <div style={{ marginTop: 16 }}>
              <div className="task-manager-header">
                <h4>Orchestrator Runs ({projRuns.length})</h4>
                <span style={{ fontSize: 11, color: "#6b7280" }}>Dùng nút ▶ Run ở góc trên để chạy</span>
              </div>
              {queue.length > 0 && (
                <div className="history-list" style={{ marginBottom: 12 }}>
                  {queue.map(j => (
                    <div key={`job-${j.id}`} className="history-row">
                      <span className="history-id">job#{j.id}</span>
                      <span className="history-meta" style={{ flex: 1 }}>
                        {j.error ? <span style={{ color: "#f87171" }} title={j.error}>{j.error.slice(0, 60)}</span> : "queue"}
                      </span>
                      <span className={`project-status-badge status-${j.status === "running" ? "active" : j.status === "done" ? "completed" : j.status === "failed" ? "archived" : "paused"}`}>
                        {j.status}
                      </span>
                      {j.status === "queued" && (
                        <button className="btn-muted" style={{ fontSize: 11, padding: "2px 8px", marginLeft: 8 }}
                          onClick={() => cancelJob(j.id)}>Huỷ</button>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {projRuns.length === 0
                ? <p style={{ color: "#6b7280", fontSize: 12 }}>No runs yet.</p>
                : (
                  <div className="history-list">
                    {projRuns.map(r => (
                      <div key={r.id} className="history-row">
                        <span className="history-id">#{r.id}</span>
                        <span className="history-meta">{r.total_tasks} tasks</span>
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
                )
              }
            </div>
          )}

          {/* Docs tab */}
          {activeTab === "docs" && (() => {
            type DocFile = { path: string; name: string; size: number; source: string };
            const planningFiles = (docFiles as DocFile[]).filter(f => f.source === "docs");
            const codeFiles     = (docFiles as DocFile[]).filter(f => f.source === "code");
            const selectedFile  = (docFiles as DocFile[]).find(f => f.path === selectedDoc);
            return (
              <div style={{ marginTop: 16 }}>
                {docFiles.length === 0 ? (
                  <p style={{ color: "#6b7280", fontSize: 13 }}>Chưa có file output. Chạy orchestrator để tạo tài liệu.</p>
                ) : (
                  <div style={{ display: "grid", gridTemplateColumns: selectedDoc ? "260px 1fr" : "1fr", gap: 12 }}>
                    <div style={{ borderRight: selectedDoc ? "1px solid #1e293b" : "none", paddingRight: selectedDoc ? 12 : 0 }}>
                      {planningFiles.length > 0 && (
                        <>
                          <div style={{ fontSize: 10, color: "#6b7280", padding: "6px 8px 2px", textTransform: "uppercase", letterSpacing: 1 }}>📋 Planning Docs</div>
                          {planningFiles.map(f => (
                            <div key={f.path} onClick={() => loadDocContent(selected.id, f.path, "docs")}
                              style={{ padding: "4px 8px", cursor: "pointer", borderRadius: 4, fontSize: 12,
                                background: selectedDoc === f.path ? "#1e293b" : "transparent",
                                color: selectedDoc === f.path ? "#f1f5f9" : "#9ca3af",
                                fontFamily: "monospace", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                              title={f.path}>{f.path}</div>
                          ))}
                        </>
                      )}
                      {codeFiles.length > 0 && (
                        <>
                          <div style={{ fontSize: 10, color: "#6b7280", padding: "10px 8px 2px", textTransform: "uppercase", letterSpacing: 1 }}>💻 Source Code</div>
                          {codeFiles.map(f => (
                            <div key={f.path} onClick={() => loadDocContent(selected.id, f.path, "code")}
                              style={{ padding: "4px 8px", cursor: "pointer", borderRadius: 4, fontSize: 12,
                                background: selectedDoc === f.path ? "#1e293b" : "transparent",
                                color: selectedDoc === f.path ? "#f1f5f9" : "#9ca3af",
                                fontFamily: "monospace", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                              title={f.path}>{f.path}</div>
                          ))}
                        </>
                      )}
                    </div>
                    {selectedDoc && (
                      <div>
                        <div style={{ fontSize: 11, color: "#4b5563", marginBottom: 8, fontFamily: "monospace" }}>
                          {selectedFile?.source === "docs" ? "📋" : "💻"} {selectedDoc}
                        </div>
                        {docLoading ? (
                          <div style={{ color: "#6b7280", fontSize: 13 }}>Loading...</div>
                        ) : (
                          <pre style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, padding: 16,
                            fontFamily: "monospace", fontSize: 12, lineHeight: 1.6, whiteSpace: "pre-wrap",
                            wordBreak: "break-word", color: "#e2e8f0", maxHeight: 600, overflowY: "auto", margin: 0 }}>
                            {docContent}
                          </pre>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })()}
        </div>
      )}

      {/* Delete project modal */}
      {showDeleteProject && selected && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ background: "#0f172a", border: "1px solid #374151", borderRadius: 12, padding: 28, minWidth: 420, maxWidth: 520 }}>
            {deleteStep === "done" ? (
              <div style={{ textAlign: "center", padding: "8px 0" }}>
                <div style={{ fontSize: 32, marginBottom: 8 }}>✅</div>
                <p style={{ color: "#4ade80", fontSize: 15, fontWeight: 600 }}>Đã xóa project <strong>{selected.name}</strong></p>
              </div>
            ) : (
              <>
                <h4 style={{ margin: "0 0 6px", color: "#f1f5f9" }}>Xóa project <code style={{ background: "#1e293b", padding: "2px 8px", borderRadius: 4 }}>{selected.id}</code>?</h4>
                <p style={{ fontSize: 13, color: "#9ca3af", margin: "0 0 20px" }}>
                  Folder <code style={{ background: "#1e293b", padding: "1px 5px", borderRadius: 3, fontSize: 11 }}>clients/{selected.id}/</code> sẽ bị xóa vĩnh viễn.
                  Tải backup trước nếu cần.
                </p>

                {/* Download buttons */}
                <div style={{ display: "flex", gap: 10, marginBottom: 20 }}>
                  <a href={`/api/projects/${selected.id}/backup/docs`} download
                    style={{ flex: 1, background: "#172554", border: "1px solid #1e40af", borderRadius: 8, padding: "10px 14px", textDecoration: "none", display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                    <span style={{ fontSize: 20 }}>📄</span>
                    <span style={{ fontSize: 12, color: "#93c5fd", fontWeight: 600 }}>Backup Docs</span>
                    <span style={{ fontSize: 10, color: "#3b82f6" }}>prd.md + docs/</span>
                  </a>
                  <a href={`/api/projects/${selected.id}/backup/source`} download
                    style={{ flex: 1, background: "#14532d", border: "1px solid #166534", borderRadius: 8, padding: "10px 14px", textDecoration: "none", display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                    <span style={{ fontSize: 20 }}>💻</span>
                    <span style={{ fontSize: 12, color: "#86efac", fontWeight: 600 }}>Backup Source</span>
                    <span style={{ fontSize: 10, color: "#4ade80" }}>output/{selected.id}/</span>
                  </a>
                </div>

                <div style={{ background: "#1a0a0a", border: "1px solid #7f1d1d", borderRadius: 8, padding: "10px 14px", marginBottom: 20, fontSize: 12, color: "#fca5a5" }}>
                  ⚠️ Hành động này không thể hoàn tác. Source code trong <code style={{ background: "#0f172a", padding: "1px 4px", borderRadius: 3 }}>output/</code> sẽ không bị xóa (cần xóa thủ công nếu muốn).
                </div>

                <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                  <button className="btn-muted" onClick={() => setShowDeleteProject(false)}>Huỷ</button>
                  <button className="btn-danger" disabled={deleteProjecting} onClick={handleDeleteProject}>
                    {deleteProjecting ? "Đang xóa..." : "Xóa Project"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Remove agent confirm dialog */}
      {removeAgentKey && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ background: "#0f172a", border: "1px solid #374151", borderRadius: 12, padding: 24, minWidth: 360, maxWidth: 480 }}>
            <h4 style={{ margin: "0 0 12px", color: "#f1f5f9" }}>Xóa agent <code style={{ background: "#1e293b", padding: "2px 6px", borderRadius: 4 }}>{removeAgentKey}</code>?</h4>
            <p style={{ fontSize: 13, color: "#9ca3af", margin: "0 0 16px" }}>
              Agent sẽ bị xóa khỏi <code style={{ background: "#1e293b", padding: "1px 5px", borderRadius: 3, fontSize: 11 }}>settings.toml</code> và không chạy trong các lần orchestrate tiếp theo.
            </p>
            {AGENTS_WITH_WORKSPACE.includes(removeAgentKey) && (
              <label style={{ display: "flex", alignItems: "flex-start", gap: 10, cursor: "pointer", background: "#1e293b", border: "1px solid #374151", borderRadius: 8, padding: "10px 12px", marginBottom: 16 }}>
                <input type="checkbox" checked={removeWithCleanup} onChange={e => setRemoveWithCleanup(e.target.checked)}
                  style={{ marginTop: 2, accentColor: "#ef4444", flexShrink: 0 }} />
                <div>
                  <div style={{ fontSize: 13, color: "#f1f5f9", fontWeight: 500 }}>Xóa workspace code</div>
                  <div style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>
                    Xóa toàn bộ folder <code style={{ background: "#0f172a", padding: "1px 4px", borderRadius: 3 }}>output/{selected?.id}/{removeAgentKey.startsWith("be") ? "backend" : removeAgentKey.startsWith("fe") ? "frontend" : "fullstack"}/{removeAgentKey}/</code>
                  </div>
                </div>
              </label>
            )}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button className="btn-muted" onClick={() => setRemoveAgentKey(null)}>Huỷ</button>
              <button className="btn-danger" onClick={handleRemoveAgent}>
                {removeWithCleanup ? "Xóa agent + workspace" : "Xóa agent"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Workspace deleted toast */}
      {removedWorkspaceMsg && (
        <div style={{ position: "fixed", bottom: 24, right: 24, background: "#14532d", border: "1px solid #166534", borderRadius: 8, padding: "10px 16px", fontSize: 13, color: "#86efac", zIndex: 200, maxWidth: 400 }}>
          ✓ {removedWorkspaceMsg}
          <button onClick={() => setRemovedWorkspaceMsg(null)} style={{ marginLeft: 12, background: "none", border: "none", color: "#86efac", cursor: "pointer", fontSize: 16, lineHeight: 1 }}>✕</button>
        </div>
      )}

      {runDetail && (
        <RunConsole mode="overlay"
          initialWorkflowId={runDetail.workflowId}
          initialRunId={runDetail.runId}
          onClose={() => {
            setRunDetail(null);
            if (selected) loadFeatures(selected.id);   // tiến độ có thể đã đổi
          }} />
      )}

      {!selected && projects.length === 0 && (
        <div className="state">Không tìm thấy folder nào trong clients/. Tạo folder và thêm settings.toml.</div>
      )}

      <div className="project-grid">
        {projects.map(p => (
          <div key={p.id} className="project-card" onClick={() => openProject(p.id)}>
            <div className="project-card-top">
              <span className="project-card-name">{p.name}</span>
              <span className="project-link" style={{ fontSize: 10, padding: "2px 6px" }}>{p.id}</span>
            </div>
            {p.tech_stack?.backend && (
              <p className="project-card-desc" style={{ color: "#22c55e" }}>{p.tech_stack.backend}</p>
            )}
            <div className="project-card-meta">
              <span>{p.agent_count} agent{p.agent_count !== 1 ? "s" : ""}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
