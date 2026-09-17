import { createSingaporeCanvas } from "../lib/index.js";
import type { BasemapKind, CircleStyle, LightingPreset, TimedSample } from "../lib/index.js";
import { circleBounds, framePose } from "./decision-model.js";
import { mountMilitary } from "./military.js";
import type { Grade, Option } from "./decision-model.js";

export interface InspectorContent {
  eyebrow: string;
  title: string;
  colour: string;
  pinned: boolean;
  /** `grade` colours a figure; `urgency` (0–1) reddens a countdown as it runs out. */
  rows: readonly { label: string; value: string; grade?: Grade | null; urgency?: number }[];
}

export interface Inspector {
  /** The window's own areas are built. */
  readonly ready: Promise<void>;
  /** Shows the window framed on `option`, or just refreshes the stats if it is already shown. */
  open(option: Option, content: InspectorContent): void;
  close(): void;
  setBasemap(kind: BasemapKind): void;
  setLighting(preset: LightingPreset): void;
  syncTime(t: Date): void;
  setCircleStyles(styles: ReadonlyMap<string, CircleStyle>): void;
  dispose(): void;
}

const PITCH = -70;

const ignoreCancel = (err: unknown): void => {
  if (!(err instanceof Error && err.name === "FlightCancelled")) throw err;
};

/**
 * The side window: a second, independent canvas zoomed onto one area, plus its
 * stats. Built once in Standby. While hidden its canvas has zero size, so Cesium
 * skips rendering it; Google tiles only load while it is open.
 */
export async function mountInspector(setup: {
  keys: { ionToken?: string; googleApiKey?: string };
  basemap: BasemapKind;
  lighting: LightingPreset;
  samples: readonly TimedSample[];
  range: readonly [Date, Date];
  options: readonly Option[];
  onUnpin(): void;
}): Promise<Inspector> {
  const root = document.createElement("aside");
  root.id = "inspector";
  root.setAttribute("aria-label", "Area inspector");
  root.innerHTML = `<header><span class="eyebrow"></span><button type="button" class="unpin">Unpin</button></header>
    <h2><i></i><span></span></h2><div class="inspector-map"></div><dl></dl>`;
  // Laid out but invisible until its areas are built: a display:none canvas never
  // renders, and a canvas that never renders never builds its primitives.
  root.style.visibility = "hidden";
  document.body.append(root);
  const eyebrow = root.querySelector<HTMLElement>(".eyebrow")!;
  const unpin = root.querySelector<HTMLButtonElement>(".unpin")!;
  const swatch = root.querySelector<HTMLElement>("h2 i")!;
  const title = root.querySelector<HTMLElement>("h2 span")!;
  const mapEl = root.querySelector<HTMLElement>(".inspector-map")!;
  const dl = root.querySelector<HTMLElement>("dl")!;
  unpin.onclick = () => setup.onUnpin();

  // Tile detail scales with canvas height, so this small window would only load
  // the coarse building tiles; 2 brings in every building the main map has.
  const detail = { lighting: setup.lighting, maximumScreenSpaceError: 2 };
  const canvas = await createSingaporeCanvas(mapEl, { ...setup.keys, basemap: setup.basemap, ...detail })
    .catch(() => createSingaporeCanvas(mapEl, { basemap: "plain", ...detail }));
  canvas.time.setRange(setup.range[0], setup.range[1]);
  canvas.addPath(setup.samples, { color: "#f5f7fa", width: 2 });
  const circles = canvas.addGroundCircles(setup.options.map(o => ({ id: o.id, center: o.position, radiusM: o.footprint.radiusM })));
  mountMilitary(canvas, { labels: false }); // the same bases as the main map; released with the canvas
  const aspect = (): number => mapEl.clientWidth / Math.max(1, mapEl.clientHeight);
  const frame = (o: Option, duration: number): void => {
    canvas.camera.flyTo(framePose(circleBounds(o.position, o.footprint.radiusM * 1.2), PITCH, aspect()), { duration }).catch(ignoreCancel);
  };
  // Pre-aim at the first option so its tiles load while the window is still invisible.
  if (setup.options[0]) frame(setup.options[0], 0);

  let shown: string | null = null;
  let built = false;
  let lastRows = "";
  const ready = circles.ready.then(() => {
    built = true;
    root.hidden = shown === null; // stop rendering until first opened
    root.style.visibility = "";
  });
  return {
    ready,
    open(option, content) {
      root.hidden = false;
      eyebrow.textContent = content.eyebrow;
      title.textContent = content.title;
      swatch.style.background = content.colour;
      unpin.hidden = !content.pinned;
      const rows = JSON.stringify(content.rows);
      if (rows !== lastRows) {
        lastRows = rows;
        dl.replaceChildren(...content.rows.flatMap(r => {
          const dt = document.createElement("dt"); dt.textContent = r.label;
          const dd = document.createElement("dd"); dd.textContent = r.value;
          if (r.grade) dd.dataset.grade = r.grade;
          if (r.urgency !== undefined) { dd.className = "countdown"; dd.style.setProperty("--urgency", String(r.urgency)); }
          return [dt, dd];
        }));
      }
      if (shown === option.id) return;
      const first = shown === null;
      shown = option.id;
      frame(option, first ? 0 : 0.6);
    },
    close() {
      shown = null;
      if (built) root.hidden = true; // before that, hiding would stop the build
    },
    setBasemap(kind) {
      // A failed load keeps the window's current map; the main view reports failures.
      canvas.scene.setBasemap(kind).catch(() => undefined);
    },
    setLighting: preset => canvas.scene.setLighting(preset),
    syncTime: t => canvas.time.seek(t),
    setCircleStyles: styles => circles.setStyles(styles),
    dispose() {
      canvas.destroy(); // releases its layers too
      root.remove();
    },
  };
}
