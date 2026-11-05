#!/usr/bin/env node
/**
 * figma — MCP server CHỈ ĐỌC, nối thẳng Figma REST API bằng token của từng dự án
 * ===============================================================================
 *
 * Không đi qua connector của tài khoản Claude: mỗi dự án dán personal access token
 * Figma của mình ở tab MCP (dashboard → routers/figma_connect.py), token nằm trong
 * clients/<slug>/secrets/figma-<server>.json, worker đưa ĐƯỜNG DẪN qua env
 * FIGMA_TOKEN_PATH. Dự án khác không thấy token này.
 *
 * Tool (đều chỉ đọc phía Figma):
 *   figma-get-file     cây trang → frame của 1 file (để biết node nào cần xem)
 *   figma-get-node     chi tiết 1 hay vài node: layout, màu, chữ, font, bo góc…
 *   figma-render-image xuất node ra PNG/SVG/JPG, LƯU VỀ MÁY trong thư mục làm việc
 *                      — agent mở ảnh bằng Read để nhìn thiết kế
 *   figma-get-comments comment trên file (khách góp ý gì)
 * Mọi tool nhận `url` (dán thẳng link Figma, có ?node-id=…) hoặc fileKey + nodeIds.
 *
 * Thư viện: MCP SDK dùng lại bản đã cài ở vendor/mcp/google-drive-mcp. Gọi HTTP bằng
 * fetch có sẵn của Node ≥ 18 — không cài thêm gì.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const { fileURLToPath } = require("url");
const { createRequire } = require("module");

const DEPS = process.env.MCP_SDK_DEPS ||
  path.join(__dirname, "..", "..", "vendor", "mcp", "google-drive-mcp", "package.json");
const need = createRequire(DEPS);
const { McpServer } = need("@modelcontextprotocol/sdk/server/mcp.js");
const { StdioServerTransport } = need("@modelcontextprotocol/sdk/server/stdio.js");
const { z } = need("zod");

const API = "https://api.figma.com/v1";
// Tương đối thì tính từ gốc ai_team, không phải cwd (cwd = thư mục code của dự án).
const AI_TEAM_ROOT = path.join(__dirname, "..", "..");
const TOKEN_RAW = process.env.FIGMA_TOKEN_PATH || "";
const TOKEN_PATH = TOKEN_RAW && !path.isAbsolute(TOKEN_RAW) ? path.join(AI_TEAM_ROOT, TOKEN_RAW) : TOKEN_RAW;
const MAX_TEXT_CHARS = 120_000;

let token = null;
function getToken() {
  if (token) return token;
  if (!TOKEN_PATH) throw new Error("Dự án chưa kết nối Figma — vào tab MCP của dự án, mục server Figma, dán token.");
  const data = JSON.parse(fs.readFileSync(TOKEN_PATH, "utf8"));
  if (!data.token) throw new Error("File token Figma hỏng — kết nối lại ở tab MCP.");
  token = data.token;
  return token;
}

async function figma(pathAndQuery) {
  const res = await fetch(API + pathAndQuery, { headers: { "X-Figma-Token": getToken() } });
  const text = await res.text();
  if (!res.ok) {
    let msg = text;
    try { msg = JSON.parse(text).err || JSON.parse(text).message || text; } catch (_) {}
    if (res.status === 403) msg += " — token hết hạn/bị thu hồi, hoặc tài khoản Figma này không xem được file. Kết nối lại hoặc nhờ chủ file share.";
    if (res.status === 404) msg += " — sai file key, hoặc file không share cho tài khoản Figma đã kết nối.";
    if (res.status === 429) msg += " — Figma giới hạn tốc độ, đợi 1 phút rồi thử lại.";
    throw new Error(`Figma ${res.status}: ${msg}`);
  }
  return JSON.parse(text);
}

// ── Link Figma → fileKey + node id ──────────────────────────────────────────

/** https://www.figma.com/design/<key>/<tên>?node-id=12-34 → {fileKey, nodeIds:["12:34"]}.
 *  Nhận cả /file/, /proto/, /board/. node-id trên URL dùng '-' còn API dùng ':'. */
function parseTarget({ url, fileKey, nodeIds }) {
  let key = fileKey, ids = nodeIds || [];
  if (url) {
    const m = String(url).match(/figma\.com\/(?:design|file|proto|board|make)\/([A-Za-z0-9]+)/);
    if (!m) throw new Error("Link không phải link file Figma (cần dạng figma.com/design/<key>/…).");
    key = key || m[1];
    const nid = new URL(url).searchParams.get("node-id");
    if (nid && !ids.length) ids = [nid];
  }
  if (!key) throw new Error("Thiếu url hoặc fileKey.");
  return { fileKey: key, nodeIds: ids.map(i => String(i).replace(/-/g, ":")) };
}

// ── Rút gọn node: giữ thứ người dựng UI cần, bỏ phần nặng vô ích ────────────

