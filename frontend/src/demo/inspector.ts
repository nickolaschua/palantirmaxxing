import { createSingaporeCanvas } from "../lib/index.js";
import type { BasemapKind, CircleStyle, LightingPreset, SingaporeCanvas as SingaporeCanvasT, TimedSample } from "../lib/index.js";
import { circleBounds, framePose } from "./decision-model.js";
import { HOSPITALS, MILITARY, mountOsmAreas } from "./osm-areas.js";
import type { ConsequenceRow, Grade, Option } from "./decision-model.js";

export interface InspectorContent {
  eyebrow: string;
  title: string;
  colour: string;
  pinned: boolean;
  /** `grade` colours a figure; `urgency` (0–1) reddens a countdown as it runs out. */
  rows: readonly { label: string; value: string; grade?: Grade | null; urgency?: number }[];
  /** Absent when the result carries no consequence for this area. */
  consequence?: { scenario: string | null; illustrative: boolean; rows: readonly ConsequenceRow[] } | undefined;
}

export interface Inspector {
  /** Shows the window framed on `option`, or just refreshes the stats if it is already shown. */
  open(option: Option, content: InspectorContent): void;
  close(): void;
  setBasemap(kind: BasemapKind): void;
  setLighting(preset: LightingPreset): void;
  syncTime(t: Date): void;
  setCircleStyles(styles: ReadonlyMap<string, CircleStyle>): void;
  /** The threat's route in the window; off once the threat is down. */
  setRouteVisible(visible: boolean): void;
  dispose(): void;
}

const PITCH = -70;

const ignoreCancel = (err: unknown): void => {
  if (!(err instanceof Error && err.name === "FlightCancelled")) throw err;
};

/**
 * The side window: a second, independent canvas zoomed onto one area, plus its
 * stats. The canvas is built the first time the window opens; while hidden it has
 * zero size, so Cesium skips rendering it.
 */
