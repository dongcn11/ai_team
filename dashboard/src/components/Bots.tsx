import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useProjects } from "../hooks/useProjects";
import { useWorkflows } from "../hooks/useWorkflows";
import { ChatBot } from "../types";

/**
 * Màn quản lý bot chat.
 *
 * Một dự án có nhiều QUY TRÌNH (fixbug, làm CR...) nên có nhiều bot — thông báo
 * của quy trình này không lẫn sang nhóm chat của quy trình kia. Bot vì thế là bộ
 * lọc hai tầng chứ không phải phân cấp cứng:
 *
 *     không chọn dự án            → hứng mọi dự án
 *     chọn dự án                  → mọi workflow của dự án đó
 *     chọn dự án + tick workflow  → chỉ những workflow đã tick
 *
 * Khi đẩy câu hỏi đi, bot khớp HẸP nhất thắng (chat_router.pick_bot).
 */

const PLATFORM_META: Record<string, { icon: string; label: string; note: string }> = {
  telegram: {
    icon: "✈️", label: "Telegram",
    note: "Không cần URL public — bot chủ động đi ra (long polling).",
  },
  slack: {
    icon: "💬", label: "Slack",
    note: "Khai App Token (xapp-…) để chạy Socket Mode — app mở kết nối đi ra, "
        + "không cần URL công khai, giống Telegram. Chỉ dùng Signing Secret khi "
        + "workspace cấm Socket Mode.",
  },
};

type Draft = {
  id: number | null;
  platform: string;
  name: string;
  token: string;
  signing_secret: string;
  app_token: string;
  chats: string;
  client_folder: string;
  workflow_ids: number[];
  enabled: boolean;
};

const emptyDraft = (platform = "telegram"): Draft => ({
  id: null, platform, name: "", token: "", signing_secret: "", app_token: "",
  chats: "", client_folder: "", workflow_ids: [], enabled: true,
});

