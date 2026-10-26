import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Application } from "pixi.js";
import type { Live2DModel } from "pixi-live2d-display/cubism4";

/* Nhân vật Live2D (model mẫu của Live2D Inc.) cho khung Trợ lý.
   pixi + plugin Live2D (~0.7MB) và model (1–5MB) chỉ tải khi khung hiện ra thật
   (màn ≤1100px khung bị ẩn → không tải). Trong lúc tải lần đầu, máy không có WebGL,
   hoặc người dùng bật "giảm chuyển động" thì hiện `fallback` (robot SVG). */

const CORE_URL = "/live2d/live2dcubismcore.min.js";
const CHIP_SPACE = 34;            // chừa chỗ cho chip "Sẵn sàng" dưới chân
const FILL = 0.78;                // nhân vật cao bằng ngần này phần khung; phía trên để bong bóng lời chào

// Thêm nhân vật: chép thư mục model vào public/live2d/ rồi thêm 1 dòng. Model
// moc3 bản 6 (Cubism 5.3, vd mẫu "Ren") core 5.1 chưa đọc được.
export type Character = { id: string; name: string; model?: string };
export const CHARACTERS: Character[] = [
  { id: "hiyori", name: "Hiyori", model: "/live2d/hiyori/Hiyori.model3.json" },
  { id: "haru",   name: "Haru",   model: "/live2d/haru/Haru.model3.json" },
  { id: "mao",    name: "Mao",    model: "/live2d/mao/Mao.model3.json" },
  { id: "natori", name: "Natori", model: "/live2d/natori/Natori.model3.json" },
  { id: "rice",   name: "Rice",   model: "/live2d/rice/Rice.model3.json" },
  { id: "mark",   name: "Mark",   model: "/live2d/mark/Mark.model3.json" },
  { id: "wanko",  name: "Wanko",  model: "/live2d/wanko/Wanko.model3.json" },
  { id: "robot",  name: "Robot" },          // robot SVG, không tải Live2D
];
export const DEFAULT_CHARACTER = "hiyori";

declare global {
  interface Window { Live2DCubismCore?: unknown; PIXI?: unknown }
}

// Cubism Core là script toàn cục, Live2D không phát hành qua npm. Plugin cubism4
// kiểm tra nó ngay lúc import → phải nạp xong core rồi mới import plugin.
function loadCore(): Promise<void> {
  if (window.Live2DCubismCore) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = CORE_URL;
    s.onload = () => resolve();
    s.onerror = () => { s.remove(); reject(new Error("Không tải được Cubism Core")); };
    document.head.appendChild(s);
  });
}

async function createEngine() {
  await loadCore();
  const PIXI = await import("pixi.js");
  window.PIXI = PIXI;             // plugin tìm Ticker qua window.PIXI
  const { Live2DModel } = await import("pixi-live2d-display/cubism4");
  const app = new PIXI.Application({
    backgroundAlpha: 0, antialias: true, autoDensity: true, autoStart: false,
    resolution: Math.min(window.devicePixelRatio || 1, 2),
  });
  return { app, Live2DModel };
}

// Một app (1 WebGL context) cho cả trang: plugin cache shader theo context, tạo app
// mới mỗi lần mount lại sẽ vẽ lỗi ("object does not belong to this context").
// Rời trang thì chỉ gỡ canvas + dừng vẽ. Hệ quả: mỗi lúc chỉ hiện được 1 Live2DFigure.
let engine: ReturnType<typeof createEngine> | null = null;
const getEngine = () => (engine ??= createEngine().catch(err => { engine = null; throw err; }));

type Box = { x: number; y: number; w: number; h: number };
type Shown = { char: Character; model: Live2DModel; content: Box; tap: string };
let shown: Shown | null = null;   // model đang nằm trên stage
let wanted = "";                  // model được chọn gần nhất — đổi nhanh liên tục thì bỏ bản về muộn

async function showCharacter(char: Character): Promise<Shown | null> {
  wanted = char.id;
  const { app, Live2DModel } = await getEngine();
  if (shown?.char.id === char.id) return shown;
  const model = await Live2DModel.from(char.model!, { autoInteract: false });
  if (wanted !== char.id) { model.destroy(); return null; }
  if (shown) { app.stage.removeChild(shown.model); shown.model.destroy(); }
  app.stage.addChild(model);
  // Nhóm động tác khi bấm: model mẫu đặt tên "TapBody"; model không có thì dùng Idle.
  const groups = Object.keys(model.internalModel.motionManager.definitions);
  const tap = groups.includes("TapBody") ? "TapBody" : groups[0] ?? "";
  shown = { char, model, content: contentBox(model), tap };
  return shown;
}