export function mountInspector(setup: {
  keys: { ionToken?: string; googleApiKey?: string };
  basemap: BasemapKind;
  lighting: LightingPreset;
  samples: readonly TimedSample[];
  range: readonly [Date, Date];
  options: readonly Option[];
  onUnpin(): void;
}): Inspector {
  const root = document.createElement("aside");
  root.id = "inspector";
  root.setAttribute("aria-label", "Area inspector");
  root.innerHTML = `<header><span class="eyebrow"></span><button type="button" class="unpin">Unpin</button></header>
    <h2><i></i><span></span></h2><div class="inspector-map"></div><dl></dl>
    <section class="consequence" hidden><h3>Consequence <span class="tag">Illustrative values</span></h3><p class="scenario"></p><ol></ol></section>`;
  document.body.append(root);
  const eyebrow = root.querySelector<HTMLElement>(".eyebrow")!;
  const unpin = root.querySelector<HTMLButtonElement>(".unpin")!;
  const swatch = root.querySelector<HTMLElement>("h2 i")!;
  const title = root.querySelector<HTMLElement>("h2 span")!;
  const mapEl = root.querySelector<HTMLElement>(".inspector-map")!;
  const dl = root.querySelector<HTMLElement>("dl")!;
  const consequence = root.querySelector<HTMLElement>(".consequence")!;
  const illustrativeTag = consequence.querySelector<HTMLElement>(".tag")!;
  const scenario = consequence.querySelector<HTMLElement>(".scenario")!;
  const consequenceList = consequence.querySelector<HTMLElement>("ol")!;
  unpin.onclick = () => setup.onUnpin();

  // Built on first open, not at startup: a second full map is most of the page's memory.
  // Everything set before then is remembered and applied once it exists.
  let basemap = setup.basemap;
  let lighting = setup.lighting;
  let time: Date | undefined;
  let styles: ReadonlyMap<string, CircleStyle> | undefined;
  let routeVisible = true;
  let disposed = false;
  let map: {
    canvas: Awaited<ReturnType<typeof createSingaporeCanvas>>;
    route: ReturnType<SingaporeCanvasT["addPath"]>;
    circles: ReturnType<SingaporeCanvasT["addGroundCircles"]>;
  } | undefined;
  let building: Promise<void> | undefined;

  const aspect = (): number => mapEl.clientWidth / Math.max(1, mapEl.clientHeight);
  const frame = (o: Option, duration: number): void => {
    map?.canvas.camera.flyTo(framePose(circleBounds(o.position, o.footprint.radiusM * 1.2), PITCH, aspect()), { duration }).catch(ignoreCancel);
  };
  const build = (): Promise<void> => building ??= (async () => {
    // Tile detail scales with canvas height, so a small window loads coarse tiles;
    // 4 (Cesium's default is 16) matches the main map's density at this height without the memory of 2.
    const want = basemap;
    const detail = { lighting, maximumScreenSpaceError: 4 };
    mapEl.style.visibility = "hidden"; // no whole-Earth flash: shown once framed
    const canvas = await createSingaporeCanvas(mapEl, { ...setup.keys, basemap, ...detail })
      .catch(() => createSingaporeCanvas(mapEl, { basemap: "plain", ...detail }));
    if (disposed) { canvas.destroy(); return; }
    canvas.time.setRange(setup.range[0], setup.range[1]);
    const route = canvas.addPath(setup.samples, { color: "#f5f7fa", width: 2 });
    const circles = canvas.addGroundCircles(setup.options.map(o => ({ id: o.id, center: o.position, radiusM: o.footprint.radiusM })));
    for (const layer of [MILITARY, HOSPITALS]) mountOsmAreas(canvas, layer, { labels: false }); // as on the main map; released with the canvas
    map = { canvas, route, circles };
    // Switched while building. Against `want`, so a Google failure that fell back to plain is not retried.
    if (basemap !== want) canvas.scene.setBasemap(basemap).catch(() => undefined);
    if (lighting !== detail.lighting) canvas.scene.setLighting(lighting);
    // A framed view only: the camera stays on the selected area.
    mapEl.querySelector("canvas")!.style.pointerEvents = "none";
    if (time) canvas.time.seek(time);
    if (styles) circles.setStyles(styles);
    route.setVisible(routeVisible);
    const target = setup.options.find(o => o.id === shown);
    if (target) frame(target, 0);
    await circles.ready;
    built = true;
    root.hidden = shown === null; // closed while building: stop rendering now
    root.style.visibility = "";
    mapEl.style.visibility = "";
  })();

  const pct = (n: number): string => `${(n * 100).toFixed(1)}%`;
  function renderConsequence(c: InspectorContent["consequence"]): void {
    consequence.hidden = !c;
    if (!c) return;
    illustrativeTag.hidden = !c.illustrative;
    scenario.textContent = c.scenario ? `Scenario: ${c.scenario}` : "";
    consequenceList.replaceChildren(...c.rows.map(r => {
      const li = document.createElement("li");
      li.title = r.detail;
      if (r.id === "total") li.className = "total";
      if (!r.bar) li.dataset.unavailable = "";
      const name = document.createElement("span"); name.className = "name"; name.textContent = r.label;
      const weight = document.createElement("span"); weight.className = "weight"; weight.textContent = r.weight;
      const bar = document.createElement("span"); bar.className = "bar";
      if (r.bar) {
        const band = document.createElement("i");
        band.style.left = pct(r.bar.low); band.style.width = pct(r.bar.high - r.bar.low);
        const point = document.createElement("b");
        point.style.left = pct(r.bar.central);
        bar.append(band, point);
      }
      const value = document.createElement("span"); value.className = "value"; value.textContent = r.value;
      li.append(name, weight, bar, value);
      return li;
    }));
  }

  let shown: string | null = null;
  let built = false;
  let lastRows = "";
  root.hidden = true;
  root.style.visibility = "";
  return {
    open(option, content) {
      root.hidden = false;
      root.style.visibility = "";
      build().catch(() => { if (!map) building = undefined; }); // retry on the next open
      eyebrow.textContent = content.eyebrow;
      title.textContent = content.title;
      swatch.style.background = content.colour;
      unpin.hidden = !content.pinned;
      const rows = JSON.stringify([content.rows, content.consequence]);
      if (rows !== lastRows) {
        lastRows = rows;
        dl.replaceChildren(...content.rows.flatMap(r => {
          const dt = document.createElement("dt"); dt.textContent = r.label;
          const dd = document.createElement("dd"); dd.textContent = r.value;
          if (r.grade) dd.dataset.grade = r.grade;
          if (r.urgency !== undefined) { dd.className = "countdown"; dd.style.setProperty("--urgency", String(r.urgency)); }
          return [dt, dd];
        }));
        renderConsequence(content.consequence);
      }
      if (shown === option.id) return;
      const first = shown === null;
      shown = option.id;
      frame(option, first ? 0 : 0.6);
    },
    close() {
      shown = null;
      // While building, stay laid out but invisible: a display:none canvas never renders, so never builds.
      if (built || !building) root.hidden = true;
      else root.style.visibility = "hidden";
    },
    setBasemap(kind) {
      basemap = kind;
      // A failed load keeps the window's current map; the main view reports failures.
      map?.canvas.scene.setBasemap(kind).catch(() => undefined);
    },
    setLighting(preset) { lighting = preset; map?.canvas.scene.setLighting(preset); },
    syncTime(t) { time = t; map?.canvas.time.seek(t); },
    setCircleStyles(next) { styles = next; map?.circles.setStyles(next); },
    setRouteVisible(visible) { routeVisible = visible; map?.route.setVisible(visible); },
    dispose() {
      disposed = true;
      map?.canvas.destroy(); // releases its layers too
      root.remove();
    },
  };
}
