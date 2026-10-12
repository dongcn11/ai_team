import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import RunConsole from "./RunConsole";
import TaskDraftCard, { Created, Draft } from "./TaskDraftCard";
import { useProjects } from "../hooks/useProjects";
import "./AssistantHome.css";

/* Màn hình chính: trợ lý (trái) · trò chuyện (giữa) · công việc (phải).
   Trò chuyện là chat AI thường, KHÔNG giao việc — worker.py trên host gọi Claude
   trả lời (api/routers/assistant.py). Cột Công việc chỉ hiển thị các lần chạy
   workflow từ mọi nguồn khác. */

interface Thread {
  id: number;
  title: string;
  client_folder: string | null;
  model: string | null;        // khoá model; null = mặc định (model đầu tiên được dùng)
  message_count: number;
  busy: boolean;
  preview: string;
  created_at: string | null;
  updated_at: string | null;
}

interface FileRef { id: number; name: string; mime: string; size: number }

// Model chat tài khoản được dùng (api/chat_models.py) — phần tử đầu là mặc định.
export interface ChatModel {
  key: string; label: string; description: string; group: string;
  via: "cli" | "http"; files: boolean; project: boolean;
}

// File trong ô soạn tin: tải lên ngay khi chọn, gửi tin chỉ kèm id.
interface Attachment { key: string; name: string; size: number; file?: FileRef; error?: string }

interface ChatMsg {
  id: number;
  thread_id: number | null;
  role: "user" | "assistant";
  text: string;
  kind: "chat" | "task_draft";
  meta: {
    draft?: Draft; created?: Created; files?: FileRef[]; model?: string;
    // Script tạo file chạy trong sandbox (api/routers/assistant._run_gen)
    gen?: { status: "running" | "done" | "error"; code?: string; error?: string };
  } | null;
  status: "pending" | "running" | "done" | "error";
  error: string | null;
  cost_usd: number | null;
  created_at: string | null;
}

type JobState = "waiting" | "running" | "done" | "failed" | "cancelled";

interface Job {
  run_id: number;
  workflow_id: number;
  title: string;
  client_folder: string | null;
  state: JobState;
  reason: string | null;
  open_questions: number;
  source: "chat" | "schedule" | "task" | "manual";
  trigger: string | null;
  progress: { done: number; total: number };
  cost_usd: number;
  created_at: string | null;
  finished_at: string | null;
}

interface Overview {
  jobs: Job[];
  counts: { running: number; waiting: number };
  today: { turns: number; cost_usd: number; chat_cost_usd: number };
  worker: { online: boolean; silent_s: number | null };
  chat_busy: boolean;
  greeting: string;
}

type Filter = "all" | "waiting" | "running" | "done";

const POLL_MS = 4000;
// Đang chờ trợ lý trả lời thì hỏi dày hơn — câu trả lời thường về sau ~5s.
const POLL_FAST_MS = 1200;
const THREAD_KEY = "assistant.thread";

const FILE_MAX = 15 * 1024 * 1024;           // khớp _FILE_MAX ở api/routers/assistant.py
const FILES_PER_MSG = 10;

const fmtSize = (n: number) =>
  n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${Math.round(n / 1024)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;

const fileUrl = (id: number) => `/api/assistant/files/${id}`;

function FileChips({ files }: { files: FileRef[] }) {
  return (
    <div className="ah-files">
      {files.map(f => f.mime.startsWith("image/") && f.mime !== "image/svg+xml" ? (
        <a key={f.id} className="ah-file-img" href={fileUrl(f.id)} target="_blank" rel="noreferrer" title={f.name}>
          <img src={fileUrl(f.id)} alt={f.name} loading="lazy" />
        </a>
      ) : (
        <a key={f.id} className="ah-file" href={fileUrl(f.id)} target="_blank" rel="noreferrer" title={f.name}>
          <span className="ah-file-ico">📄</span>
          <span className="ah-file-name">{f.name}</span>
          <span className="ah-file-size">{fmtSize(f.size)}</span>
        </a>
      ))}
    </div>
  );
}

const readLS = (k: string) => { try { return localStorage.getItem(k); } catch { return null; } };
const writeLS = (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* bỏ qua */ } };

async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init?.body ? { ...init, headers: { "Content-Type": "application/json" } } : init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// API trả datetime UTC không kèm múi giờ — thiếu "Z" thì trình duyệt hiểu là giờ địa phương.
const parseTs = (s: string | null) =>
  s ? new Date(/([zZ]|[+-]\d\d:?\d\d)$/.test(s) ? s : s + "Z") : null;

const hhmm = (s: string | null) =>
  parseTs(s)?.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }) ?? "";

