import { createSingaporeCanvas } from "../lib/index.js";
import type { BasemapKind, CircleStyle, LightingPreset, SingaporeCanvas as SingaporeCanvasT, TimedSample } from "../lib/index.js";
import { circleBounds, framePose } from "./decision-model.js";
import { viewAspect } from "./engagement-model.js";
import { HOSPITALS, MILITARY, mountOsmAreas } from "./osm-areas.js";

export interface FocusThreat { id: string; samples: readonly TimedSample[]; target: { lon: number; lat: number }; radiusM: number; colour: string }
export interface FocusContent { title: string; colour: string; rows: readonly { label: string; value: string }[] }
export interface FocusWindow {
  /** Shows the window framed on threat `id`'s area, or just refreshes the rows if it is already shown. */
  open(id: string, content: FocusContent): void;
  /** Shows the window with no missile in focus. */
  idle(): void;
  close(): void;
  setBasemap(kind: BasemapKind): void;
  setLighting(preset: LightingPreset): void;
  syncTime(t: Date): void;
  setCircleStyles(styles: ReadonlyMap<string, CircleStyle>): void;
  setRouteVisible(id: string, visible: boolean): void;
  dispose(): void;
}

const PITCH = -70;
const ignoreCancel = (err: unknown): void => { if (!(err instanceof Error && err.name === "FlightCancelled")) throw err; };

/**
 * The missile focus window: a second, independent canvas zoomed onto one threat's supplied area, plus its
 * live readings, inside `parent`. The canvas is built the first time a missile opens; while hidden it has
 * zero size, so Cesium skips rendering it.
 */
export function mountFocusWindow(setup: {
  parent: HTMLElement; keys: { ionToken?: string; googleApiKey?: string }; basemap: BasemapKind; lighting: LightingPreset;
  threats: readonly FocusThreat[]; range: readonly [Date, Date];
}): FocusWindow {
  const root = document.createElement("section");
  root.id = "focus";
  root.setAttribute("aria-label", "Missile focus");
  root.innerHTML = `<p class="eyebrow">MISSILE FOCUS</p><h2><i></i><span></span></h2><p class="empty idle">No missile in focus. Click a threat.</p><div class="inspector-map"></div><dl></dl>`;
  setup.parent.append(root);
  const swatch = root.querySelector<HTMLElement>("h2 i")!;
  const title = root.querySelector<HTMLElement>("h2 span")!;
  const idleEl = root.querySelector<HTMLElement>(".idle")!;
  const mapEl = root.querySelector<HTMLElement>(".inspector-map")!;
  const dl = root.querySelector<HTMLElement>("dl")!;

  let basemap = setup.basemap, lighting = setup.lighting;
  let time: Date | undefined;
  let styles: ReadonlyMap<string, CircleStyle> | undefined;
  const routeVisible = new Map(setup.threats.map(t => [t.id, false]));
  let disposed = false, built = false, framePending = false;
  let shown: string | null = null;
  let lastRows = "";
  let map: { canvas: Awaited<ReturnType<typeof createSingaporeCanvas>>; routes: Map<string, ReturnType<SingaporeCanvasT["addPath"]>>; circles: ReturnType<SingaporeCanvasT["addGroundCircles"]> } | undefined;
  let building: Promise<void> | undefined;

  const threatOf = (id: string): FocusThreat | undefined => setup.threats.find(t => t.id === id);
  const frame = (t: FocusThreat, duration: number): void => {
    const aspect = viewAspect(mapEl.clientWidth, mapEl.clientHeight);
    framePending = aspect === null; // a zero-size view would fly the camera to NaN: wait until it has a size
    if (aspect !== null) map?.canvas.camera.flyTo(framePose(circleBounds(t.target, Math.max(t.radiusM, 400) * 1.2), PITCH, aspect), { duration }).catch(ignoreCancel);
  };
  // Built on first open, not at startup: a second full map is most of the page's memory.
  const build = (): Promise<void> => building ??= (async () => {
    const want = basemap;
    const detail = { lighting, maximumScreenSpaceError: 4 };
    mapEl.style.visibility = "hidden";
    const canvas = await createSingaporeCanvas(mapEl, { ...setup.keys, basemap, ...detail })
      .catch(() => createSingaporeCanvas(mapEl, { basemap: "plain", ...detail }));
    if (disposed) { canvas.destroy(); return; }
    canvas.time.setRange(setup.range[0], setup.range[1]);
    const routes = new Map(setup.threats.map(t => [t.id, canvas.addPath(t.samples, { color: t.colour, width: 2 })]));
    const circles = canvas.addGroundCircles(setup.threats.map(t => ({ id: t.id, center: t.target, radiusM: t.radiusM })));
    for (const layer of [MILITARY, HOSPITALS]) mountOsmAreas(canvas, layer, { labels: false });
    map = { canvas, routes, circles };
    if (basemap !== want) canvas.scene.setBasemap(basemap).catch(() => undefined);
    if (lighting !== detail.lighting) canvas.scene.setLighting(lighting);
    mapEl.querySelector("canvas")!.style.pointerEvents = "none"; // a framed view only
    if (time) canvas.time.seek(time);
    if (styles) circles.setStyles(styles);
    for (const [id, route] of routes) route.setVisible(routeVisible.get(id) ?? false);
    const target = shown === null ? undefined : threatOf(shown);
    if (target) frame(target, 0);
    await circles.ready;
    built = true;
    root.hidden = closed;
    root.style.visibility = "";
    mapEl.style.visibility = "";
  })();

  let closed = true;
  root.hidden = true;
  return {
    open(id, content) {
      closed = false; root.hidden = false; root.style.visibility = "";
      idleEl.hidden = true; mapEl.hidden = false; dl.hidden = false;
      build().catch(() => { if (!map) building = undefined; }); // retry on the next open
      title.textContent = content.title;
      swatch.style.background = content.colour;
      const rows = JSON.stringify(content.rows);
      if (rows !== lastRows) {
        lastRows = rows;
        dl.replaceChildren(...content.rows.flatMap(r => {
          const dt = document.createElement("dt"); dt.textContent = r.label;
          const dd = document.createElement("dd"); dd.textContent = r.value;
          return [dt, dd];
        }));
      }
      if (shown === id) { const t = framePending ? threatOf(id) : undefined; if (t) frame(t, 0); return; }
      const first = shown === null;
      shown = id;
      const t = threatOf(id);
      if (t) frame(t, first ? 0 : 0.6);
    },
    idle() {
      closed = false; shown = null; root.hidden = false; root.style.visibility = "";
      title.textContent = ""; swatch.style.background = "transparent";
      idleEl.hidden = false; mapEl.hidden = true; dl.hidden = true;
    },
    close() {
      closed = true; shown = null;
      if (built || !building) root.hidden = true; else root.style.visibility = "hidden";
    },
    setBasemap(kind) { basemap = kind; map?.canvas.scene.setBasemap(kind).catch(() => undefined); },
    setLighting(preset) { lighting = preset; map?.canvas.scene.setLighting(preset); },
    syncTime(t) { time = t; map?.canvas.time.seek(t); },
    setCircleStyles(next) { styles = next; map?.circles.setStyles(next); },
    setRouteVisible(id, visible) { routeVisible.set(id, visible); map?.routes.get(id)?.setVisible(visible); },
    dispose() { disposed = true; map?.canvas.destroy(); root.remove(); },
  };
}
