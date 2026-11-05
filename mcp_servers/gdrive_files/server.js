#!/usr/bin/env node
/**
 * gdrive-files — MCP server nhỏ bù 2 chỗ trống của @us-all/google-drive-mcp
 * ===========================================================================
 *
 * Server kia làm việc tốt với Google Docs/Sheets nhưng:
 *   - `create-file` chỉ nhận nội dung TEXT → không tải lên được docx/xlsx/pdf/ảnh.
 *   - `read-file` đọc file Office (.docx/.xlsx) dưới dạng text → ra chữ rác.
 *
 * Server này chỉ có 3 tool, và KHÔNG có tool nào sửa/xoá/đổi quyền chia sẻ:
 *   upload-file      tải 1 file trên máy lên 1 thư mục Drive (luôn tạo file MỚI)
 *   download-file    tải 1 file Drive về máy (Google Docs/Sheets thì xuất ra docx/xlsx/pdf…)
 *   read-office-file đọc chữ trong .docx và bảng trong .xlsx ngay trên Drive
 *   (không có list/search — dùng tool của server google-workspace để tìm file id)
 *
 * Đường dẫn trên máy bị khoá trong các "roots" mà Claude Code gửi xuống (thư mục
 * làm việc của bước: cwd + --add-dir). Không có cách nào đọc/ghi file ngoài đó.
 *
 * Xác thực: đường dẫn file credential qua env GOOGLE_SERVICE_ACCOUNT_KEY_PATH (worker
 * bơm vào từ clients/<slug>/settings.local.toml). File là MỘT TRONG HAI loại, thư
 * viện google-auth tự nhận theo trường `type`:
 *   - service_account  — key tải từ Google Cloud. Chỉ ghi được vào Shared Drive.
 *   - authorized_user  — token đăng nhập của 1 người (tools/google_login.py). File
 *     tải lên thuộc về người đó, ghi thẳng vào "Drive của tôi" — dùng cho Gmail cá nhân.
 * Quyền ghi chỉ bật khi GOOGLE_DRIVE_ALLOW_WRITE=true (hồ sơ read-create, `profile_env`).
 *
 * Thư viện dùng lại bản đã cài & ghim ở vendor/mcp/google-drive-mcp — không cài
 * thêm gói nào. File này là mã của mình nên nằm trong repo, không trong vendor/.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const zlib = require("zlib");
const { fileURLToPath } = require("url");
const { createRequire } = require("module");

const DEPS = process.env.GDRIVE_FILES_DEPS ||
  path.join(__dirname, "..", "..", "vendor", "mcp", "google-drive-mcp", "package.json");
const need = createRequire(DEPS);
const { McpServer } = need("@modelcontextprotocol/sdk/server/mcp.js");
const { StdioServerTransport } = need("@modelcontextprotocol/sdk/server/stdio.js");
const { google } = need("googleapis");
const { z } = need("zod");

const ALLOW_WRITE = process.env.GOOGLE_DRIVE_ALLOW_WRITE === "true";
// Đường dẫn tương đối (vd "clients/aloweb/secrets/google-oauth-gfiles.json" do nút Kết
// nối Google ghi) tính từ GỐC ai_team, không phải từ cwd: server chạy với cwd = thư mục
// code của dự án nên resolve theo cwd sẽ ra C:\www\aloweb\clients\... (ENOENT). Worker
// mới đã tự đổi sang tuyệt đối; dòng này giữ cho đúng cả khi worker cũ chưa restart.
const AI_TEAM_ROOT = path.join(__dirname, "..", "..");
const KEY_RAW = process.env.GOOGLE_SERVICE_ACCOUNT_KEY_PATH || "";
const KEY_PATH = KEY_RAW && !path.isAbsolute(KEY_RAW) ? path.join(AI_TEAM_ROOT, KEY_RAW) : KEY_RAW;
// Đọc file Office lớn quá thì cắt — kết quả tool đi thẳng vào ngữ cảnh của model.
const MAX_TEXT_CHARS = 200_000;
const MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024;

const OFFICE_EXPORT = {
  "application/vnd.google-apps.document":
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.google-apps.spreadsheet":
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.google-apps.presentation":
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "application/vnd.google-apps.drawing": "image/png",
};
const EXT_MIME = {
  ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  ".doc": "application/msword", ".xls": "application/vnd.ms-excel",
  ".pdf": "application/pdf", ".csv": "text/csv", ".txt": "text/plain", ".md": "text/markdown",
  ".html": "text/html", ".json": "application/json", ".zip": "application/zip",
  ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
  ".svg": "image/svg+xml", ".webp": "image/webp",
};
// Tải lên kèm `convert` → Drive đổi sang định dạng Google tương ứng.
const CONVERT_TO = {
  ".docx": "application/vnd.google-apps.document", ".doc": "application/vnd.google-apps.document",
  ".txt": "application/vnd.google-apps.document", ".md": "application/vnd.google-apps.document",
  ".html": "application/vnd.google-apps.document",
  ".xlsx": "application/vnd.google-apps.spreadsheet", ".xls": "application/vnd.google-apps.spreadsheet",
  ".csv": "application/vnd.google-apps.spreadsheet",
  ".pptx": "application/vnd.google-apps.presentation",
};

let drive = null;
function getDrive() {
  if (!KEY_PATH) throw new Error("Thiếu GOOGLE_SERVICE_ACCOUNT_KEY_PATH — khai credentials_path cho server này trong clients/<slug>/settings.local.toml.");
  if (!drive) {
    const auth = new google.auth.GoogleAuth({
      keyFile: KEY_PATH,
      scopes: [ALLOW_WRITE ? "https://www.googleapis.com/auth/drive"
                           : "https://www.googleapis.com/auth/drive.readonly"],
    });
    drive = google.drive({ version: "v3", auth });
  }
  return drive;
}

// ── Hàng rào đường dẫn ───────────────────────────────────────────────────────

const server = new McpServer({ name: "gdrive-files", version: "1.0.0" });

async function allowedRoots() {
  try {
    const { roots } = await server.server.listRoots();
    const out = (roots || [])
      .filter(r => String(r.uri || "").startsWith("file://"))
      .map(r => path.resolve(fileURLToPath(r.uri)));
    if (out.length) return out;
  } catch (_) { /* client không hỗ trợ roots → dùng cwd */ }
  return [path.resolve(process.cwd())];
}

