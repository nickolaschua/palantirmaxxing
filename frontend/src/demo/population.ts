import type { SingaporeCanvas, PolygonLayer } from "../lib/index.js";
import {
  BREAKS, COLORS, UNKNOWN_COLOR, colorOf, parseDataset, rankZones, selectZones, units, valueOf,
} from "./population-model.js";
import type { Metric, PopulationData, Zone } from "./population-model.js";

const format = (value: number | null, digits = 0): string => value === null ? "Unavailable" : value.toLocaleString("en-SG", { maximumFractionDigits: digits });
const label = (value: string): string => value.toLowerCase().replace(/\b\w/g, c => c.toUpperCase());

export async function mountPopulation(canvas: SingaporeCanvas): Promise<() => void> {
  const root = document.createElement("section");
  root.id = "population-panel";
  root.setAttribute("aria-label", "Resident population explorer");
  root.innerHTML = `
    <header><span class="eyebrow">SINGAPORE CANVAS / POPULATION ATLAS</span>
      <h1>Singapore Resident Population <span>— Census 2020</span></h1>
      <p class="intro">A residential portrait of the island, one subzone at a time.</p></header>
    <p id="population-state" role="status">Loading prepared population data…</p>
    <button id="population-retry" hidden>Retry loading data</button>
    <div id="population-content" hidden>
      <div class="population-toolbar"><label class="layer-switch"><input id="population-enabled" type="checkbox" checked> Population layer</label><span class="year-tag">2020 / MP2019</span></div>
      <div class="metric-switch" role="group" aria-label="Population metric"><button data-metric="population" aria-pressed="true">Resident count</button><button data-metric="density" aria-pressed="false">Density</button></div>
      <label class="field-label" for="population-search">Find a subzone</label><input id="population-search" type="search" placeholder="Search name or zone code…">
      <label class="field-label" for="population-area">Planning area</label><select id="population-area"><option value="">All planning areas</option></select>
      <div id="population-stats" class="population-stats"></div>
      <div id="population-legend" aria-label="Population legend"></div>
      <section class="ranking"><div class="section-label"><h2 id="ranking-title">Highest resident counts</h2><span>TOP 12</span></div><p id="ranking-note"></p><ol id="population-chart"></ol></section>
      <details class="all-zones"><summary>Browse all matching subzones</summary><div id="population-list"></div></details>
    </div>
    <footer><p>Citizens and permanent residents. Historical residential population, not live crowd levels or everyone physically present. Density is a subzone area average, not building-level occupancy.</p>
      <p><a href="https://data.gov.sg/datasets/d_d95ae740c0f8961a0b10435836660ce0/view" target="_blank" rel="noreferrer">SingStat Census 2020</a> · <a href="https://data.gov.sg/datasets/d_8594ae9ff96d0c708bc2af633048edfb/view" target="_blank" rel="noreferrer">URA Master Plan 2019</a></p><p id="population-provenance"></p></footer>`;
  document.body.append(root);
  const detail = document.createElement("aside");
  detail.id = "population-details";
  detail.setAttribute("aria-label", "Subzone details");
  detail.innerHTML = `<span class="eyebrow">EXPLORE THE DATA</span><h2>Every zone has a story.</h2><p>Hover over a subzone to inspect it. Click to pin its details, or choose a ranked row.</p>`;
  document.body.append(detail);
  function el<T extends HTMLElement>(id: string): T { return root.querySelector<T>(`#${id}`)!; }
  const state = el("population-state");
  let dataset: PopulationData;
  let layer: PolygonLayer | undefined;
  let metric: Metric = "population";
  let filtered: Zone[] = [];
  let selected: string | null = null;
  let hovered: string | null = null;
  let disposed = false;
  let abort: AbortController | undefined;
  let enabled = true;
  const byId = new Map<string, Zone>();
  function showDetails(): void {
    const zone = byId.get(selected ?? hovered ?? "");
    detail.replaceChildren();
    const tag = document.createElement("span"); tag.className = "eyebrow";
    tag.textContent = selected ? "PINNED SUBZONE" : "SUBZONE DETAILS"; detail.append(tag);
    const title = document.createElement("h2"); title.textContent = zone ? label(zone.properties.subzone) : "Explore a subzone"; detail.append(title);
    if (!zone) { const p = document.createElement("p"); p.textContent = "Hover to inspect; click a polygon or a ranked row to pin details."; detail.append(p); return; }
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
    if (selected) { const close = document.createElement("button"); close.textContent = "Unpin details"; close.onclick = () => { selected = null; hovered = null; refresh(); }; detail.append(close); }
  }
  function select(zone: Zone): void { selected = zone.id; hovered = null; refresh(); }
  function refresh(): void {
    if (!dataset) return;
    filtered = selectZones(dataset, el<HTMLInputElement>("population-search").value, el<HTMLSelectElement>("population-area").value);
    const ids = new Set(filtered.map(z => z.id));
    if (selected && !ids.has(selected)) selected = null;
    if (hovered && !ids.has(hovered)) hovered = null;
    const styles = new Map(dataset.features.map(zone => [zone.id, { color: selected === zone.id ? "#f3d3ff" : colorOf(zone, metric), visible: ids.has(zone.id), selected: zone.id === selected }]));
    layer?.setStyles(styles);
    const known = filtered.filter(z => z.properties.population !== null);
    const total = known.reduce((sum, z) => sum + (z.properties.population ?? 0), 0);
    el("population-stats").textContent = `${format(total)} known residents · ${filtered.length} subzones · ${filtered.length - known.length} population unknown`;
    state.textContent = !filtered.length ? "No subzones match. Clear the search or change the planning area." : !enabled ? "Map layer hidden. The chart and data remain available." : `${dataset.features.length} source zones · ${dataset.metadata.coverage.counts.eligible} eligible for the partial PEC-candidate subset`;
    const legend = el("population-legend"); legend.replaceChildren();
    const legendTitle = document.createElement("p"); legendTitle.className = "section-label"; legendTitle.textContent = `${units(metric)} · fixed island-wide scale`; legend.append(legendTitle);
    const limits = [0, ...BREAKS[metric]];
    COLORS.forEach((color, i) => { const item = document.createElement("span"); const swatch = document.createElement("i"); swatch.style.background = color; const upper = limits[i+1]; item.append(swatch, upper === undefined ? `${format(limits[i]!)}+` : `${format(limits[i]!)}–<${format(upper)}`); legend.append(item); });
    const unknown = document.createElement("span"); const swatch = document.createElement("i"); swatch.style.background = UNKNOWN_COLOR; unknown.append(swatch, metric === "population" ? "Unknown / qualified population" : "Unknown population / invalid area"); legend.append(unknown);
    const ranked = rankZones(filtered, metric);
    el("ranking-title").textContent = metric === "population" ? "Highest resident counts" : "Highest densities";
    el("ranking-note").textContent = `${units(metric)} · ${filtered.length - ranked.length} unavailable values excluded from ranking`;
    const chart = el("population-chart"); chart.replaceChildren();
    const max = valueOf(ranked[0] ?? { properties: { population: 0, population_density_people_per_m2: 0 } } as Zone, metric) || 1;
    for (const zone of ranked.slice(0, 12)) {
      const li = document.createElement("li"); const button = document.createElement("button");
      button.className = "rank-row"; button.setAttribute("aria-pressed", String(zone.id === selected));
      const name = document.createElement("span"); name.textContent = label(zone.properties.subzone);
      const value = document.createElement("strong"); value.textContent = format(valueOf(zone, metric));
      const bar = document.createElement("i"); bar.style.width = `${100 * (valueOf(zone, metric) ?? 0) / max}%`; bar.style.background = colorOf(zone, metric);
      button.append(name, value, bar); button.onclick = () => select(zone); li.append(button); chart.append(li);
    }
    if (!ranked.length) { const p = document.createElement("li"); p.textContent = filtered.length ? "No known values for this metric." : "No matching subzones."; chart.append(p); }
    const list = el("population-list"); list.replaceChildren();
    for (const zone of filtered) { const button = document.createElement("button"); button.textContent = `${label(zone.properties.subzone)} · ${format(valueOf(zone, metric))} ${units(metric)}`; button.onclick = () => select(zone); list.append(button); }
    for (const button of root.querySelectorAll<HTMLButtonElement>("[data-metric]")) button.setAttribute("aria-pressed", String(button.dataset.metric === metric));
    showDetails();
  }
  async function load(): Promise<void> {
    el("population-retry").hidden = true;
    el("population-content").hidden = true;
    state.textContent = "Loading prepared population data…";
    abort?.abort(); abort = new AbortController();
    try {
      const response = await fetch(`${import.meta.env.BASE_URL}population.geojson`, { signal: abort.signal });
      if (!response.ok) throw new Error(`Population file unavailable (HTTP ${response.status}).`);
      if (!response.headers.get("content-type")?.includes("json")) throw new Error("Prepared population artifact is missing or not JSON.");
      dataset = parseDataset(await response.json());
      if (disposed) return;
      byId.clear(); dataset.features.forEach(z => byId.set(z.id, z));
      layer?.destroy();
      layer = await canvas.addPolygonLayer(dataset, {
        hover(id) { hovered = id; if (!selected) showDetails(); },
        click(id) { selected = id; refresh(); },
      });
      if (disposed) { layer.destroy(); return; }
      layer.setVisible(enabled);
      const area = el<HTMLSelectElement>("population-area");
      area.replaceChildren(new Option("All planning areas", ""));
      for (const name of [...new Set(dataset.features.map(z => z.properties.planning_area))].sort()) area.add(new Option(label(name), name));
      el("population-provenance").textContent = `Census year: 2020. Boundary vintage: 2019. Population published: 18 Jun 2021. Retrieved: ${new Date(dataset.metadata.retrieved_at).toLocaleDateString("en-SG")}. ${dataset.metadata.retrieval_meaning}.`;
      el("population-content").hidden = false;
      refresh();
    } catch (error) {
      if (disposed) return;
      layer?.destroy(); layer = undefined;
      state.textContent = `${error instanceof Error ? error.message : "Population loading failed."} Prepare data from the repository root with: .venv/bin/python scripts/population_data.py prepare`;
      el("population-retry").hidden = false;
    }
  }
  el("population-retry").onclick = () => { void load(); };
  el("population-search").oninput = refresh;
  el("population-area").onchange = refresh;
  el<HTMLInputElement>("population-enabled").onchange = () => { enabled = el<HTMLInputElement>("population-enabled").checked; layer?.setVisible(enabled); hovered = null; refresh(); };
  for (const button of root.querySelectorAll<HTMLButtonElement>("[data-metric]")) button.onclick = () => { metric = button.dataset.metric as Metric; refresh(); };
  await load();
  return () => { disposed = true; abort?.abort(); layer?.destroy(); root.remove(); detail.remove(); };
}