export default function BotsPage() {
  const [bots, setBots]       = useState<ChatBot[]>([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft]     = useState<Draft | null>(null);
  const [saving, setSaving]   = useState(false);
  const [err, setErr]         = useState<string | null>(null);
  const [msg, setMsg]         = useState<string | null>(null);
  const [testing, setTesting] = useState<number | null>(null);
  const [confirmDel, setConfirmDel] = useState<number | null>(null);

  const { projects }  = useProjects();
  const { workflows } = useWorkflows();

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/chat-bots/");
      if (res.ok) setBots(await res.json());
    } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    load();
    // Trạng thái vòng poll Telegram đổi theo thời gian thật → làm mới đều tay.
    const id = setInterval(load, 8000);
    return () => clearInterval(id);
  }, [load]);

  /** Workflow chọn được cho 1 dự án. Workflow MẪU (chưa gắn dự án) bị loại: chúng
   *  không chạy được, buộc bot vào đó thì bot im lặng mãi mãi — kiểu hỏng khó tìm
   *  nhất trong cả tính năng này. */
  const pickableWorkflows = useMemo(
    () => workflows.filter(w => w.project_id !== null && w.client_folder === draft?.client_folder),
    [workflows, draft?.client_folder],
  );

  const save = async () => {
    if (!draft) return;
    setSaving(true); setErr(null); setMsg(null);
    const body: any = {
      name: draft.name, chats: draft.chats,
      client_folder: draft.client_folder || null,
      workflow_ids: draft.workflow_ids, enabled: draft.enabled,
      token: draft.token, signing_secret: draft.signing_secret, app_token: draft.app_token,
    };
    let res: Response;
    if (draft.id === null) {
      res = await fetch("/api/chat-bots/", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, platform: draft.platform }),
      });
    } else {
      // Sửa: không chọn dự án nữa thì phải nói rõ, vì null bị coi là "không đụng tới".
      res = await fetch(`/api/chat-bots/${draft.id}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, clear_client_folder: !draft.client_folder }),
      });
    }
    if (res.ok) { setDraft(null); load(); setMsg("Đã lưu"); }
    else setErr((await res.json().catch(() => ({}))).detail || "Không lưu được");
    setSaving(false);
  };

  const test = async (id: number) => {
    setTesting(id); setErr(null); setMsg(null);
    try {
      const res  = await fetch(`/api/chat-bots/${id}/test`, { method: "POST" });
      const body = await res.json();
      if (!res.ok) setErr(body.detail || "Không thử được");
      else if (body.sent) setMsg(`Đã nhắn thử vào ${body.chat_id} bằng ${body.bot} — mở app lên xem.`);
      else setMsg(body.detail);
    } finally { setTesting(null); }
  };

  const remove = async (id: number) => {
    await fetch(`/api/chat-bots/${id}`, { method: "DELETE" });
    setConfirmDel(null); load();
  };

  const toggle = async (b: ChatBot) => {
    await fetch(`/api/chat-bots/${b.id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !b.enabled }),
    });
    load();
  };

  const startEdit = (b: ChatBot) => setDraft({
    id: b.id, platform: b.platform, name: b.name, token: "", signing_secret: "", app_token: "",
    chats: b.chats, client_folder: b.client_folder || "",
    workflow_ids: b.workflow_ids || [], enabled: b.enabled,
  });

  if (loading) return <div className="state">Đang tải bot...</div>;

  return (
    <div className="projects-page">
      <div className="page-header">
        <h2>Bots</h2>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn-primary" onClick={() => setDraft(emptyDraft("telegram"))}>
            ✈️ Thêm bot Telegram
          </button>
          <button className="btn-muted" onClick={() => setDraft(emptyDraft("slack"))}>
            💬 Thêm bot Slack
          </button>
        </div>
      </div>

      <p style={{ fontSize: 12, color: "#64748b", marginTop: -10, marginBottom: 16, lineHeight: 1.7 }}>
        Bot nhận câu hỏi của agent và trả lời ngay trên điện thoại; nhắn tin để chạy workflow.
        Mỗi bot phụ trách một <b>phạm vi</b>: cả hệ thống, một dự án, hoặc đúng vài quy trình
        của dự án đó. Khi có câu hỏi, bot khớp <b>hẹp nhất</b> được chọn — nên bot buộc vào
        workflow "Fixbug" sẽ thắng bot chung của dự án.
      </p>

      {err && <div className="state err" style={{ marginBottom: 12 }}>{err}</div>}
      {msg && <div className="settings-msg ok" style={{ marginBottom: 12 }}>{msg}</div>}

      {draft && (
        <BotForm
          draft={draft} setDraft={setDraft} onSave={save} onCancel={() => { setDraft(null); setErr(null); }}
          saving={saving} projects={projects} workflows={pickableWorkflows}
        />
      )}

      {bots.length === 0 && !draft ? (
        <div className="card" style={{ textAlign: "center", color: "#64748b", fontSize: 13, lineHeight: 1.8 }}>
          Chưa có bot nào.<br />
          Bắt đầu với <b>Telegram</b> — nhắn <code>@BotFather</code> → <code>/newbot</code> → dán token vào đây.
          Không cần URL public, chạy được ngay trên máy này.
        </div>
      ) : (
        <div className="project-grid" style={{ gridTemplateColumns: "1fr" }}>
          {bots.map(b => (
            <BotRow key={b.id} bot={b} onEdit={() => startEdit(b)} onToggle={() => toggle(b)}
              onTest={() => test(b.id)} testing={testing === b.id}
              confirming={confirmDel === b.id} onAskDelete={() => setConfirmDel(b.id)}
              onCancelDelete={() => setConfirmDel(null)} onDelete={() => remove(b.id)} />
          ))}
        </div>
      )}
    </div>
  );
}