function hex({ r, g, b }, a = 1) {
  const h = v => Math.round(v * 255).toString(16).padStart(2, "0");
  return "#" + h(r) + h(g) + h(b) + (a < 1 ? h(a) : "");
}

function paints(list) {
  return (list || []).filter(p => p.visible !== false).map(p =>
    p.type === "SOLID" ? hex(p.color, (p.opacity ?? 1) * (p.color.a ?? 1))
      : p.type === "IMAGE" ? `image(${p.scaleMode || "FILL"})`
      : p.type.startsWith("GRADIENT") ? `${p.type.toLowerCase()}(${(p.gradientStops || []).map(s => hex(s.color, s.color.a)).join(", ")})`
      : p.type);
}

function slim(n, depth) {
  const o = { id: n.id, name: n.name, type: n.type };
  const bb = n.absoluteBoundingBox;
  if (bb) o.box = { x: Math.round(bb.x), y: Math.round(bb.y), w: Math.round(bb.width), h: Math.round(bb.height) };
  if (n.visible === false) o.hidden = true;
  const fills = paints(n.fills); if (fills.length) o.fills = fills;
  const strokes = paints(n.strokes); if (strokes.length) o.strokes = { colors: strokes, weight: n.strokeWeight };
  if (n.cornerRadius) o.radius = n.cornerRadius;
  if (n.rectangleCornerRadii) o.radius = n.rectangleCornerRadii;
  if (n.opacity !== undefined && n.opacity < 1) o.opacity = n.opacity;
  if (n.layoutMode && n.layoutMode !== "NONE") {
    o.layout = {
      mode: n.layoutMode, gap: n.itemSpacing,
      padding: [n.paddingTop || 0, n.paddingRight || 0, n.paddingBottom || 0, n.paddingLeft || 0],
      align: n.primaryAxisAlignItems, crossAlign: n.counterAxisAlignItems, wrap: n.layoutWrap,
    };
  }
  if (n.layoutSizingHorizontal) o.sizing = [n.layoutSizingHorizontal, n.layoutSizingVertical];
  const fx = (n.effects || []).filter(e => e.visible !== false)
    .map(e => `${e.type}(${e.offset ? e.offset.x + "," + e.offset.y : ""} r${e.radius}${e.color ? " " + hex(e.color, e.color.a) : ""})`);
  if (fx.length) o.effects = fx;
  if (n.type === "TEXT") {
    o.text = n.characters;
    const s = n.style || {};
    o.font = { family: s.fontFamily, size: s.fontSize, weight: s.fontWeight, lineHeight: s.lineHeightPx && Math.round(s.lineHeightPx),
               letterSpacing: s.letterSpacing || undefined, align: s.textAlignHorizontal, case: s.textCase };
  }
  if (n.componentId) o.componentId = n.componentId;
  if (n.children?.length) {
    o.children = depth > 0 ? n.children.map(c => slim(c, depth - 1)) : `${n.children.length} node con (tăng depth để xem)`;
  }
  return o;
}

function cut(text) {
  return text.length > MAX_TEXT_CHARS
    ? text.slice(0, MAX_TEXT_CHARS) + `\n…(đã cắt ${text.length - MAX_TEXT_CHARS} ký tự — xem node nhỏ hơn hoặc giảm depth)`
    : text;
}

// ── Hàng rào đường dẫn cho ảnh lưu về máy (giống gdrive_files) ──────────────

const server = new McpServer({ name: "figma", version: "1.0.0" });

async function allowedRoots() {
  try {
    const { roots } = await server.server.listRoots();
    const out = (roots || []).filter(r => String(r.uri || "").startsWith("file://"))
      .map(r => path.resolve(fileURLToPath(r.uri)));
    if (out.length) return out;
  } catch (_) { /* client không hỗ trợ roots */ }
  return [path.resolve(process.cwd())];
}

function realOrSelf(p) { try { return fs.realpathSync.native(p); } catch (_) { return p; } }

function isInside(child, parent) {
  const rel = path.relative(parent.toLowerCase(), child.toLowerCase());
  return rel === "" || (!rel.startsWith("..") && !path.isAbsolute(rel));
}

async function guardPath(p) {
  const roots = (await allowedRoots()).map(realOrSelf);
  const abs = path.resolve(process.cwd(), p);
  const real = fs.existsSync(abs) ? realOrSelf(abs) : path.join(realOrSelf(path.dirname(abs)), path.basename(abs));
  if (!roots.some(r => isInside(real, r))) {
    throw new Error(`Đường dẫn ${abs} nằm ngoài thư mục làm việc của bước (${roots.join(", ")}).`);
  }
  return real;
}

const ok = obj => ({ content: [{ type: "text", text: typeof obj === "string" ? obj : JSON.stringify(obj, null, 1) }] });
const fail = e => ({ isError: true, content: [{ type: "text", text: e?.message || String(e) }] });

