import { createSingaporeCanvas, FlightCancelled, PRESETS } from "../lib/index.js";
import { mountPopulation } from "./population.js";
import type { BasemapKind, LightingPreset } from "../lib/index.js";
import "./style.css";

const container = document.getElementById("scene");
const panel = document.getElementById("panel");
const statusEl = document.getElementById("status");
if (!container || !panel || !statusEl) throw new Error("demo markup missing");

const setStatus = (text: string): void => {
  statusEl.textContent = text;
};

const canvas = await createSingaporeCanvas(container, {
  ionToken: import.meta.env.VITE_CESIUM_ION_TOKEN,
  googleApiKey: import.meta.env.VITE_GOOGLE_MAPS_API_KEY,
}).catch(async () => {
  setStatus("Remote basemap unavailable — using plain globe.");
  return createSingaporeCanvas(container, { basemap: "plain" });
});

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

// Presets, straight from the library's own data file.
for (const id of canvas.camera.presets) {
  panel.append(
    button(PRESETS[id]?.label ?? id, () => {
      canvas.camera.flyToPreset(id).catch(ignoreCancel);
    }),
  );
}

// Basemap: all modes remain directly selectable even if another provider fails.
panel.append(group("Basemap"));
const basemapSelect = document.createElement("select");
basemapSelect.setAttribute("aria-label", "Basemap");
for (const [value, label] of [["plain", "Plain globe"], ["extruded", "Terrain + OSM buildings"], ["photorealistic", "Google photorealistic"]]) {
  basemapSelect.add(new Option(label, value));
}
basemapSelect.value = canvas.scene.basemap;
basemapSelect.onchange = () => {
  const next = basemapSelect.value as BasemapKind;
  basemapSelect.disabled = true;
  setStatus(`Loading ${next}…`);
  canvas.scene.setBasemap(next)
    .then(() => setStatus(`Basemap: ${next}`))
    .catch(() => setStatus(`${next} failed — check provider credentials; previous map retained.`))
    .finally(() => { basemapSelect.disabled = false; basemapSelect.value = canvas.scene.basemap; });
};
panel.append(basemapSelect);

// Lighting
let lighting: LightingPreset = "midday";
const lightBtn = button(`Light: ${lighting}`, () => {
  lighting = lighting === "midday" ? "blue-hour" : "midday";
  canvas.scene.setLighting(lighting);
  lightBtn.textContent = `Light: ${lighting}`;
});
panel.append(lightBtn);

// Camera
panel.append(group("Camera"));
let orbiting = false;
const orbitBtn = button("Start orbit", () => {
  orbiting = !orbiting;
  if (orbiting) {
    canvas.camera.orbit({
      centre: { lon: 103.8607, lat: 1.2834 },
      radius: 1200,
      pitch: -22,
      degreesPerSecond: 5,
    });
  } else {
    canvas.camera.stop();
  }
  orbitBtn.textContent = orbiting ? "Stop orbit" : "Start orbit";
});
panel.append(orbitBtn);

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
setStatus(`Singapore · ${canvas.scene.basemap} basemap`);
const disposePopulation = await mountPopulation(canvas);
if (import.meta.hot) import.meta.hot.dispose(() => {
  window.clearTimeout(edgeTimer);
  disposePopulation();
  canvas.destroy();
});

Object.assign(window, { __canvas: canvas });