function BotRow({ bot, onEdit, onToggle, onTest, testing, confirming,
                 onAskDelete, onCancelDelete, onDelete }: {
  bot: ChatBot; onEdit: () => void; onToggle: () => void; onTest: () => void;
  testing: boolean; confirming: boolean;
  onAskDelete: () => void; onCancelDelete: () => void; onDelete: () => void;
}) {
  const meta = PLATFORM_META[bot.platform] || PLATFORM_META.telegram;
  const dot = !bot.enabled ? { c: "#64748b", t: "đã tắt" }
    : bot.mode === "webhook" ? { c: "#93c5fd", t: "chờ webhook" }
    : bot.running ? { c: "#22c55e", t: bot.me ? `đang chạy · @${bot.me}` : "đang chạy" }
    : { c: "#f87171", t: bot.last_error ? "lỗi" : "chưa nối" };

  return (
    <div className="card" style={{ padding: 16, opacity: bot.enabled ? 1 : 0.6 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontSize: 18 }}>{meta.icon}</span>
        <strong style={{ fontSize: 15 }}>{bot.name}</strong>
        <span className="pd-slug">{bot.scope_label}</span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: dot.c }}>
          <span style={{ width: 8, height: 8, borderRadius: 4, background: dot.c }} />{dot.t}
        </span>
        <div style={{ flex: 1 }} />
        <button className="pd-ghost-btn" onClick={onTest} disabled={testing}>
          {testing ? "Đang thử..." : "Thử"}
        </button>
        <button className="pd-ghost-btn" onClick={onToggle}>{bot.enabled ? "Tắt" : "Bật"}</button>
        <button className="pd-ghost-btn" onClick={onEdit}>Sửa</button>
        {confirming ? (
          <>
            <button className="pd-ghost-btn danger" onClick={onDelete}>Xoá thật</button>
            <button className="pd-ghost-btn" onClick={onCancelDelete}>Thôi</button>
          </>
        ) : (
          <button className="pd-ghost-btn danger" onClick={onAskDelete}>Xoá</button>
        )}
      </div>

      <div style={{ fontSize: 12, color: "#64748b", marginTop: 8, lineHeight: 1.8 }}>
        <span>Token <code style={{ color: "#93c5fd" }}>{bot.token_hint || "chưa có"}</code></span>
        <span style={{ margin: "0 8px", color: "#334155" }}>·</span>
        <span>{bot.chats ? `Chat: ${bot.chats}` : <b style={{ color: "#d97706" }}>chưa khai chat — bot sẽ không gửi cho ai</b>}</span>
        {bot.platform === "slack" && (
          <div style={{ marginTop: 4 }}>
            {bot.mode === "socket" ? (
              <span style={{ color: "#4ade80" }}>
                🔌 Socket Mode — kết nối đi ra, không cần URL công khai
              </span>
            ) : bot.mode === "webhook" ? (
              <>Request URL: <code style={{ color: "#93c5fd" }}>{"<url-công-khai>"}{bot.request_path}</code></>
            ) : (
              <b style={{ color: "#d97706" }}>Chưa khai App Token lẫn Signing Secret — bot không nhận được sự kiện nào</b>
            )}
            {!bot.has_token && <b style={{ color: "#d97706" }}> · thiếu Bot Token, không trả lời được</b>}
          </div>
        )}
        {bot.stale_workflow_ids?.length > 0 && (
          <div style={{ marginTop: 4, color: "#d97706" }}>
            ⚠ Workflow {bot.stale_workflow_ids.join(", ")} đã bị xoá — sửa lại phạm vi cho đúng.
          </div>
        )}
        {bot.last_error && <div style={{ marginTop: 4, color: "#f87171" }}>{bot.last_error}</div>}
      </div>
    </div>
  );
}