const target = {
  url: z.string().optional().describe("Link Figma (figma.com/design/<key>/…?node-id=12-34)"),
  fileKey: z.string().optional().describe("Key của file nếu không dùng url"),
  nodeIds: z.array(z.string()).optional().describe("ID node, vd ['12:34']. Bỏ trống thì lấy node-id trên url"),
};

server.registerTool("figma-get-file", {
  description: "Cây trang → frame của 1 file Figma (tên, id, kích thước). Dùng đầu tiên để biết frame nào cần xem kỹ.",
  inputSchema: { ...target, depth: z.number().int().min(1).max(4).optional().describe("Độ sâu cây, mặc định 2 (trang → frame)") },
}, async (a) => {
  try {
    const { fileKey } = parseTarget(a);
    const d = await figma(`/files/${fileKey}?depth=${a.depth || 2}`);
    const tree = (d.document.children || []).map(pg => slim(pg, (a.depth || 2) - 1));
    return ok(cut(JSON.stringify({ name: d.name, lastModified: d.lastModified, fileKey, pages: tree }, null, 1)));
  } catch (e) { return fail(e); }
});

server.registerTool("figma-get-node", {
  description: "Chi tiết node Figma để dựng UI: kích thước, auto layout (gap/padding/align), màu (hex), chữ + font, bo góc, đổ bóng, node con.",
  inputSchema: { ...target, depth: z.number().int().min(0).max(8).optional().describe("Số tầng node con, mặc định 4") },
}, async (a) => {
  try {
    const { fileKey, nodeIds } = parseTarget(a);
    if (!nodeIds.length) throw new Error("Cần nodeIds hoặc link có ?node-id=… (chuột phải frame → Copy link to selection).");
    const d = await figma(`/files/${fileKey}/nodes?ids=${encodeURIComponent(nodeIds.join(","))}`);
    const out = Object.entries(d.nodes || {}).map(([id, v]) => v ? slim(v.document, a.depth ?? 4) : { id, error: "không thấy node" });
    return ok(cut(JSON.stringify(out, null, 1)));
  } catch (e) { return fail(e); }
});

server.registerTool("figma-render-image", {
  description: "Xuất node Figma ra ảnh và LƯU VỀ MÁY (trong thư mục làm việc). Mở ảnh bằng Read để nhìn thiết kế. Không ghi đè file có sẵn.",
  inputSchema: {
    ...target,
    outDir: z.string().describe("Thư mục lưu ảnh trên máy (tạo nếu chưa có)"),
    format: z.enum(["png", "jpg", "svg"]).optional().describe("Mặc định png"),
    scale: z.number().min(0.5).max(4).optional().describe("Tỉ lệ (png/jpg), mặc định 2"),
  },
}, async (a) => {
  try {
    const { fileKey, nodeIds } = parseTarget(a);
    if (!nodeIds.length) throw new Error("Cần nodeIds hoặc link có ?node-id=….");
    const fmt = a.format || "png";
    const d = await figma(`/images/${fileKey}?ids=${encodeURIComponent(nodeIds.join(","))}&format=${fmt}&scale=${a.scale || 2}`);
    const dir = await guardPath(a.outDir);
    fs.mkdirSync(dir, { recursive: true });
    const saved = [];
    for (const [id, link] of Object.entries(d.images || {})) {
      if (!link) { saved.push({ id, error: "Figma không xuất được node này (ẩn hoặc rỗng)" }); continue; }
      const res = await fetch(link);
      if (!res.ok) { saved.push({ id, error: `tải ảnh lỗi ${res.status}` }); continue; }
      const file = path.join(dir, `figma_${id.replace(/[^0-9A-Za-z]+/g, "-")}.${fmt}`);
      if (fs.existsSync(file)) { saved.push({ id, savedTo: file, note: "đã có sẵn, không ghi đè" }); continue; }
      fs.writeFileSync(file, Buffer.from(await res.arrayBuffer()), { flag: "wx" });
      saved.push({ id, savedTo: file });
    }
    return ok(saved);
  } catch (e) { return fail(e); }
});

server.registerTool("figma-get-comments", {
  description: "Comment trên file Figma: ai viết, nội dung, gắn vào node nào, đã resolve chưa.",
  inputSchema: target,
}, async (a) => {
  try {
    const { fileKey } = parseTarget(a);
    const d = await figma(`/files/${fileKey}/comments`);
    return ok(cut(JSON.stringify((d.comments || []).map(c => ({
      by: c.user?.handle, at: c.created_at, text: c.message, node: c.client_meta?.node_id,
      resolved: Boolean(c.resolved_at), replyTo: c.parent_id || undefined,
    })), null, 1)));
  } catch (e) { return fail(e); }
});

if (require.main === module) {
  server.connect(new StdioServerTransport()).catch(e => {
    console.error("[figma] không khởi động được:", e);
    process.exit(1);
  });
} else {
  module.exports = { parseTarget, slim, hex };
}
