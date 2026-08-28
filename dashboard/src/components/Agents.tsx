import React, { useEffect, useState } from "react";
import { ConfigAgent, Profile } from "../types";

/**
 * Danh sách agent của PIPELINE — đọc thẳng từ `config/settings.toml`.
 *
 * Trước đây màn hình này hiển thị bảng `agents` trong DB: một bản sao chép tay,
 * không ai đọc (pipeline `ai_team/` chỉ đọc settings.toml) và đã lệch thật —
 * DB ghi Analyst = qwen3.6-plus trong khi settings.toml là qwen3.5-plus. Giờ chỉ
 * còn một nguồn sự thật, và màn hình này là chỗ XEM chứ không phải chỗ sửa.
 *
 * Lưu ý: đây là làn A (pipeline OpenCode chạy qua `main.py`). Bước trong Workflow
 * KHÔNG dùng những agent này — xem chú thích cuối trang.
 */

function useConfigAgents() {
  const [agents, setAgents]     = useState<ConfigAgent[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetch("/api/system/agents").then(r => r.ok ? r.json() : Promise.reject()),
      fetch("/api/system/profiles").then(r => r.ok ? r.json() : []).catch(() => []),
    ])
      .then(([a, p]) => { setAgents(a); setProfiles(p); setError(null); })
      .catch(() => setError("Không đọc được config/settings.toml"))
      .finally(() => setLoading(false));
  }, []);

  return { agents, profiles, loading, error };
}

export default function AgentsPage() {
  const { agents, profiles, loading, error } = useConfigAgents();

  if (loading) return <div className="state">Đang đọc config/settings.toml...</div>;
  if (error)   return <div className="state err">{error}</div>;

  /** Profile nào bật agent này — cho biết nó có thực sự chạy hay chỉ nằm trong config */
  const profilesOf = (key: string) =>
    profiles.filter(p => (p.agents || []).includes(key)).map(p => p.label || p.key);

  return (
    <div className="projects-page">
      <div className="page-header">
        <h2>Agents của pipeline</h2>
        <span style={{ fontSize: 12, color: "#6b7280" }}>
          nguồn: <code>config/settings.toml</code> — chỉ đọc
        </span>
      </div>

      <p style={{ fontSize: 12, color: "#9ca3af", marginTop: 0, marginBottom: 16, lineHeight: 1.6 }}>
        Đây là đội chạy <b>pipeline</b> (<code>python main.py</code> qua worker) — chỉ dùng OpenCode
        theo chính sách trong README. Sửa tool/model thì sửa <code>config/settings.toml</code>;
        muốn khác cho riêng 1 project thì vào <b>Projects → tab Agents</b> của project đó.
      </p>

      {agents.length === 0 && (
        <div className="state">Không tìm thấy agent nào trong config/settings.toml.</div>
      )}

      <div className="project-grid">
        {agents.map(a => {
          const inProfiles = profilesOf(a.key);
          const isClaude = a.tool === "claude";
          return (
            <div key={a.key} className="project-card" style={{ cursor: "default" }}>
              <div className="project-card-top">
                <span className="project-card-name">{a.name}</span>
                <span style={{
                  fontSize: 10, padding: "2px 7px", borderRadius: 10,
                  color: isClaude ? "#fca5a5" : "#86efac",
                  background: isClaude ? "#450a0a" : "#052e16",
                  border: `1px solid ${isClaude ? "#7f1d1d" : "#166534"}`,
                }} title={isClaude
                  ? "tool = claude bị chặn trong pipeline (xem README) — pipeline sẽ dừng khi load config"
                  : "công cụ chạy agent này"}>
                  {a.tool}
                </span>
              </div>
              <div style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>
                <code>{a.key}</code> · {a.model}
              </div>
              {a.description && <p className="project-card-desc">{a.description}</p>}
              <div style={{ fontSize: 11, color: "#4b5563", marginTop: 8 }}>
                {inProfiles.length > 0
                  ? <>Profile bật: {inProfiles.join(", ")}</>
                  : <>Không profile nào bật agent này</>}
              </div>
            </div>
          );
        })}
      </div>

      <div style={{
        marginTop: 24, padding: "12px 16px", borderRadius: 8,
        background: "#0b1220", border: "1px solid #1e293b", fontSize: 12,
        color: "#9ca3af", lineHeight: 1.7, maxWidth: 900,
      }}>
        <b style={{ color: "#e2e8f0" }}>Workflow không dùng những agent này.</b> Một bước trong Workflow
        sinh ra file task rồi do <b>bạn</b> chạy, hoặc do <b>Claude headless</b> chạy nếu workflow bật
        công tắc tự chạy. Cái mà node workflow chọn là <b>skill</b> (thư mục <code>skills/</code>) —
        nội dung skill được nhúng thẳng vào file task, giống cách pipeline nhét skill vào prompt agent.
      </div>
    </div>
  );
}