function realOrSelf(p) {
  try { return fs.realpathSync.native(p); } catch (_) { return p; }
}

function isInside(child, parent) {
  const rel = path.relative(parent.toLowerCase(), child.toLowerCase());
  return rel === "" || (!rel.startsWith("..") && !path.isAbsolute(rel));
}

/** Đường dẫn tuyệt đối đã kiểm: phải nằm trong 1 root. File chưa tồn tại (lúc tải
 *  về) thì kiểm thư mục cha thật — chặn đi vòng qua symlink. */
async function guardPath(p) {
  const roots = (await allowedRoots()).map(realOrSelf);
  const abs = path.resolve(process.cwd(), p);
  const real = fs.existsSync(abs) ? realOrSelf(abs) : path.join(realOrSelf(path.dirname(abs)), path.basename(abs));
  if (!roots.some(r => isInside(real, r))) {
    throw new Error(`Đường dẫn ${abs} nằm ngoài thư mục làm việc của bước (${roots.join(", ")}).`);
  }
  return real;
}

// ── Đọc file Office (zip + XML), không dùng thư viện ngoài ───────────────────

function unzip(buf) {
  let eocd = -1;
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 65_557); i--) {
    if (buf.readUInt32LE(i) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error("Không phải file zip (docx/xlsx hỏng hoặc là định dạng cũ .doc/.xls).");
  const count = buf.readUInt16LE(eocd + 10);
  let p = buf.readUInt32LE(eocd + 16);
  const files = {};
  for (let n = 0; n < count; n++) {
    if (buf.readUInt32LE(p) !== 0x02014b50) break;
    const method = buf.readUInt16LE(p + 10);
    const csize = buf.readUInt32LE(p + 20);
    const nameLen = buf.readUInt16LE(p + 28), extraLen = buf.readUInt16LE(p + 30), cmtLen = buf.readUInt16LE(p + 32);
    const local = buf.readUInt32LE(p + 42);
    const name = buf.toString("utf8", p + 46, p + 46 + nameLen);
    files[name] = () => {
      const start = local + 30 + buf.readUInt16LE(local + 26) + buf.readUInt16LE(local + 28);
      const raw = buf.subarray(start, start + csize);
      return (method === 8 ? zlib.inflateRawSync(raw) : raw).toString("utf8");
    };
    p += 46 + nameLen + extraLen + cmtLen;
  }
  return files;
}

function xmlText(s) {
  return s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&apos;/g, "'")
    .replace(/&#x([0-9a-f]+);/gi, (_, h) => String.fromCodePoint(parseInt(h, 16)))
    .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(+d)).replace(/&amp;/g, "&");
}

