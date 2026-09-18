import React, { useCallback, useEffect, useState } from "react";
import { useSettings } from "../hooks/useSettings";
import { useWorkerStatus, type ClaudeAccountState } from "../hooks/useWorkflows";

const SETTING_KEYS = {
  aiProvider:    { key: "ai_provider",    label: "AI Provider",         type: "select", options: ["openai", "anthropic", "google", "local"], fallback: "openai" },
  aiModel:       { key: "ai_model",       label: "AI Model",           type: "text",   fallback: "gpt-4o" },
  apiKey:        { key: "api_key",        label: "API Key",            type: "password", fallback: "" },
  maxConcurrent: { key: "max_concurrent", label: "Max Concurrent",      type: "number", fallback: "3" },
  autoClose:     { key: "auto_close_run", label: "Auto-close run",     type: "checkbox", fallback: "true" },
  refreshMs:     { key: "refresh_ms",     label: "Refresh interval (ms)", type: "number", fallback: "3000" },
  runTimeout:    { key: "run_timeout_m",  label: "Run timeout (min)",   type: "number", fallback: "30" },
} as const;

export default function Settings() {
  const { getValue, saveSetting, saving, msg } = useSettings();
  const [showKey, setShowKey] = useState(false);

  const Field = ({ meta }: { meta: (typeof SETTING_KEYS)[keyof typeof SETTING_KEYS] }) => {
    const current = getValue(meta.key, meta.fallback);
    const [val, setVal] = useState(current);

    const handleSave = () => saveSetting(meta.key, val);
    const dirty = val !== current;

    return (
      <div className="setting-row">
        <label className="setting-label">{meta.label}</label>
        <div className="setting-input-group">
          {meta.type === "select" ? (
            <select className="setting-select" value={val} onChange={e => setVal(e.target.value)}>
              {meta.options.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          ) : meta.type === "checkbox" ? (
            <label className="setting-checkbox-label">
              <input type="checkbox" checked={val === "true"} onChange={e => setVal(e.target.checked ? "true" : "false")} />
              <span className="setting-checkbox-text">Enabled</span>
            </label>
          ) : meta.type === "password" ? (
            <div className="setting-password-wrap">
              <input type={showKey ? "text" : "password"} className="setting-input" value={val} onChange={e => setVal(e.target.value)}
                placeholder="sk-..." />
              <button type="button" className="setting-toggle-pw" onClick={() => setShowKey(!showKey)}>
                {showKey ? "Hide" : "Show"}
              </button>
            </div>
          ) : (
            <input type={meta.type} className="setting-input" value={val} onChange={e => setVal(e.target.value)} />
          )}
          <button className={`setting-save-btn ${dirty ? "dirty" : ""}`} disabled={!dirty || saving} onClick={handleSave}>
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="settings-page">
      <div className="settings-stack">
      <div className="settings-card">
        <h2 className="settings-title">Team Settings</h2>
        <p className="settings-sub">Configure AI provider, model, and runtime options.</p>

        <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8,
                      padding: "10px 14px", marginBottom: 16, fontSize: 12, color: "#9ca3af", lineHeight: 1.7 }}>
          <strong style={{ color: "#e2e8f0" }}>Bot Telegram / Slack chuyển sang tab “Bots”.</strong>{" "}
          Để riêng vì một dự án có nhiều quy trình (fixbug, làm CR…) nên cần nhiều bot, mỗi bot
          buộc vào một hoặc vài workflow — không nhét vừa một ô cấu hình ở đây.
        </div>

        {Object.values(SETTING_KEYS).map(meta => (
          <Field key={meta.key} meta={meta} />
        ))}

        {msg && (
          <div className={`settings-msg ${msg === "Saved" ? "ok" : "err"}`}>
            {msg}
          </div>
        )}
      </div>

      <ClaudeAccountsCard
        chosen={getValue("claude_account", "")}
        autoSwitch={getValue("claude_auto_switch", "true") !== "false"}
        saving={saving}
        onChoose={name => saveSetting("claude_account", name)}
        onAutoSwitch={on => saveSetting("claude_auto_switch", on ? "true" : "false")}
      />
      </div>
    </div>
  );
}

// ── Tài khoản Claude ──────────────────────────────────────────────────────────
// Worker trên host cầm token của từng tài khoản Pro (config/claude_accounts.local.toml)
// và báo tên + trạng thái lên qua heartbeat. Ở đây chỉ chọn TÊN — lưu Setting
// `claude_account`; worker đọc lúc claim nên bước KẾ TIẾP dùng ngay, bước đang
// chạy giữ nguyên. Không có worker/không có file → chỉ hướng dẫn, không lỗi.

const ACC_STATE: Record<ClaudeAccountState["state"], { icon: string; label: string }> = {
  ready:   { icon: "🟢", label: "sẵn sàng" },
  cooling: { icon: "⏳", label: "hết quota, nghỉ tới" },
  error:   { icon: "🔴", label: "lỗi" },
};