// Vùng có hình thật của nhân vật (toạ độ model khi scale = 1). Khung model mỗi
// mẫu thừa trống khác nhau, có mẫu nhân vật lệch hẳn một bên (Rice) — canh theo
// khung thì người bé hoặc lệch, nên canh theo vùng này.
function contentBox(model: Live2DModel): Box {
  const im = model.internalModel;
  const core = im.coreModel as { getDrawableOpacity?(i: number): number };
  let l = Infinity, t = Infinity, r = -Infinity, b = -Infinity;
  im.getDrawableIDs().forEach((_, i) => {
    if ((core.getDrawableOpacity?.(i) ?? 1) < 0.01) return;
    const d = im.getDrawableBounds(i);
    if (!d.width || !d.height) return;
    l = Math.min(l, d.x); t = Math.min(t, d.y);
    r = Math.max(r, d.x + d.width); b = Math.max(b, d.y + d.height);
  });
  if (!isFinite(l)) return { x: 0, y: 0, w: model.width, h: model.height };
  const sx = model.width / im.originalWidth, sy = model.height / im.originalHeight;
  return { x: l * sx, y: t * sy, w: (r - l) * sx, h: (b - t) * sy };
}

function fit(app: Application, s: Shown, box: HTMLElement) {
  const w = box.clientWidth, h = box.clientHeight;
  if (!w || !h) return;
  app.renderer.resize(w, h);
  const avail = h - CHIP_SPACE;
  const c = s.content;
  const k = Math.min(avail * FILL / c.h, w * 0.98 / c.w);
  s.model.scale.set(k);
  s.model.x = w / 2 - (c.x + c.w / 2) * k;
  s.model.y = avail - (c.y + c.h) * k;   // chân chạm ngay trên chip
}

const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

export default function Live2DFigure({ busy, character, fallback }: {
  busy: boolean; character: Character; fallback: ReactNode;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [app, setApp] = useState<Application | null>(null);
  const [ready, setReady] = useState(false);       // đã có model trên canvas
  const [failed, setFailed] = useState(reducedMotion);

  // 1) Gắn canvas vào khung khi khung hiện ra; gỡ khi rời trang.
  useEffect(() => {
    const box = boxRef.current;
    if (!box || failed) return;
    let cancelled = false;
    let detach = () => {};

    const waitVisible = new ResizeObserver(() => {
      if (!box.clientWidth || !box.clientHeight) return;
      waitVisible.disconnect();
      getEngine().then(({ app }) => {
        if (cancelled) return;
        const canvas = app.view;
        canvas.className = "ah-l2d-canvas";
        box.appendChild(canvas);
        const ro = new ResizeObserver(() => shown && fit(app, shown, box));
        ro.observe(box);
        // Mắt + đầu nhìn theo chuột trên cả trang, không chỉ khi chuột nằm trên canvas.
        const onMove = (e: PointerEvent) => {
          const r = canvas.getBoundingClientRect();
          shown?.model.focus(e.clientX - r.left, e.clientY - r.top);
        };
        const onTap = (e: PointerEvent) => {
          const r = canvas.getBoundingClientRect();
          if (shown?.model.getBounds().contains(e.clientX - r.left, e.clientY - r.top)) shown.model.motion(shown.tap);
        };
        window.addEventListener("pointermove", onMove);
        canvas.addEventListener("pointerdown", onTap);
        app.start();
        setApp(app);
        detach = () => {
          ro.disconnect();
          window.removeEventListener("pointermove", onMove);
          canvas.removeEventListener("pointerdown", onTap);
          app.stop();
          canvas.remove();
        };
      }).catch(err => {
        console.warn("[live2d]", err);
        if (!cancelled) setFailed(true);
      });
    });
    waitVisible.observe(box);

    return () => {
      cancelled = true;
      waitVisible.disconnect();
      detach();
    };
  }, [failed]);

  // 2) Nạp nhân vật được chọn. Model cũ vẫn hiện tới khi model mới tải xong.
  useEffect(() => {
    if (!app || !character.model) return;
    let cancelled = false;
    showCharacter(character).then(s => {
      if (cancelled || !s || !boxRef.current) return;
      fit(app, s, boxRef.current);
      setReady(true);
    }).catch(err => {
      // Hỏng riêng model này (file thiếu/không đọc được) → hiện robot SVG, vẫn
      // đổi sang nhân vật khác được.
      console.warn("[live2d]", character.id, err);
      if (!cancelled) setReady(false);
    });
    return () => { cancelled = true; };
  }, [app, character]);

  // Bắt đầu trả lời → nhân vật làm một động tác, báo hiệu đã nhận câu hỏi.
  useEffect(() => {
    if (busy && ready) shown?.model.motion(shown.tap);
  }, [busy, ready]);

  return (
    <>
      {!ready && fallback}
      {!failed && (
        <div ref={boxRef} className={`ah-l2d ${ready ? "on" : ""}`} title="Bấm vào nhân vật để chào" />
      )}
    </>
  );
}
