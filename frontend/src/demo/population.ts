import type { SingaporeCanvas, LabelLayer, PolygonLayer } from "../lib/index.js";
import { BREAKS, COLORS, UNKNOWN_COLOR, colorOf, labelPoint, parseDataset, planningAreaLabelPoints, valueOf } from "./population-model.js";
import type { PopulationData, Zone } from "./population-model.js";

const BOUNDARY_GREY = "#6e7378";
/** Camera height, in metres, below which subzone names replace planning-area names. Tune by eye. */
const SUBZONE_NAMES_BELOW_M = 12_000;

const format = (value: number | null, digits = 0): string => value === null ? "Unavailable" : value.toLocaleString("en-SG", { maximumFractionDigits: digits });
const label = (value: string): string => value.toLowerCase().replace(/\b\w/g, c => c.toUpperCase());

export interface PopulationView {
  setActive(active: boolean): void;
  dispose(): void;
}

/** Population view: subzones coloured by resident count, a legend, hover/click details. Data loads on first activation. */
export function mountPopulation(canvas: SingaporeCanvas, legendHost: HTMLElement): PopulationView {
  const legend = document.createElement("section");
  legend.id = "population-legend";
  legend.setAttribute("aria-label", "Population legend");
  legend.hidden = true;
  legend.innerHTML = `<p class="state" role="status"></p><button type="button" hidden>Retry loading data</button><div class="swatches"></div>
    <p class="source">Census 2020 residents (citizens and PRs) by URA 2019 subzone — not people present now.</p>`;
  legendHost.append(legend);
  const state = legend.querySelector<HTMLElement>(".state")!;
  const retry = legend.querySelector<HTMLButtonElement>("button")!;
  const swatches = legend.querySelector<HTMLElement>(".swatches")!;

  const detail = document.createElement("aside");
  detail.id = "population-details";
  detail.setAttribute("aria-label", "Subzone details");
  detail.hidden = true;
  document.body.append(detail);

  let dataset: PopulationData | undefined;
  let layer: PolygonLayer | undefined;
  let subzoneLabels: LabelLayer | undefined;
  let areaLabels: LabelLayer | undefined;
  let cameraHeight = canvas.camera.pose.height ?? Infinity;
  let loading = false;
  let active = false;
  let selected: string | null = null;
  let hovered: string | null = null;
  let disposed = false;
  let abort: AbortController | undefined;
  const byId = new Map<string, Zone>();

  function showDetails(): void {
    const zone = byId.get(selected ?? hovered ?? "");
    detail.replaceChildren();
    const tag = document.createElement("span"); tag.className = "eyebrow";
    tag.textContent = selected ? "PINNED SUBZONE" : "SUBZONE DETAILS"; detail.append(tag);
    const title = document.createElement("h2"); title.textContent = zone ? label(zone.properties.subzone) : "Explore a subzone"; detail.append(title);
    if (!zone) { const p = document.createElement("p"); p.textContent = "Hover to inspect; click a subzone to pin its details."; detail.append(p); return; }
    const p = zone.properties;
    const subtitle = document.createElement("p"); subtitle.textContent = `${label(p.planning_area)} · ${p.zone_id}`; detail.append(subtitle);
    const rows = [
      ["Resident population", format(p.population) + (p.population === null ? "" : " people")],
      ["Supplied zone area", p.zone_area_m2 === null ? "Unavailable — invalid geometry" : `${format(p.zone_area_m2 / 1_000_000, 3)} km²`],
      ["Area-average density", format(valueOf(zone, "density")) + (valueOf(zone, "density") === null ? "" : " people/km²")],
      ["Population status", p.population_status.replaceAll("_", " ")],
      ["Original source value", p.population_raw ?? "Missing"],
      ["Geometry", p.geometry_status],
      ["Future PEC input", p.pec_eligible ? "Eligible in partial-coverage subset" : "Excluded from candidate subset"],
    ];
    const dl = document.createElement("dl");
    for (const [name, value] of rows) { const dt = document.createElement("dt"); dt.textContent = name!; const dd = document.createElement("dd"); dd.textContent = value!; dl.append(dt, dd); }
    detail.append(dl);
    if (p.exclusion_reasons.length) { const note = document.createElement("p"); note.className = "data-note"; note.textContent = p.exclusion_reasons.join("; ").replaceAll("_", " "); detail.append(note); }
    if (p.outside_viewer_bounds) { const note = document.createElement("p"); note.textContent = "Some geometry is outside the current viewer camera bounds."; detail.append(note); }
    const areaNote = document.createElement("p"); areaNote.className = "data-note"; areaNote.textContent = "Area uses the supplied zone geometry; it is not independently water-masked land area."; detail.append(areaNote);
    if (selected) { const close = document.createElement("button"); close.type = "button"; close.textContent = "Unpin details"; close.onclick = () => { selected = null; hovered = null; paint(); }; detail.append(close); }
  }

  function paint(): void {
    if (!dataset) return;
    layer?.setStyles(new Map(dataset.features.map(zone => [zone.id, { color: selected === zone.id ? "#f3d3ff" : colorOf(zone, "population"), visible: true, selected: zone.id === selected }])));
    showDetails();
  }

  function drawLegend(): void {
    swatches.replaceChildren();
    const title = document.createElement("p"); title.textContent = "Resident population · people"; swatches.append(title);
    const limits = [0, ...BREAKS.population];
    COLORS.forEach((color, i) => {
      const item = document.createElement("span"); const swatch = document.createElement("i"); swatch.style.background = color;
      const upper = limits[i + 1];
      item.append(swatch, upper === undefined ? `${format(limits[i]!)}+` : `${format(limits[i]!)}–<${format(upper)}`); swatches.append(item);
    });
    const unknown = document.createElement("span"); const swatch = document.createElement("i"); swatch.style.background = UNKNOWN_COLOR;
    unknown.append(swatch, "Unknown / qualified population"); swatches.append(unknown);
  }

  function showLabels(): void {
    const near = cameraHeight < SUBZONE_NAMES_BELOW_M;
    subzoneLabels?.setVisible(active && near);
    areaLabels?.setVisible(active && !near);
  }
  const offCamera = canvas.on("cameraChange", pose => { cameraHeight = pose.height ?? Infinity; showLabels(); });

  function destroyLayers(): void {
    layer?.destroy(); subzoneLabels?.destroy(); areaLabels?.destroy();
    layer = subzoneLabels = areaLabels = undefined;
  }

  async function load(): Promise<void> {
    loading = true;
    retry.hidden = true;
    state.hidden = false;
    state.textContent = "Loading prepared population data…";
    abort?.abort(); abort = new AbortController();
    try {
      const response = await fetch(`${import.meta.env.BASE_URL}population.geojson`, { signal: abort.signal });
      if (!response.ok) throw new Error(`Population file unavailable (HTTP ${response.status}).`);
      // The Vite dev server answers a missing file with index.html, so check the type.
      if (!response.headers.get("content-type")?.includes("json")) throw new Error("Prepared population artifact is missing or not JSON.");
      dataset = parseDataset(await response.json());
      if (disposed) return;
      byId.clear(); dataset.features.forEach(z => byId.set(z.id, z));
      layer = await canvas.addPolygonLayer(dataset, {
        hover(id) { hovered = id; if (!selected) showDetails(); },
        click(id) { selected = id; paint(); },
      }, { outline: BOUNDARY_GREY });
      if (disposed) { layer.destroy(); return; }
      layer.setVisible(active);
      // Zones with unusable geometry get no label rather than a label at NaN.
      subzoneLabels = canvas.addLabels(dataset.features.flatMap(zone => {
        const { lon, lat } = labelPoint(zone);
        return Number.isFinite(lon) && Number.isFinite(lat) ? [{ position: { lon, lat }, text: label(zone.properties.subzone) }] : [];
      }));
      areaLabels = canvas.addLabels(planningAreaLabelPoints(dataset.features).map(a => ({ position: { lon: a.lon, lat: a.lat }, text: a.name })), { font: "600 16px 'Alliance No.2', 'Alliance No.1', Inter, sans-serif" });
      showLabels();
      detail.hidden = !active;
      state.hidden = true;
      drawLegend();
      paint();
    } catch (error) {
      if (disposed) return;
      destroyLayers(); dataset = undefined;
      state.textContent = `${error instanceof Error ? error.message : "Population loading failed."} Prepare data from the repository root with: .venv/bin/python scripts/population_data.py prepare`;
      retry.hidden = false;
    } finally {
      loading = false;
    }
  }
  retry.onclick = () => { void load(); };

  return {
    setActive(value) {
      active = value;
      legend.hidden = !value;
      detail.hidden = !value || !layer;
      if (layer) layer.setVisible(value);
      else if (value && !loading) void load();
      showLabels();
    },
    dispose() { disposed = true; abort?.abort(); offCamera(); destroyLayers(); legend.remove(); detail.remove(); },
  };
}
