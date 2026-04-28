import React, { useState } from "react";
import { useSettings } from "../hooks/useSettings";

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
      <div className="settings-card">
        <h2 className="settings-title">Team Settings</h2>
        <p className="settings-sub">Configure AI provider, model, and runtime options.</p>

        {Object.values(SETTING_KEYS).map(meta => (
          <Field key={meta.key} meta={meta} />
        ))}

        {msg && (
          <div className={`settings-msg ${msg === "Saved" ? "ok" : "err"}`}>
            {msg}
          </div>
        )}
      </div>
    </div>
  );
}
