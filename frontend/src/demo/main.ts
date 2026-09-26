import { createSingaporeCanvas, FlightCancelled, PRESETS } from "../lib/index.js";
import { mountPopulation } from "./population.js";
import { HOSPITALS, MILITARY, mountOsmAreas } from "./osm-areas.js";
import { mountDecision } from "./decision.js";
import { mountComparison, type Comparison } from "./comparison.js";
import { mountSimulationResult } from "./simulation.js";
import type { BasemapKind, LightingPreset } from "../lib/index.js";
import "./style.css";

const container = document.getElementById("scene");
const panel = document.getElementById("panel");
const statusEl = document.getElementById("status");
if (!container || !panel || !statusEl) throw new Error("demo markup missing");

// The panel slides in from the left edge and back out again.
const panelToggle = document.getElementById("panel-toggle");
if (panelToggle) panelToggle.onclick = () => {
  const open = panelToggle.getAttribute("aria-expanded") !== "true";
  panelToggle.setAttribute("aria-expanded", String(open));
  panelToggle.setAttribute("aria-label", open ? "Hide panel" : "Show panel");
  panelToggle.textContent = open ? "‹" : "›";
};

const setStatus = (text: string): void => {
  statusEl.textContent = text;
};

const FALLBACK_STATUS = "Terrain or buildings unavailable — plain fallback.";

const keys = {
  ionToken: import.meta.env.VITE_CESIUM_ION_TOKEN,
  googleApiKey: import.meta.env.VITE_GOOGLE_MAPS_API_KEY,
};

// Grey canvas is the default view. `plain` is only ever the fallback.
const plainStartup = new URLSearchParams(location.search).get("basemap") === "plain";
const acceptance = new URLSearchParams(location.search).get("acceptance") === "1";
const canvas = await createSingaporeCanvas(container, { ...keys, acceptance, basemap: plainStartup ? "plain" : "extruded" })
  .catch(() => createSingaporeCanvas(container, { basemap: "plain", acceptance }));

/**
 * Clicking a second preset cancels the first; that rejection is expected.
 *
 * Matched by name as well as by instance: under Vite HMR the lib and the demo
 * can end up holding two separate copies of the module, so `instanceof` fails
 * and a normal cancellation escapes as an unhandled rejection.
 */
const ignoreCancel = (err: unknown): void => {
  const cancelled =
    err instanceof FlightCancelled ||
    (err instanceof Error && err.name === "FlightCancelled");
  if (!cancelled) throw err;
};

function button(label: string, onClick: () => void): HTMLButtonElement {
  const el = document.createElement("button");
  el.type = "button";
  el.textContent = label;
  el.addEventListener("click", onClick);
  return el;
}

function group(label: string): HTMLParagraphElement {
  const el = document.createElement("p");
  el.className = "group";
  el.textContent = label;
  return el;
}

// Views: three exclusive looks at the same scene.
type View = "grey" | "population" | "google";
const VIEWS: readonly { id: View; label: string; basemap: BasemapKind }[] = [
  { id: "grey", label: "Grey canvas", basemap: "extruded" },
  { id: "population", label: "Population", basemap: "plain" },
  { id: "google", label: "Google", basemap: "photorealistic" },
];
let view: View = "grey";
// Mounted last; the panel can be used before it is ready.
let decision: ReturnType<typeof mountDecision> | undefined;
let comparison: Comparison | undefined;
const viewButtons = new Map<View, HTMLButtonElement>();

async function setView(next: (typeof VIEWS)[number]): Promise<void> {
  for (const b of viewButtons.values()) b.disabled = true;
  setStatus(`Loading ${next.label}…`);
  try {
    await canvas.scene.setBasemap(next.basemap);
    setStatus("Singapore");
  } catch {
    // A failed load keeps the current map, so Google failing leaves the view as it was.
    if (next.id !== "grey") {
      setStatus(`${next.label} failed — check provider credentials; view unchanged.`);
      return;
    }
    await canvas.scene.setBasemap("plain");
    setStatus(FALLBACK_STATUS);
  } finally {
    for (const b of viewButtons.values()) b.disabled = false;
  }
  view = next.id;
  population.setActive(view === "population");
  for (const layer of osmLayers) layer.setVisible(view !== "population"); // that view has its own labels and colours
  decision?.setBasemap(canvas.scene.basemap);
  comparison?.setBasemap(canvas.scene.basemap);
  for (const [id, b] of viewButtons) b.setAttribute("aria-pressed", String(id === view));
}

panel.append(group("View"));
for (const v of VIEWS) {
  const b = button(v.label, () => void setView(v));
  b.setAttribute("aria-pressed", String(v.id === view));
  viewButtons.set(v.id, b);
  panel.append(b);
}
const population = mountPopulation(canvas, panel);

// Named areas from OSM: tinted buildings and boundaries, labelled up close.
panel.append(group("Layers"));
const osmLayers = [MILITARY, HOSPITALS].map(layer => {
  const legend = document.createElement("p");
  legend.className = "legend";
  const swatch = document.createElement("i");
  swatch.style.background = layer.colour;
  legend.append(swatch, layer.legend);
  panel.append(legend);
  return mountOsmAreas(canvas, layer, { labels: true });
});
const simulation = mountSimulationResult(canvas, panel);

// Lighting
let lighting: LightingPreset = "midday";
const lightBtn = button(`Light: ${lighting}`, () => {
  lighting = lighting === "midday" ? "blue-hour" : "midday";
  canvas.scene.setLighting(lighting);
  decision?.setLighting(lighting);
  comparison?.setLighting(lighting);
  lightBtn.textContent = `Light: ${lighting}`;
});
panel.append(group("Lighting"), lightBtn);

// Presets, straight from the library's own data file, collapsed.
const places = document.createElement("details");
const placesSummary = document.createElement("summary");
placesSummary.textContent = "Places";
places.append(placesSummary);
for (const id of canvas.camera.presets) {
  places.append(
    button(PRESETS[id]?.label ?? id, () => {
      canvas.camera.flyToPreset(id).catch(ignoreCancel);
    }),
  );
}
panel.append(places);

// The cage, made visible. Without feedback a hard clamp just feels broken.
let edgeTimer: number | undefined;
canvas.on("boundsHit", ({ edge }) => {
  document.body.classList.add("at-edge");
  setStatus(edge === "ceiling" ? "Zoom limit — Singapore only" : `Edge: ${edge}`);
  window.clearTimeout(edgeTimer);
  edgeTimer = window.setTimeout(() => {
    document.body.classList.remove("at-edge");
    setStatus("Singapore");
  }, 900);
});

canvas.on("renderError", ({ message }) => setStatus(`Map rendering failed: ${message}`));

// The promise resolving IS the ready signal — there is no "ready" event.
setStatus(plainStartup ? "Singapore · plain basemap" : canvas.scene.basemap === "plain" ? FALLBACK_STATUS : "Singapore");
decision = mountDecision(canvas, { ...keys, lighting });
comparison = await mountComparison(canvas, { ...keys, lighting, initiallyOpen: false });
if (import.meta.hot) import.meta.hot.dispose(() => {
  window.clearTimeout(edgeTimer);
  decision?.dispose();
  comparison?.dispose();
  population.dispose();
  simulation.dispose();
  canvas.destroy();
});

Object.assign(window, { __canvas: canvas });
if (acceptance) Object.defineProperty(window, "__mvpAcceptance", { configurable: true, value: Object.freeze({
  inspect: () => ({ canvas: canvas.inspect?.(), planning: decision?.snapshot(), simulation: simulation.snapshot() }),
}) });