function ago(s: string | null) {
  const d = parseTs(s);
  if (!d) return "";
  const sec = Math.max(0, (Date.now() - d.getTime()) / 1000);
  if (sec < 60) return "vừa xong";
  if (sec < 3600) return `${Math.floor(sec / 60)} phút trước`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} giờ trước`;
  return d.toLocaleDateString("vi-VN");
}

/* Markdown tối giản cho câu trả lời của Claude: khối ``` code, **đậm**, `code`,
   _nghiêng_. Không kéo thư viện markdown — React tự escape nên an toàn. */
function Inline({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|(?<![\w/])_[^_\n]+_(?![\w]))/g);
  return (
    <>
      {parts.map((p, i) => {
        if (p.startsWith("**") && p.endsWith("**") && p.length > 4) return <b key={i}>{p.slice(2, -2)}</b>;
        if (p.startsWith("`") && p.endsWith("`") && p.length > 2) return <code key={i}>{p.slice(1, -1)}</code>;
        if (p.startsWith("_") && p.endsWith("_") && p.length > 2) return <i key={i}>{p.slice(1, -1)}</i>;
        return <React.Fragment key={i}>{p}</React.Fragment>;
      })}
    </>
  );
}

function RichText({ text }: { text: string }) {
  const blocks = text.split(/```[^\n]*\n?([\s\S]*?)```/g);
  return (
    <>
      {blocks.map((b, i) => i % 2 === 1
        ? <pre key={i} className="ah-pre">{b.replace(/\n$/, "")}</pre>
        : <Inline key={i} text={b} />)}
    </>
  );
}

/* Nhân vật trợ lý — SVG vẽ tay, không kéo thêm runtime Live2D (~MB) chỉ để trang trí. */
function AssistantFigure({ busy }: { busy: boolean }) {
  return (
    <svg className={`ah-figure ${busy ? "busy" : ""}`} viewBox="0 0 160 360" aria-hidden="true">
      <ellipse cx="80" cy="352" rx="44" ry="6" fill="rgba(60,40,20,.12)" />
      {/* chân */}
      <path d="M62 250 L60 336 L70 336 L74 252 Z" fill="#3a3340" />
      <path d="M98 250 L100 336 L90 336 L86 252 Z" fill="#3a3340" />
      <path d="M56 334 h18 v8 h-20 z M86 334 h18 v8 h-20 z" fill="#1f1b24" />
      {/* váy + áo */}
      <path d="M52 200 L108 200 L116 262 L44 262 Z" fill="#2f3440" />
      <path d="M50 118 Q80 104 110 118 L114 206 L46 206 Z" fill="#343a46" />
      <path d="M72 116 L80 150 L88 116 Z" fill="#f4f1ec" />
      <path d="M76 124 L80 138 L84 124 Z" fill="#6b9bd1" />
      {/* tay */}
      <path d="M50 122 Q36 160 44 200 L54 198 Q50 162 60 130 Z" fill="#343a46" />
      <g className="ah-wave">
        <path d="M110 122 Q126 140 122 156 L112 158 Q112 144 102 132 Z" fill="#343a46" />
        <circle cx="118" cy="160" r="7" fill="#f6dcc8" />
      </g>
      <circle cx="48" cy="204" r="6" fill="#f6dcc8" />
      {/* cổ + đầu */}
      <rect x="74" y="98" width="12" height="14" fill="#f6dcc8" />
      <path d="M50 64 Q50 26 80 24 Q110 26 110 64 Q112 86 100 96 L60 96 Q48 86 50 64 Z" fill="#3b3346" />
      <ellipse cx="80" cy="70" rx="24" ry="28" fill="#f6dcc8" />
      <path d="M56 58 Q64 36 80 38 Q98 36 104 58 Q92 48 80 50 Q66 48 56 58 Z" fill="#3b3346" />
      <path d="M52 60 Q44 84 54 104 L60 100 Q54 84 58 64 Z" fill="#3b3346" />
      <g className="ah-eyes">
        <ellipse cx="71" cy="72" rx="3.2" ry="4" fill="#2c3e66" />
        <ellipse cx="89" cy="72" rx="3.2" ry="4" fill="#2c3e66" />
      </g>
      <path d="M75 86 Q80 90 85 86" stroke="#c46a5a" strokeWidth="2" fill="none" strokeLinecap="round" />
      <ellipse cx="66" cy="81" rx="4" ry="2" fill="#f2b3a6" opacity=".6" />
      <ellipse cx="94" cy="81" rx="4" ry="2" fill="#f2b3a6" opacity=".6" />
    </svg>
  );
}