function docxText(files) {
  const xml = files["word/document.xml"];
  if (!xml) throw new Error("Không thấy word/document.xml trong file.");
  const body = xml();
  const lines = [];
  // Bảng: mỗi hàng 1 dòng, các ô cách nhau " | ". Ngoài bảng: mỗi đoạn 1 dòng.
  const paraText = p => xmlText((p.match(/<w:t[^>]*>[^<]*<\/w:t>|<w:tab\/>|<w:br\/>/g) || [])
    .map(t => t === "<w:tab/>" ? "\t" : t === "<w:br/>" ? "\n" : t.replace(/<[^>]+>/g, "")).join(""));
  const parts = body.split(/(<w:tbl>[\s\S]*?<\/w:tbl>)/);
  for (const part of parts) {
    if (part.startsWith("<w:tbl>")) {
      for (const row of part.match(/<w:tr[ >][\s\S]*?<\/w:tr>/g) || []) {
        const cells = (row.match(/<w:tc>[\s\S]*?<\/w:tc>/g) || [])
          .map(c => (c.match(/<w:p[ >][\s\S]*?<\/w:p>/g) || []).map(paraText).join(" ").trim());
        lines.push("| " + cells.join(" | ") + " |");
      }
    } else {
      for (const p of part.match(/<w:p[ >][\s\S]*?<\/w:p>/g) || []) lines.push(paraText(p));
    }
  }
  return lines.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

function colIndex(ref) {
  const letters = (ref.match(/^[A-Z]+/) || ["A"])[0];
  let n = 0;
  for (const ch of letters) n = n * 26 + (ch.charCodeAt(0) - 64);
  return n - 1;
}

function csvCell(v) {
  return /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
}

function xlsxText(files, onlySheet) {
  const shared = files["xl/sharedStrings.xml"]
    ? (files["xl/sharedStrings.xml"]().match(/<si>[\s\S]*?<\/si>/g) || [])
        .map(si => xmlText((si.match(/<t[^>]*>[^<]*<\/t>/g) || []).map(t => t.replace(/<[^>]+>/g, "")).join("")))
    : [];
  const wb = files["xl/workbook.xml"]();
  const rels = files["xl/_rels/workbook.xml.rels"]();
  const target = {};
  for (const m of rels.matchAll(/<Relationship[^>]*Id="([^"]+)"[^>]*Target="([^"]+)"/g)) target[m[1]] = m[2];
  for (const m of rels.matchAll(/<Relationship[^>]*Target="([^"]+)"[^>]*Id="([^"]+)"/g)) target[m[2]] = m[1];
  const out = [];
  for (const m of wb.matchAll(/<sheet [^>]*name="([^"]+)"[^>]*r:id="([^"]+)"/g)) {
    const name = xmlText(m[1]);
    if (onlySheet && name !== onlySheet) continue;
    let t = (target[m[2]] || "").replace(/^\/?xl\//, "").replace(/^\//, "");
    const xml = files["xl/" + t];
    if (!xml) continue;
    const rows = [];
    for (const row of xml().match(/<row[ >][\s\S]*?<\/row>/g) || []) {
      const cells = [];
      for (const c of row.match(/<c [^>]*?(?:\/>|>[\s\S]*?<\/c>)/g) || []) {
        const ref = (c.match(/ r="([A-Z]+\d+)"/) || [])[1] || "";
        const type = (c.match(/ t="([^"]+)"/) || [])[1] || "";
        let v = (c.match(/<v>([\s\S]*?)<\/v>/) || [])[1];
        if (type === "s" && v !== undefined) v = shared[+v] ?? "";
        else if (type === "inlineStr") v = (c.match(/<t[^>]*>([^<]*)<\/t>/) || [])[1] || "";
        else if (type === "b") v = v === "1" ? "TRUE" : "FALSE";
        // Công thức chưa có giá trị tính sẵn (file sinh bằng thư viện, chưa mở bằng
        // Excel) → hiện chính công thức, còn hơn ô trống khiến agent hiểu sai.
        if ((v === undefined || v === "") && /<f[ >]/.test(c)) {
          v = "=" + ((c.match(/<f[^>]*>([\s\S]*?)<\/f>/) || [])[1] || "");
        }
        cells[ref ? colIndex(ref) : cells.length] = xmlText(v ?? "");
      }
      rows.push(Array.from(cells, x => csvCell(x ?? "")).join(","));
    }
    out.push(`### Sheet: ${name}\n` + rows.join("\n"));
  }
  if (!out.length) throw new Error(onlySheet ? `Không có sheet '${onlySheet}'.` : "File không có sheet nào.");
  return out.join("\n\n");
}

// ── Gọi Drive ────────────────────────────────────────────────────────────────

async function meta(fileId) {
  const r = await getDrive().files.get({
    fileId, fields: "id,name,mimeType,size,webViewLink,parents", supportsAllDrives: true,
  });
  return r.data;
}

async function fetchBytes(m, exportMime) {
  const d = getDrive();
  if (m.mimeType.startsWith("application/vnd.google-apps.")) {
    const mime = exportMime || OFFICE_EXPORT[m.mimeType];
    if (!mime) throw new Error(`Không xuất được loại ${m.mimeType}; truyền exportMimeType (vd application/pdf).`);
    const r = await d.files.export({ fileId: m.id, mimeType: mime }, { responseType: "arraybuffer" });
    return { buf: Buffer.from(r.data), mime };
  }
  if (Number(m.size || 0) > MAX_DOWNLOAD_BYTES) throw new Error(`File quá lớn (${m.size} byte).`);
  const r = await d.files.get({ fileId: m.id, alt: "media", supportsAllDrives: true }, { responseType: "arraybuffer" });
  return { buf: Buffer.from(r.data), mime: m.mimeType };
}

function ok(obj) {
  return { content: [{ type: "text", text: typeof obj === "string" ? obj : JSON.stringify(obj, null, 2) }] };
}

function fail(e) {
  const msg = e?.response?.data?.error?.message || e?.message || String(e);
  let hint = "";
  if (/storageQuotaExceeded|storage quota/i.test(msg)) {
    hint = " — service account không có dung lượng riêng: thư mục đích phải nằm trong SHARED DRIVE. " +
      "Drive là Gmail cá nhân (không có Shared Drive) thì dev cần đăng nhập bằng tài khoản đó: " +
      "`python tools/google_login.py <dự án> <client_secret.json>` trên máy chạy worker.";
  } else if (/invalid_grant|token has been expired or revoked/i.test(msg)) {
    hint = " — token đăng nhập Google đã hết hạn hoặc bị thu hồi. Dev chạy lại " +
      "`python tools/google_login.py <dự án> <client_secret.json>` trên máy chạy worker.";
  } else if (/insufficient|permission|forbidden|not found/i.test(msg)) {
    hint = " — kiểm tra thư mục/file đã được chia sẻ cho email của service account chưa.";
  }
  return { isError: true, content: [{ type: "text", text: msg + hint }] };
}

// ── Tool ─────────────────────────────────────────────────────────────────────

server.registerTool("upload-file", {
  description: "Tải 1 file trên máy (trong thư mục làm việc) lên 1 thư mục Google Drive. Luôn tạo file MỚI, " +
    "không ghi đè. Hỗ trợ mọi loại file (docx, xlsx, pdf, ảnh, zip…). convert=true thì Drive đổi sang " +
    "Google Docs/Sheets/Slides (docx/txt/md/html→Docs, xlsx/csv→Sheets, pptx→Slides). " +
    "Thư mục đích nên nằm trong Shared Drive.",
  inputSchema: {
    localPath: z.string().describe("Đường dẫn file trên máy"),
    parentId: z.string().describe("ID thư mục Google Drive đích"),
    name: z.string().optional().describe("Tên file trên Drive. Mặc định = tên file trên máy"),
    convert: z.boolean().optional().describe("Đổi sang định dạng Google. Mặc định false (giữ nguyên file)"),
  },
}, async ({ localPath, parentId, name, convert }) => {
  try {
    if (!ALLOW_WRITE) throw new Error("Hồ sơ quyền của server này chỉ đọc — đổi sang read-create trong tab MCP của dự án.");
    const abs = await guardPath(localPath);
    if (!fs.statSync(abs).isFile()) throw new Error(`${abs} không phải file.`);
    const ext = path.extname(abs).toLowerCase();
    const requestBody = { name: name || path.basename(abs), parents: [parentId] };
    if (convert) {
      if (!CONVERT_TO[ext]) throw new Error(`Không đổi được đuôi ${ext} sang định dạng Google.`);
      requestBody.mimeType = CONVERT_TO[ext];
      if (!name) requestBody.name = path.basename(abs, ext);
    }
    const r = await getDrive().files.create({
      requestBody,
      media: { mimeType: EXT_MIME[ext] || "application/octet-stream", body: fs.createReadStream(abs) },
      fields: "id,name,mimeType,size,webViewLink,parents",
      supportsAllDrives: true,
    });
    return ok(r.data);
  } catch (e) { return fail(e); }
});

server.registerTool("download-file", {
  description: "Tải 1 file Google Drive về máy (trong thư mục làm việc). Google Docs/Sheets/Slides mặc định " +
    "xuất ra docx/xlsx/pptx; truyền exportMimeType để lấy loại khác (vd application/pdf, text/csv). " +
    "Không ghi đè file đã có.",
  inputSchema: {
    fileId: z.string().describe("ID file trên Drive"),
    localPath: z.string().describe("Đường dẫn file đích trên máy (hoặc thư mục có sẵn — giữ tên gốc)"),
    exportMimeType: z.string().optional().describe("Chỉ cho file Google Docs/Sheets/Slides"),
  },
}, async ({ fileId, localPath, exportMimeType }) => {
  try {
    const m = await meta(fileId);
    const { buf, mime } = await fetchBytes(m, exportMimeType);
    let dest = path.resolve(process.cwd(), localPath);
    if (fs.existsSync(dest) && fs.statSync(dest).isDirectory()) {
      const ext = Object.keys(EXT_MIME).find(k => EXT_MIME[k] === mime) || "";
      dest = path.join(dest, path.extname(m.name) ? m.name : m.name + ext);
    }
    dest = await guardPath(dest);
    if (fs.existsSync(dest)) throw new Error(`${dest} đã tồn tại — chọn tên khác, tool không ghi đè.`);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.writeFileSync(dest, buf, { flag: "wx" });
    return ok({ id: m.id, name: m.name, savedTo: dest, bytes: buf.length, mimeType: mime });
  } catch (e) { return fail(e); }
});

server.registerTool("read-office-file", {
  description: "Đọc nội dung file Word (.docx) hoặc Excel (.xlsx) nằm trên Google Drive — kể cả Google " +
    "Docs/Sheets. Word trả về chữ (bảng dạng | ô | ô |); Excel trả về từng sheet dạng CSV.",
  inputSchema: {
    fileId: z.string().describe("ID file trên Drive"),
    sheet: z.string().optional().describe("Chỉ đọc 1 sheet theo tên (Excel)"),
  },
}, async ({ fileId, sheet }) => {
  try {
    const m = await meta(fileId);
    const { buf, mime } = await fetchBytes(m);
    const files = unzip(buf);
    let text;
    if (/wordprocessingml/.test(mime) || files["word/document.xml"]) text = docxText(files);
    else if (/spreadsheetml/.test(mime) || files["xl/workbook.xml"]) text = xlsxText(files, sheet);
    else throw new Error(`Chưa đọc được loại ${mime}. Dùng download-file để tải về máy.`);
    const cut = text.length > MAX_TEXT_CHARS;
    return ok(`# ${m.name}\n${m.webViewLink || ""}\n\n` + text.slice(0, MAX_TEXT_CHARS) +
      (cut ? `\n\n…(đã cắt, file còn ${text.length - MAX_TEXT_CHARS} ký tự — tải về để đọc hết)` : ""));
  } catch (e) { return fail(e); }
});

if (require.main === module) {
  server.connect(new StdioServerTransport()).catch(e => {
    console.error("[gdrive-files] không khởi động được:", e);
    process.exit(1);
  });
} else {
  // Cho test: phần đọc Office kiểm được mà không cần Google.
  module.exports = { unzip, docxText, xlsxText, guardPath, isInside };
}