function fmtUntil(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const hm = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const today = d.toDateString() === new Date().toDateString();
  return today ? hm : `${hm} ${d.toLocaleDateString()}`;
}

function ClaudeAccountsCard({ chosen, autoSwitch, saving, onChoose, onAutoSwitch }: {
  chosen: string;
  autoSwitch: boolean;
  saving: boolean;
  onChoose: (name: string) => void;
  onAutoSwitch: (on: boolean) => void;
}) {
  const worker = useWorkerStatus(true);
  const online = worker?.online ?? false;
  // Snapshot chỉ mới khi worker hỏi việc — đang chạy 1 bước dài thì nó im. Mốc
  // "nghỉ tới" đã qua thì coi như sẵn sàng thay vì hiện giờ cũ.
  const accounts = (worker?.accounts ?? []).map(a =>
    a.state === "cooling" && a.until && Date.parse(a.until) < Date.now() ? { ...a, state: "ready" as const, until: null } : a);
  // Đang chọn 1 tên không còn trong file (xoá/đổi tên) → nói rõ worker sẽ tự lấy tài khoản đầu tiên
  const chosenMissing = chosen !== "" && !accounts.some(a => a.name === chosen);
  const lastSeen = worker?.last_seen ? fmtUntil(worker.last_seen.endsWith("Z") ? worker.last_seen : worker.last_seen + "Z") : "";

  return (
    <div className="settings-card">
      <h2 className="settings-title">Tài khoản Claude</h2>
      <p className="settings-sub">
        Bước workflow chạy headless dùng tài khoản nào. Đổi ở đây áp cho bước kế tiếp — không cần vào terminal.
      </p>

      {!online && (
        <div className="claude-acc-hint">
          ○ Worker chưa hỏi việc{worker?.silent_s != null ? ` ${worker.silent_s}s` : ""} — đang bận 1 bước, hoặc chưa chạy
          (<code>python worker.py</code>). Danh sách bên dưới là lần báo gần nhất{lastSeen ? ` lúc ${lastSeen}` : ""}.
        </div>
      )}
      {online && accounts.length === 0 && (
        <div className="claude-acc-hint">
          Worker chưa có tài khoản nào. Chép <code>config/claude_accounts.example.toml</code> thành{" "}
          <code>config/claude_accounts.local.toml</code>, chạy <code>claude setup-token</code> cho từng tài khoản Pro
          rồi dán token vào. Không cần khởi động lại worker. Chưa có file thì worker dùng đăng nhập trong <code>~/.claude</code> như cũ.
        </div>
      )}

      {(accounts.length > 0 || chosen !== "") && (
        <div className="claude-acc-list">
          <label className={`claude-acc-row ${chosen === "" ? "chosen" : ""}`}>
            <input type="radio" name="claude_account" checked={chosen === ""} disabled={saving}
                   onChange={() => onChoose("")} />
            <span className="claude-acc-name">Tự động</span>
            <span className="claude-acc-state">tài khoản sẵn sàng đầu tiên theo thứ tự file</span>
          </label>
          {accounts.map(a => {
            const st = ACC_STATE[a.state] ?? ACC_STATE.error;
            return (
              <label key={a.name} className={`claude-acc-row ${chosen === a.name ? "chosen" : ""}`}
                     title={a.note ?? undefined}>
                <input type="radio" name="claude_account" checked={chosen === a.name} disabled={saving}
                       onChange={() => onChoose(a.name)} />
                <span className="claude-acc-name">{a.name}</span>
                <span className={`claude-acc-state ${a.state}`}>
                  {st.icon} {st.label}{a.state === "cooling" ? ` ${fmtUntil(a.until)}` : ""}
                  {a.state === "error" && a.note ? ` — ${a.note}` : ""}
                </span>
              </label>
            );
          })}
        </div>
      )}
      {chosenMissing && (
        <div className="claude-acc-hint warn">
          Đang chọn “{chosen}” nhưng worker không báo có tài khoản này — worker sẽ dùng tài khoản sẵn sàng đầu tiên.
          Chọn “Tự động” ở trên để bỏ.
        </div>
      )}

      <label className="setting-checkbox-label claude-acc-auto">
        <input type="checkbox" checked={autoSwitch} disabled={saving} onChange={e => onAutoSwitch(e.target.checked)} />
        <span className="setting-checkbox-text">
          Tự chuyển tài khoản khi hết quota
          <span className="claude-acc-sub"> — chạy lại ngay bằng tài khoản kế tiếp nếu Claude chưa gọi tool nào (chưa đọc/sửa gì);
          đã gọi rồi thì bước báo lỗi kèm tên tài khoản kế tiếp để bạn bấm chạy lại. Tắt: chỉ dùng đúng tài khoản đã chọn.</span>
        </span>
      </label>
    </div>
  );
}