const STATE_LABEL: Record<JobState, string> = {
  waiting: "Chờ làm", running: "Đang chạy", done: "Hoàn thành", failed: "Lỗi", cancelled: "Đã huỷ",
};
const SOURCE_LABEL: Record<Job["source"], string> = {
  chat: "từ bot", schedule: "theo lịch", task: "từ feature", manual: "chạy tay",
};

export default function AssistantHome({ onOpenProject }: { onOpenProject?: (slug: string) => void } = {}) {
  const { projects } = useProjects();
  const [threads, setThreads] = useState<Thread[]>([]);
  const [threadId, setThreadId] = useState<number | null>(() => Number(readLS(THREAD_KEY)) || null);
  const [renaming, setRenaming] = useState<{ id: number; title: string } | null>(null);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [ov, setOv] = useState<Overview | null>(null);
  const [apiErr, setApiErr] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [attach, setAttach] = useState<Attachment[]>([]);
  const [models, setModels] = useState<ChatModel[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [bubble, setBubble] = useState(true);
  const [openRun, setOpenRun] = useState<Job | null>(null);
  // Điện thoại (≤760px) chỉ hiện 1 khung: chat hoặc danh sách công việc.
  const [pane, setPane] = useState<"chat" | "jobs">("chat");
  const listRef = useRef<HTMLDivElement>(null);
  const lastIdRef = useRef(0);
  // Thread đang mở tại thời điểm response về — đổi thread giữa chừng thì bỏ kết
  // quả cũ, không thì tin của thread trước đè lên thread vừa chọn.
  const threadRef = useRef<number | null>(threadId);

  const selectThread = useCallback((id: number | null) => {
    threadRef.current = id;
    setThreadId(id);
    setMessages([]);
    setAttach([]);                    // file trong ô soạn thuộc thread cũ
    lastIdRef.current = 0;
    writeLS(THREAD_KEY, id ? String(id) : "");
  }, []);

  const load = useCallback(async () => {
    try {
      const [ts, o, ms] = await Promise.all([
        api<Thread[]>("/api/assistant/threads"),
        api<Overview>(`/api/assistant/overview?tz_offset=${new Date().getTimezoneOffset()}`),
        api<ChatModel[]>("/api/assistant/models"),
      ]);
      setThreads(ts);
      setModels(ms);
      setOv(o);
      let tid = threadRef.current;
      if (tid && !ts.some(t => t.id === tid)) tid = null;       // bị xoá ở tab khác
      if (!tid && ts.length) tid = ts[0].id;
      if (tid !== threadRef.current) selectThread(tid);
      if (tid) {
        const ms = await api<ChatMsg[]>(`/api/assistant/threads/${tid}/messages`);
        if (threadRef.current === tid) setMessages(ms);
      }
      setApiErr(null);
    } catch (e) {
      setApiErr(e instanceof Error ? e.message : "Không kết nối được API");
    }
  }, [selectThread]);

  const waitingReply = messages.some(m => m.status === "pending" || m.status === "running");

  useEffect(() => {
    const t = setInterval(load, waitingReply ? POLL_FAST_MS : POLL_MS);
    return () => clearInterval(t);
  }, [load, waitingReply]);

  useEffect(() => { load(); }, [load, threadId]);

  // Chỉ cuộn xuống khi có tin MỚI hoặc câu trả lời vừa về — poll vài giây/lần mà
  // cuộn mỗi lần thì không đọc lại tin cũ được.
  useEffect(() => {
    const lastMsg = messages[messages.length - 1];
    const last = lastMsg ? lastMsg.id * 10 + (lastMsg.status === "done" ? 1 : 0) : 0;
    if (last !== lastIdRef.current) {
      lastIdRef.current = last;
      listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [messages]);

  // Chưa có thread nào (lần đầu) → tạo luôn, người dùng không phải bấm "mới" trước.
  const ensureThread = async () => {
    if (threadRef.current) return threadRef.current;
    const tid = (await api<Thread>("/api/assistant/threads", { method: "POST", body: "{}" })).id;
    selectThread(tid);
    return tid;
  };

  const addFiles = async (list: FileList | File[]) => {
    const picked = Array.from(list);
    if (!picked.length) return;
    if (curModel?.files === false) {
      setApiErr(`${curModel.label} không đọc được file — chọn model Claude để gửi file`);
      return;
    }
    const room = FILES_PER_MSG - attach.length;
    if (room <= 0) { setApiErr(`Tối đa ${FILES_PER_MSG} file mỗi tin`); return; }
    let tid: number;
    try {
      tid = await ensureThread();
    } catch (e) {
      setApiErr(e instanceof Error ? e.message : "Không tạo được cuộc trò chuyện");
      return;
    }
    const items = picked.slice(0, room).map(f => ({
      src: f,
      a: { key: `${Date.now()}-${Math.random()}`, name: f.name || "anh-dan.png", size: f.size,
           error: f.size > FILE_MAX ? `quá ${FILE_MAX / 1024 / 1024} MB` : undefined } as Attachment,
    }));
    setAttach(prev => [...prev, ...items.map(i => i.a)]);
    await Promise.all(items.filter(i => !i.a.error).map(async ({ src, a }) => {
      const fd = new FormData();
      fd.append("file", src, a.name);
      let patch: Partial<Attachment>;
      try {
        const res = await fetch(`/api/assistant/threads/${tid}/files`, { method: "POST", body: fd });
        const body = await res.json().catch(() => ({}));
        patch = res.ok ? { file: body as FileRef, name: body.name }
                       : { error: body.detail ?? `HTTP ${res.status}` };
      } catch {
        patch = { error: "tải lên không được" };
      }
      if (threadRef.current === tid)
        setAttach(prev => prev.map(x => x.key === a.key ? { ...x, ...patch } : x));
    }));
  };

  const removeAttach = (a: Attachment) => {
    setAttach(prev => prev.filter(x => x.key !== a.key));
    if (a.file) fetch(fileUrl(a.file.id), { method: "DELETE" }).catch(() => { /* bỏ qua */ });
  };

  const uploading = attach.some(a => !a.file && !a.error);
  const readyFiles = attach.filter(a => a.file).map(a => a.file!);
  const canSend = (!!draft.trim() || readyFiles.length > 0) && !sending && !waitingReply && !uploading;

  const send = async () => {
    const text = draft.trim();
    if (!canSend) return;
    setSending(true);
    try {
      const tid = await ensureThread();
      const fresh = await api<ChatMsg[]>(`/api/assistant/threads/${tid}/messages`,
        { method: "POST", body: JSON.stringify({ text, file_ids: readyFiles.map(f => f.id) }) });
      if (threadRef.current === tid)
        setMessages(prev => [...prev.filter(m => !fresh.some(f => f.id === m.id)), ...fresh]);
      setDraft("");
      setAttach([]);
      setBubble(false);
      load();
    } catch (e) {
      setApiErr(e instanceof Error ? e.message : "Gửi không được");
    } finally {
      setSending(false);
    }
  };

  const retry = async (id: number) => {
    const res = await fetch(`/api/assistant/messages/${id}/retry`, { method: "POST" }).catch(() => null);
    if (res && !res.ok) {
      const body = await res.json().catch(() => ({}));
      setApiErr(body.detail ?? `HTTP ${res.status}`);
    }
    load();
  };

  const hasTalk = messages.some(m => m.role === "user");

  const requestDraft = async () => {
    if (!threadId || waitingReply || !hasTalk) return;
    try {
      const m = await api<ChatMsg>(`/api/assistant/threads/${threadId}/task-draft`, {
        method: "POST",
        body: JSON.stringify({ projects: projects.map(p => ({ id: p.id, name: p.name })) }),
      });
      if (threadRef.current === threadId) setMessages(prev => [...prev, m]);
      setBubble(false);
      load();
    } catch (e) {
      setApiErr(e instanceof Error ? e.message : "Không soạn được task");
    }
  };

  const curThread = threads.find(t => t.id === threadId) ?? null;
  // Model trả lời câu tiếp theo — khớp _thread_model bên API.
  const curModel = models.find(m => m.key === curThread?.model) ?? models[0] ?? null;
  const modelLabel = (key?: string) => models.find(m => m.key === key)?.label ?? key?.replace(/^\w+:/, "");
  const modelGroups = useMemo(() => {
    const g: Record<string, ChatModel[]> = {};
    for (const m of models) (g[m.group] ??= []).push(m);
    return Object.entries(g);
  }, [models]);

  const changeModel = async (key: string) => {
    try {
      if (!threadId) {
        const t = await api<Thread>("/api/assistant/threads", { method: "POST", body: JSON.stringify({ model: key }) });
        setThreads(prev => [t, ...prev]);
        selectThread(t.id);
        return;
      }
      setThreads(prev => prev.map(t => t.id === threadId ? { ...t, model: key } : t));
      await api(`/api/assistant/threads/${threadId}`, { method: "PATCH", body: JSON.stringify({ model: key }) });
    } catch (e) {
      setApiErr(e instanceof Error ? e.message : "Không đổi được model");
    }
    load();
  };
  const projectName = (slug: string | null) =>
    slug ? (projects.find(p => p.id === slug)?.name ?? slug) : null;

  // Gắn / bỏ gắn dự án cho thread đang mở. Chưa có thread → tạo luôn với dự án đó.
  const changeProject = async (slug: string) => {
    const client_folder = slug || null;
    try {
      if (!threadId) {
        const t = await api<Thread>("/api/assistant/threads", { method: "POST", body: JSON.stringify({ client_folder }) });
        setThreads(prev => [t, ...prev]);
        selectThread(t.id);
        return;
      }
      setThreads(prev => prev.map(t => t.id === threadId ? { ...t, client_folder } : t));
      await api(`/api/assistant/threads/${threadId}`, { method: "PATCH", body: JSON.stringify({ client_folder }) });
    } catch (e) {
      setApiErr(e instanceof Error ? e.message : "Không đổi được dự án");
    }
    load();
  };

  const newThread = async () => {
    // Thread đang mở còn trống thì dùng luôn, đừng đẻ thêm thread rỗng.
    const cur = threads.find(t => t.id === threadId);
    if (cur && cur.message_count === 0) return;
    try {
      const t = await api<Thread>("/api/assistant/threads", { method: "POST", body: "{}" });
      setThreads(prev => [t, ...prev]);
      selectThread(t.id);
      setDraft("");
    } catch (e) {
      setApiErr(e instanceof Error ? e.message : "Không tạo được");
    }
  };

  const saveRename = async () => {
    if (!renaming) return;
    const { id, title } = renaming;
    setRenaming(null);
    setThreads(prev => prev.map(t => t.id === id ? { ...t, title: title.trim() || t.title } : t));
    await api(`/api/assistant/threads/${id}`, { method: "PATCH", body: JSON.stringify({ title }) })
      .catch(e => setApiErr(e.message));
    load();
  };

  const deleteThread = async (t: Thread) => {
    if (!confirm(`Xoá cuộc trò chuyện "${t.title}"?`)) return;
    await api(`/api/assistant/threads/${t.id}`, { method: "DELETE" }).catch(e => setApiErr(e.message));
    if (t.id === threadId) selectThread(null);
    load();
  };

  const jobs = ov?.jobs ?? [];
  const counts = useMemo(() => ({
    all: jobs.length,
    waiting: jobs.filter(j => j.state === "waiting").length,
    running: jobs.filter(j => j.state === "running").length,
    done: jobs.filter(j => j.state === "done").length,
  }), [jobs]);
  const shown = filter === "all" ? jobs : jobs.filter(j => j.state === filter);

  const greeting = ov?.greeting ?? "Xin chào! Bạn muốn trò chuyện gì hôm nay?";
  const online = !!ov?.worker.online;

  if (openRun) {
    return (
      <div className="ah-overlay">
        <RunConsole mode="overlay" initialWorkflowId={openRun.workflow_id}
          initialRunId={openRun.run_id} onClose={() => { setOpenRun(null); load(); }} />
      </div>
    );
  }

  return (
    <div className="ah">
      {/* ── Thanh trạng thái ── */}
      <div className="ah-top">
        <div className="ah-brand">
          <div className="ah-logo">AI</div>
          <div>
            <div className="ah-brand-name">AI Team</div>
            <div className="ah-brand-sub">giúp bạn giải quyết công việc nhanh chóng, tiết kiệm và uy tín.</div>
          </div>
        </div>
        <div className="ah-top-right">
          <span><b>{ov?.counts.running ?? 0}</b> đang chạy</span>
          <span className="ah-sep" />
          <span><b>{ov?.counts.waiting ?? 0}</b> chờ làm</span>
          <span className={`ah-online ${apiErr ? "err" : online ? "ok" : "off"}`}
            title={apiErr ? apiErr
              : online ? "worker.py đang nhận việc"
              : "Chưa thấy worker.py — bước tự chạy sẽ nằm chờ. Mở terminal: python worker.py"}>
            <i />{apiErr ? "Mất kết nối" : online ? "Trực tuyến" : "Worker nghỉ"}
          </span>
        </div>
      </div>

      {/* Điện thoại: thanh chuyển giữa Trò chuyện / Công việc (màn rộng ẩn đi) */}
      <div className="ah-mtabs" role="tablist">
        <button role="tab" aria-selected={pane === "chat"} className={pane === "chat" ? "on" : ""}
          onClick={() => setPane("chat")}>💬 Trò chuyện</button>
        <button role="tab" aria-selected={pane === "jobs"} className={pane === "jobs" ? "on" : ""}
          onClick={() => setPane("jobs")}>
          📋 Công việc <span>{jobs.length}</span>
          {counts.running > 0 && <i className="ah-mtabs-dot" title={`${counts.running} đang chạy`} />}
        </button>
      </div>

      <div className={`ah-body pane-${pane}`}>
        {/* ── Trợ lý ── */}
        <aside className="ah-left">
          <div className="ah-caption">Trợ lý</div>
          <div className="ah-name-row">
            <span className="ah-name">Trợ lý AI</span>
            <span className={`ah-status ${ov?.chat_busy ? "busy" : ""}`}>
              <i />{ov?.chat_busy ? "Đang trả lời" : online ? "Đang rảnh" : "Đang nghỉ"}
            </span>
          </div>
          <div className="ah-stage">
            {bubble && (
              <div className="ah-bubble">
                <button className="ah-bubble-x" onClick={() => setBubble(false)} aria-label="Đóng">×</button>
                {greeting}
              </div>
            )}
            <AssistantFigure busy={!!ov?.chat_busy} />
            <span className="ah-chip">{ov?.chat_busy ? "Đang suy nghĩ…" : "Sẵn sàng"}</span>
          </div>
          <div className="ah-stats">
            <div className="ah-stat">
              <div className="ah-stat-label">Hôm nay</div>
              <div className="ah-stat-value">{ov?.today.turns ?? 0} lượt</div>
            </div>
            <div className="ah-stat">
              <div className="ah-stat-label" title={`Chat: $${(ov?.today.chat_cost_usd ?? 0).toFixed(2)} · còn lại là các bước workflow`}>Chi phí</div>
              <div className="ah-stat-value accent">${(ov?.today.cost_usd ?? 0).toFixed(2)}</div>
            </div>
          </div>
        </aside>

        {/* ── Trò chuyện: danh sách thread + khung chat ── */}
        <section className="ah-chat-area">
        <nav className="ah-threads">
          <button className="ah-new" onClick={newThread}>＋ Cuộc trò chuyện mới</button>
          <div className="ah-thread-list">
            {threads.length === 0 && <div className="ah-thread-empty">Chưa có cuộc trò chuyện nào</div>}
            {threads.map(t => (
              <div key={t.id} className={`ah-thread ${t.id === threadId ? "active" : ""}`}
                onClick={() => t.id !== threadId && selectThread(t.id)}
                onDoubleClick={() => setRenaming({ id: t.id, title: t.title })}
                title="Bấm đúp để đổi tên">
                {renaming?.id === t.id ? (
                  <input className="ah-thread-input" autoFocus value={renaming.title}
                    onChange={e => setRenaming({ id: t.id, title: e.target.value })}
                    onClick={e => e.stopPropagation()}
                    onBlur={saveRename}
                    onKeyDown={e => {
                      if (e.key === "Enter") saveRename();
                      if (e.key === "Escape") setRenaming(null);
                    }} />
                ) : (
                  <>
                    <div className="ah-thread-title">
                      {t.busy && <i className="ah-thread-dot" />}
                      <span>{t.title}</span>
                    </div>
                    <div className="ah-thread-meta">
                      {t.client_folder && <b className="ah-thread-proj">{projectName(t.client_folder)}</b>}
                      <span>{t.preview || "Chưa có tin nhắn"}</span>
                    </div>
                    <div className="ah-thread-actions" onClick={e => e.stopPropagation()}>
                      <button title="Đổi tên" onClick={() => setRenaming({ id: t.id, title: t.title })}>✎</button>
                      <button title="Xoá" onClick={() => deleteThread(t)}>×</button>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </nav>

        <div className="ah-chat">
          <div className="ah-chat-head">
            <h2>Trò chuyện</h2>
            <select className="ah-thread-select" value={threadId ?? ""}
              onChange={e => selectThread(Number(e.target.value) || null)}>
              {threads.map(t => <option key={t.id} value={t.id}>{t.title}</option>)}
            </select>
            <button className="ah-ghost ah-new-sm" onClick={newThread} title="Cuộc trò chuyện mới">＋</button>
            <select className={`ah-project ${curThread?.client_folder ? "on" : ""}`}
              value={curThread?.client_folder ?? ""} onChange={e => changeProject(e.target.value)}
              disabled={waitingReply}
              title="Chọn dự án: Claude được đọc tài liệu + code của dự án đó để trả lời (chỉ đọc). Để trống = chat tự do.">
              <option value="">💬 Chat tự do</option>
              {projects.map(p => <option key={p.id} value={p.id}>📁 {p.name}</option>)}
            </select>
            {models.length > 0 && (
              <select className="ah-project ah-model" value={curModel?.key ?? ""}
                onChange={e => changeModel(e.target.value)} disabled={waitingReply}
                title={curModel ? `${curModel.label}${curModel.description ? " — " + curModel.description : ""}`
                  + (curModel.files ? "" : " · không đọc được file đính kèm")
                  + (curThread?.client_folder && !curModel.project ? " · không đọc được tài liệu/code dự án" : "")
                  : ""}>
                {modelGroups.map(([group, ms]) => (
                  <optgroup key={group} label={group}>
                    {ms.map(m => (
                      <option key={m.key} value={m.key}>
                        ✨ {m.label}{m.files ? "" : " (chỉ chữ)"}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            )}
            {!models.length && ov && (
              <span className="ah-model-none" title="Liên hệ quản trị viên để được cấp model">Chưa được cấp model</span>
            )}
            <button className="ah-ghost ah-task-btn" onClick={requestDraft}
              disabled={!hasTalk || waitingReply}
              title={hasTalk ? "Claude đọc cuộc trò chuyện và soạn nháp task để bạn chọn dự án rồi tạo"
                             : "Trao đổi vài câu trước rồi mới tạo task được"}>
              📋 Tạo task
            </button>
            <span className="ah-chat-hint">Trò chuyện bằng tiếng Việt — Enter để gửi</span>
          </div>

          {!online && !apiErr && (
            <div className="ah-q-banner">
              Worker chưa chạy nên trợ lý chưa trả lời được — mở terminal ở thư mục repo và chạy <code>python worker.py</code>.
            </div>
          )}

          <div className="ah-msgs" ref={listRef}>
            <div className="ah-divider">Đầu cuộc trò chuyện</div>
            {messages.length === 0 && (
              <div className="ah-msg assistant">
                <div className="ah-msg-bubble">{greeting}</div>
              </div>
            )}
            {messages.map(m => {
              if (m.status === "running" && m.meta?.gen?.status === "running") {
                return (
                  <div key={m.id} className="ah-msg assistant">
                    <div className="ah-msg-bubble"><RichText text={m.text} /></div>
                    <div className="ah-gen-run"><i className="ah-gen-spin" />Đang tạo file…</div>
                  </div>
                );
              }
              if (m.status === "pending" || m.status === "running") {
                return (
                  <div key={m.id} className="ah-msg assistant">
                    <div className="ah-msg-bubble ah-typing" title={m.status === "pending" ? "Chờ worker nhận" : "Claude đang viết"}>
                      {m.kind === "task_draft" && <span className="ah-typing-label">Đang soạn nháp task</span>}
                      <i /><i /><i />
                    </div>
                  </div>
                );
              }
              if (m.status === "error") {
                return (
                  <div key={m.id} className="ah-msg assistant">
                    <div className="ah-msg-bubble ah-err">⚠️ Không trả lời được: {m.error}</div>
                    <div className="ah-msg-time">
                      {hhmm(m.created_at)}
                      <button className="ah-link" onClick={() => retry(m.id)}>· thử lại</button>
                    </div>
                  </div>
                );
              }
              if (m.kind === "task_draft" && m.meta?.draft) {
                return (
                  <div key={m.id} className="ah-msg assistant wide">
                    <TaskDraftCard msgId={m.id} draft={m.meta.draft} created={m.meta.created ?? null}
                      projects={projects} onCreated={load} onOpenProject={onOpenProject} />
                    <div className="ah-msg-time">{hhmm(m.created_at)}</div>
                  </div>
                );
              }
              const mine = m.role === "user";
              return (
                <div key={m.id} className={`ah-msg ${m.role}`}>
                  {mine && !!m.meta?.files?.length && <FileChips files={m.meta.files} />}
                  <div className="ah-msg-bubble"><RichText text={m.text} /></div>
                  {!mine && !!m.meta?.files?.length && <FileChips files={m.meta.files} />}
                  {m.meta?.gen?.status === "error" && (
                    <div className="ah-gen-err">⚠️ Không tạo được file: <code>{m.meta.gen.error}</code>
                      <div className="ah-gen-hint">Nhắn lại để trợ lý sửa script, vd: “sửa lỗi trên rồi tạo lại file”.</div>
                    </div>
                  )}
                  {m.meta?.gen?.code && (
                    <details className="ah-gen-code">
                      <summary>Xem script tạo file</summary>
                      <pre className="ah-pre">{m.meta.gen.code}</pre>
                    </details>
                  )}
                  <div className="ah-msg-time">
                    {hhmm(m.created_at)}
                    {m.role === "assistant" && m.meta?.model && <> · {modelLabel(m.meta.model)}</>}
                  </div>
                </div>
              );
            })}
          </div>

          <div className={`ah-compose ${dragOver ? "drag" : ""}`}
            onDragOver={e => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setDragOver(true); } }}
            onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragOver(false); }}
            onDrop={e => {
              if (!e.dataTransfer.files.length) return;
              e.preventDefault();
              setDragOver(false);
              addFiles(e.dataTransfer.files);
            }}>
            {attach.length > 0 && (
              <div className="ah-attach">
                {attach.map(a => (
                  <span key={a.key} className={`ah-attach-chip ${a.error ? "err" : !a.file ? "busy" : ""}`}
                    title={a.error ? `${a.name}: ${a.error}` : a.name}>
                    <span className="ah-file-name">{a.name}</span>
                    <span className="ah-file-size">{a.error ?? (a.file ? fmtSize(a.size) : "đang tải…")}</span>
                    <button onClick={() => removeAttach(a)} aria-label={`Bỏ ${a.name}`}>×</button>
                  </span>
                ))}
              </div>
            )}
            <textarea
              value={draft}
              placeholder="Nhắn cho trợ lý... (Enter để gửi, Shift+Enter xuống dòng, kéo-thả hoặc dán file vào đây)"
              onChange={e => setDraft(e.target.value)}
              onPaste={e => {
                if (e.clipboardData.files.length) {
                  e.preventDefault();
                  addFiles(e.clipboardData.files);
                }
              }}
              onKeyDown={e => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <div className="ah-compose-foot">
              <input ref={fileInputRef} type="file" multiple hidden
                onChange={e => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }} />
              <button className="ah-attach-btn" onClick={() => fileInputRef.current?.click()}
                disabled={attach.length >= FILES_PER_MSG || curModel?.files === false}
                title={curModel?.files === false
                  ? `${curModel.label} không đọc được file — chọn model Claude để gửi file`
                  : "Đính kèm file (ảnh, PDF, Word, Excel, PowerPoint, file chữ…) — tối đa 15 MB/file"}>
                📎
              </button>
              <span className="ah-compose-tip">
                Hỏi đáp, bàn ý tưởng — chốt xong bấm <b>📋 Tạo task</b> để giao cho dự án
              </span>
              <button className="ah-send" disabled={!canSend} onClick={send}>
                {sending ? "Đang gửi…" : waitingReply ? "Đang trả lời…" : uploading ? "Đang tải file…" : "Gửi"}
              </button>
            </div>
          </div>
        </div>
        </section>

        {/* ── Công việc ── */}
        <aside className="ah-jobs">
          <div className="ah-jobs-head">
            <h2>Công việc <span className="ah-count">{jobs.length}</span></h2>
            <button className="ah-ghost" onClick={load}>Tải lại</button>
          </div>
          <div className="ah-filters">
            {([["all", "Tất cả"], ["waiting", "Chờ làm"], ["running", "Đang chạy"], ["done", "Hoàn thành"]] as [Filter, string][])
              .map(([k, label]) => (
                <button key={k} className={`ah-filter ${filter === k ? "active" : ""}`} onClick={() => setFilter(k)}>
                  {label} <span>{counts[k]}</span>
                </button>
              ))}
          </div>

          <div className="ah-job-list">
            {shown.length === 0 ? (
              <div className="ah-empty">
                <div className="ah-empty-dot" />
                <b>Chưa có việc nào</b>
                <span>Các lần chạy workflow (từ Features, lịch, bot…) sẽ hiện ra đây.</span>
              </div>
            ) : shown.map(j => {
              const pct = j.progress.total ? Math.round(j.progress.done / j.progress.total * 100) : 0;
              return (
                <button key={j.run_id} className={`ah-job ${j.state}`} onClick={() => setOpenRun(j)}
                  title="Mở màn hình chạy">
                  <div className="ah-job-top">
                    <span className="ah-job-title">{j.title}</span>
                    <span className={`ah-pill ${j.state}`}>{STATE_LABEL[j.state] ?? j.state}</span>
                  </div>
                  {j.trigger && <div className="ah-job-trigger">{j.trigger}</div>}
                  <div className="ah-bar"><i style={{ width: `${pct}%` }} /></div>
                  <div className="ah-job-meta">
                    <span>#{j.run_id}{j.client_folder ? ` · ${j.client_folder}` : ""} · {SOURCE_LABEL[j.source]}</span>
                    <span>{j.progress.done}/{j.progress.total} bước</span>
                  </div>
                  <div className="ah-job-meta">
                    <span>{j.reason ?? ago(j.finished_at ?? j.created_at)}</span>
                    {j.cost_usd > 0 && <span>${j.cost_usd.toFixed(2)}</span>}
                  </div>
                </button>
              );
            })}
          </div>
        </aside>
      </div>
    </div>
  );
}