function BotForm({ draft, setDraft, onSave, onCancel, saving, projects, workflows }: {
  draft: Draft; setDraft: (d: Draft) => void; onSave: () => void; onCancel: () => void;
  saving: boolean; projects: { id: string; name: string }[];
  workflows: { id: number; name: string }[];
}) {
  const meta = PLATFORM_META[draft.platform] || PLATFORM_META.telegram;
  const set = (patch: Partial<Draft>) => setDraft({ ...draft, ...patch });
  const isNew = draft.id === null;

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h3 style={{ fontSize: 15, marginBottom: 4 }}>
        {meta.icon} {isNew ? `Bot ${meta.label} mới` : `Sửa bot ${draft.name}`}
      </h3>
      <p style={{ fontSize: 12, color: "#64748b", marginBottom: 14 }}>{meta.note}</p>

      <div className="np-grid">
        <div className="np-field">
          <label className="setting-label">Tên bot</label>
          <input className="setting-input" placeholder="vd: Fixbug, CR, Thông báo chung"
            value={draft.name} onChange={e => set({ name: e.target.value })} />
          <div className="np-hint">Chỉ để bạn nhận ra — không hiện ra cho người trong chat.</div>
        </div>

        <div className="np-field">
          <label className="setting-label">
            {draft.platform === "telegram" ? "Chat được phép" : "Kênh được phép"}
          </label>
          <input className="setting-input"
            placeholder={draft.platform === "telegram" ? "123456789, -100987654321" : "#fixbug, #dev"}
            value={draft.chats} onChange={e => set({ chats: e.target.value })} />
          <div className="np-hint">
            Cách nhau dấu phẩy. Chưa biết id? Lưu bot trước, rồi nhắn <code>/id</code> cho nó.
          </div>
        </div>

        <div className="np-field">
          <label className="setting-label">Bot token {!isNew && "(để trống = giữ nguyên)"}</label>
          <input className="setting-input" type="password"
            placeholder={draft.platform === "telegram" ? "123456:ABC-DEF…" : "xoxb-…"}
            value={draft.token} onChange={e => set({ token: e.target.value })} />
          <div className="np-hint">
            {draft.platform === "telegram"
              ? <>Lấy ở <code>@BotFather</code> → <code>/newbot</code>.</>
              : <>Slack App → OAuth &amp; Permissions.</>}
          </div>
        </div>

        {draft.platform === "slack" && (
          <>
            <div className="np-field">
              <label className="setting-label">App token — Socket Mode {!isNew && "(để trống = giữ nguyên)"}</label>
              <input className="setting-input" type="password" placeholder="xapp-…"
                value={draft.app_token} onChange={e => set({ app_token: e.target.value })} />
              <div className="np-hint">
                <b>Cách nên dùng.</b> Slack App → Basic Information → App-Level Tokens →
                Generate, chọn scope <code>connections:write</code>. Bật <b>Socket Mode</b> trong
                app. Có cái này thì <b>không cần URL công khai</b> và không cần Signing Secret.
              </div>
            </div>
            <div className="np-field">
              <label className="setting-label">Signing secret — webhook {!isNew && "(để trống = giữ nguyên)"}</label>
              <input className="setting-input" type="password" placeholder="32 ký tự hex — chỉ khi KHÔNG dùng Socket Mode"
                value={draft.signing_secret} onChange={e => set({ signing_secret: e.target.value })} />
              <div className="np-hint">
                Chỉ cần khi workspace cấm Socket Mode. Lấy ở Basic Information → <b>App Credentials</b>
                → Signing Secret (32 ký tự hex, <b>không</b> phải <code>xapp-</code> hay <code>xoxb-</code>).
                Dùng cách này thì dashboard phải có URL HTTPS công khai.
              </div>
            </div>
          </>
        )}
      </div>

      <div className="np-section" style={{ marginTop: 14 }}>
        <div className="np-section-title">Phạm vi — bot này phụ trách gì</div>

        <div className="np-field">
          <label className="setting-label">Dự án</label>
          <select className="setting-select" style={{ width: "100%" }}
            value={draft.client_folder}
            onChange={e => set({ client_folder: e.target.value, workflow_ids: [] })}>
            <option value="">Mọi dự án (bot hứng tất cả)</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.name} — {p.id}</option>)}
          </select>
        </div>

        {draft.client_folder && (
          <div className="np-field" style={{ marginTop: 10 }}>
            <label className="setting-label">Quy trình (workflow)</label>
            {workflows.length === 0 ? (
              <div className="np-hint">
                Dự án này chưa có workflow nào chạy được. Bot sẽ phụ trách cả dự án.
              </div>
            ) : (
              <>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 4 }}>
                  {workflows.map(w => {
                    const on = draft.workflow_ids.includes(w.id);
                    return (
                      <button key={w.id} type="button"
                        className={"pd-ghost-btn" + (on ? " danger" : "")}
                        style={on ? { color: "#93c5fd", borderColor: "#2563eb", background: "#172554" } : undefined}
                        onClick={() => set({
                          workflow_ids: on ? draft.workflow_ids.filter(i => i !== w.id)
                                           : [...draft.workflow_ids, w.id],
                        })}>
                        {on ? "✓ " : ""}{w.name}
                      </button>
                    );
                  })}
                </div>
                <div className="np-hint" style={{ marginTop: 6 }}>
                  Không tick cái nào = <b>cả dự án</b>. Tick 1 cái = chỉ quy trình đó —
                  đúng cho kiểu "bot Fixbug" và "bot CR" riêng. Workflow mẫu (chưa gắn dự án)
                  không hiện ở đây vì chúng không chạy được.
                </div>
              </>
            )}
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: 8, marginTop: 16, alignItems: "center" }}>
        <button className="btn-primary" onClick={onSave}
          disabled={saving || !draft.name.trim() || (isNew && !draft.token.trim())}>
          {saving ? "Đang lưu..." : isNew ? "Tạo bot" : "Lưu"}
        </button>
        <button className="btn-muted" onClick={onCancel}>Huỷ</button>
        <label className="setting-checkbox-label" style={{ marginLeft: 8 }}>
          <input type="checkbox" checked={draft.enabled}
            onChange={e => set({ enabled: e.target.checked })} />
          <span className="setting-checkbox-text">Bật</span>
        </label>
      </div>
    </div>
  );
}
