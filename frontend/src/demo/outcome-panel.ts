import type { CircleStyle, MarkerStyle, SingaporeCanvas } from "../lib/index.js";
import { formatNumber, formatT } from "./decision-model.js";
import { flattenSnapshot, naiveCostMismatch, POLICY_NAMES, summaryRows, threatDetail } from "./engagement-model.js";
import type { RunPair, ThreatDetail } from "./engagement-model.js";
import { ResultResources } from "./result-resources.js";
import type { SimulationResultV2 } from "./simulation-model.js";

export interface OutcomePanel { setPair(pair: RunPair | null): void; selectThreat(threatId: string): void; dispose(): void }

type Stage = "baseline" | "optimised" | "improvement";
const STAGES: readonly Stage[] = ["baseline", "optimised", "improvement"];
const BASELINE = "#f0a04b";
const OPTIMISED = "#35c78a";

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (className) e.className = className;
  if (text !== undefined) e.textContent = text;
  return e;
}
const button = (label: string, className: string | undefined, onClick: () => void): HTMLButtonElement => {
  const b = el("button", className, label); b.type = "button"; b.onclick = onClick; return b;
};
const seconds = (s: number | null): string => (s === null ? "unavailable" : formatT(s));
const cost = (n: number | null): string => (n === null ? "unavailable" : formatNumber(n, 3));

/** The right panel: main's Baseline → Optimised → Compare walk, fed by two live runs. Empty until a pair exists. */
export function mountOutcomePanel(canvas: SingaporeCanvas, hooks: { onSelect(threatId: string): void; onReplay(): void }): OutcomePanel {
  const root = el("aside", "comparison-panel");
  root.id = "comparison-panel";
  root.tabIndex = -1;
  root.setAttribute("aria-label", "Outcome comparison");
  document.body.append(root);

  let pair: RunPair | null = null;
  let results: { baseline: SimulationResultV2; optimised: SimulationResultV2 } | null = null;
  let threatIds: string[] = [];
  let selectedIndex = 0;
  let stage: Stage = "baseline";
  let scope: "missile" | "all" = "missile";
  let layers: ResultResources | null = null;
  let markers: ReturnType<SingaporeCanvas["addMarkers"]> | null = null;
  let circles: ReturnType<SingaporeCanvas["addGroundCircles"]> | null = null;
  let disposed = false;

  const blur = (): void => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); };
  const top = (): void => { root.scrollTop = 0; };

  function buildLayers(): void {
    layers?.dispose();
    layers = null; markers = null; circles = null;
    if (!results) return;
    layers = new ResultResources(canvas);
    const rows = threatIds.flatMap(id => [["baseline", results!.baseline] as const, ["optimised", results!.optimised] as const].flatMap(([side, r]) => {
      const f = threatDetail(r, id).footprint;
      return f ? [{ id: `${id}:${side}`, center: { lon: f.center.lon, lat: f.center.lat }, radiusM: f.radiusM }] : [];
    }));
    circles = layers.canvas.addGroundCircles(rows, { hover() {}, click(id) { if (id) hooks.onSelect(id.split(":")[0]!); } });
    markers = layers.canvas.addMarkers(rows.map(r => ({ id: r.id, position: r.center })));
    void circles.ready.then(() => { if (!disposed) renderMap(); });
  }

  function renderMap(): void {
    if (!markers || !circles) return;
    const markerStyles = new Map<string, MarkerStyle>();
    const circleStyles = new Map<string, CircleStyle>();
    const selected = threatIds[selectedIndex];
    for (const id of threatIds) {
      const on = scope === "missile" && id === selected;
      const showBaseline = on && (stage === "baseline" || stage === "improvement");
      const showOptimised = on && (stage === "optimised" || stage === "improvement");
      markerStyles.set(`${id}:baseline`, { color: BASELINE, size: 12, visible: showBaseline, label: "Baseline" });
      markerStyles.set(`${id}:optimised`, { color: OPTIMISED, size: 12, visible: showOptimised, label: "Optimised" });
      circleStyles.set(`${id}:baseline`, { fill: "rgba(240, 160, 75, 0.24)", outline: BASELINE, visible: showBaseline });
      circleStyles.set(`${id}:optimised`, { fill: "rgba(53, 199, 138, 0.22)", outline: OPTIMISED, visible: showOptimised });
    }
    markers.setStyles(markerStyles);
    circles.setStyles(circleStyles);
  }

  function select(index: number, notify = true): void {
    if (index < 0 || index >= threatIds.length) return;
    blur();
    scope = "missile"; selectedIndex = index; stage = "baseline";
    render(); top();
    if (notify) hooks.onSelect(threatIds[index]!);
  }
  function setStage(next: Stage): void { blur(); stage = next; render(); top(); }
  function showAll(): void { blur(); scope = "all"; stage = "improvement"; render(); top(); }

  const sectionTitle = (text: string): HTMLElement => el("h3", "comparison-section-title", text);

  function stepper(): HTMLElement {
    const nav = el("nav", "story-steps");
    nav.setAttribute("aria-label", "Comparison stages");
    STAGES.forEach((item, index) => {
      const label = item === "improvement" ? "Compare" : item[0]!.toUpperCase() + item.slice(1);
      const b = button(`${index + 1} ${label}`, undefined, () => setStage(item));
      b.dataset.active = String(item === stage);
      b.setAttribute("aria-current", item === stage ? "step" : "false");
      nav.append(b);
    });
    return nav;
  }

  /** The all-missiles strip: backend totals only. */
  function summary(): HTMLElement {
    const section = el("section", "summary");
    section.setAttribute("aria-label", "All missiles summary");
    section.append(el("h2", undefined, "All missiles · Baseline → Optimised"));
    for (const r of summaryRows(results!.baseline, results!.optimised)) {
      const line = el("p", "total");
      if (r.unavailable) line.dataset.unavailable = "";
      const change = el("span", r.worse ? "worse" : "better", r.change);
      line.append(el("span", "name", r.label), el("span", "values", `${r.baseline} → ${r.optimised}`), change);
      section.append(line);
    }
    if (naiveCostMismatch(results!.baseline, results!.optimised)) {
      section.append(el("p", "note", `Naive cost differs from the optimised run's record (${formatNumber(results!.optimised.policyComparison.naive.ordinalCost, 3)}).`));
    }
    return section;
  }

  function facts(rows: readonly [string, string][]): HTMLElement {
    const dl = el("dl", "facts");
    for (const [k, v] of rows) {
      const dd = el("dd", v === "unavailable" ? "unavailable" : undefined, v);
      dl.append(el("dt", undefined, k), dd);
    }
    return dl;
  }

  function detailRows(d: ThreatDetail): [string, string][] {
    return [
      ["Outcome", d.outcome], ["Interceptor", d.interceptorId ?? "unavailable"], ["Opportunity", d.opportunityId ?? "unavailable"],
      ["Resolved", seconds(d.resolvedTimeS)], ["Training cost", cost(d.trainingCost)],
    ];
  }

  function footprintView(d: ThreatDetail): HTMLElement {
    const section = el("section", "outcome-metrics");
    section.append(sectionTitle("Supplied 100 m area"));
    if (!d.footprint) { section.append(el("p", "empty", "No selected footprint for this threat.")); return section; }
    const f = d.footprint;
    section.append(facts([["Centre", `${f.center.lon.toFixed(5)}, ${f.center.lat.toFixed(5)}`], ["Radius", `${f.radiusM} m`],
      ...flattenSnapshot(f.consequence).map(row => [row.key, row.value] as [string, string])]));
    return section;
  }

  function outcomeView(threatId: string, side: "baseline" | "optimised"): DocumentFragment {
    const r = results![side];
    const d = threatDetail(r, threatId);
    const fragment = document.createDocumentFragment();
    const hero = el("section", "outcome-heading");
    hero.append(el("p", "outcome-kicker", side === "baseline" ? "Unoptimised reference" : "Optimised result"),
      el("h2", undefined, `${POLICY_NAMES[r.policy.identity] ?? r.policy.identity} · ${r.policy.identity}`),
      el("p", undefined, `Result ${pair![side].resultId ?? "unavailable"} · run ${pair![side].runId ?? "unavailable"}`));
    const section = el("section", "outcome-metrics");
    section.append(sectionTitle("Outcome"), facts(detailRows(d)));
    fragment.append(hero, section, footprintView(d), stageActions());
    return fragment;
  }

  function tableRow(label: string, b: string, o: string, change: string, improved: boolean | null): HTMLTableRowElement {
    const tr = el("tr");
    const th = el("th", undefined, label);
    const delta = el("td", improved === null ? undefined : improved ? "delta-good" : "delta-cost", change);
    tr.append(th, el("td", undefined, b), el("td", undefined, o), delta);
    return tr;
  }

  function improvementView(threatId: string): DocumentFragment {
    const b = threatDetail(results!.baseline, threatId), o = threatDetail(results!.optimised, threatId);
    const fragment = document.createDocumentFragment();
    const heading = el("section", "outcome-heading");
    heading.append(el("p", "outcome-kicker", "Live comparison"), el("h2", undefined, `${threatId} · Naive vs ${POLICY_NAMES[results!.optimised.policy.identity] ?? results!.optimised.policy.identity}`));
    const wrap = el("div", "comparison-table-wrap");
    const table = el("table", "comparison-table");
    const head = el("thead"); const headRow = el("tr");
    for (const label of ["Measure", "Baseline", "Optimised", "Change"]) headRow.append(el("th", undefined, label));
    head.append(headRow);
    const body = el("tbody");
    const diff = (x: number | null, y: number | null, digits: number, lowerIsBetter: boolean): [string, boolean | null] => {
      if (x === null || y === null) return ["", null];
      const d = y - x;
      if (Math.abs(d) < 1e-9) return ["no change", null];
      return [`${d < 0 ? "▼" : "▲"} ${formatNumber(Math.abs(d), digits)}`, lowerIsBetter ? d < 0 : d > 0];
    };
    body.append(tableRow("Outcome", b.outcome, o.outcome, b.outcome === o.outcome ? "same" : o.outcome === "intercepted" ? "now intercepted" : "no longer intercepted", b.outcome === o.outcome ? null : o.outcome === "intercepted"));
    body.append(tableRow("Interceptor", b.interceptorId ?? "unavailable", o.interceptorId ?? "unavailable", "", null));
    body.append(tableRow("Resolved", seconds(b.resolvedTimeS), seconds(o.resolvedTimeS), ...diff(b.resolvedTimeS, o.resolvedTimeS, 1, true)));
    body.append(tableRow("Training cost", cost(b.trainingCost), cost(o.trainingCost), ...diff(b.trainingCost, o.trainingCost, 3, true)));
    const bs = new Map(flattenSnapshot(b.footprint?.consequence ?? null).map(r => [r.key, r.value]));
    const os = new Map(flattenSnapshot(o.footprint?.consequence ?? null).map(r => [r.key, r.value]));
    for (const key of new Set([...bs.keys(), ...os.keys()])) {
      const bv = bs.get(key) ?? "unavailable", ov = os.get(key) ?? "unavailable";
      const bn = Number(bv.replace(/,/g, "")), on = Number(ov.replace(/,/g, ""));
      const numeric = bv !== "unavailable" && ov !== "unavailable" && Number.isFinite(bn) && Number.isFinite(on);
      body.append(tableRow(key, bv, ov, ...(numeric ? diff(bn, on, 3, true) : [bv === ov ? "same" : "", null] as [string, boolean | null])));
    }
    table.append(head, body); wrap.append(table);
    fragment.append(heading, wrap, stageActions());
    return fragment;
  }

  function allMissilesView(): DocumentFragment {
    const fragment = document.createDocumentFragment();
    const r = results!.optimised;
    const heading = el("section", "outcome-heading");
    heading.append(el("p", "outcome-kicker", "Scenario-wide comparison"), el("h2", undefined, `All ${threatIds.length} missiles`));
    const section = el("section", "outcome-metrics");
    section.append(sectionTitle("Policy comparison"), facts([
      ["Active minus naive cost", formatNumber(r.policyComparison.activeMinusNaiveCost, 3)],
      ["Exact regret", cost(r.policyComparison.exactRegret)],
      ["Termination", r.termination.reason],
      ["Constraints", r.termination.constraintStatus],
    ]));
    const limits = el("ul", "limitations");
    for (const line of r.limitations) limits.append(el("li", undefined, line));
    section.append(sectionTitle("Limitations"), limits);
    fragment.append(heading, section);
    return fragment;
  }

  function stageActions(): HTMLElement {
    const bar = el("div", "stage-actions");
    const back = button(stage === "optimised" ? "Back to baseline" : "Back to optimised", "secondary-action", () => setStage(stage === "improvement" ? "optimised" : "baseline"));
    back.hidden = stage === "baseline";
    const nextLabel = stage === "baseline" ? "Show optimised outcome" : stage === "optimised" ? "Compare outcomes" : selectedIndex < threatIds.length - 1 ? "Next missile" : "View all missiles";
    const next = button(nextLabel, "primary-action", () => {
      if (stage === "baseline") setStage("optimised");
      else if (stage === "optimised") setStage("improvement");
      else if (selectedIndex < threatIds.length - 1) select(selectedIndex + 1);
      else showAll();
    });
    bar.append(back, next);
    return bar;
  }

  function render(): void {
    if (disposed) return;
    root.replaceChildren();
    root.dataset.stage = scope === "all" ? "improvement" : stage;
    root.dataset.scope = scope;
    const header = el("header", "comparison-header");
    const title = el("div");
    title.append(el("span", "synthetic-badge", pair ? `Live runs · ${pair.scenarioRef}` : "Live runs"), el("h1", undefined, "Outcome comparison"));
    header.append(title);
    if (!pair || !results) {
      root.append(header, el("p", "empty", pair?.problem ? `Comparison unavailable · ${pair.problem}`
        : "No run pair yet. Press Space to submit Naive and the drawer's policy on the selected scenario."));
      return;
    }
    const actions = el("div", "header-actions");
    actions.append(button(scope === "all" ? "Selected missile" : `All missiles (${threatIds.length})`, "all-missiles-button", () => { if (scope === "all") { scope = "missile"; render(); top(); } else showAll(); }),
      button("Replay tracks", "replay-button", hooks.onReplay));
    header.append(actions);
    root.append(header, summary());
    const navigator = el("div", "threat-navigator");
    const identity = el("div");
    if (scope === "all") {
      identity.append(el("strong", undefined, `All missiles - ${threatIds.length} threats`), el("small", undefined, pair.scenarioRef));
      navigator.append(identity);
      root.append(navigator, allMissilesView());
    } else {
      const id = threatIds[selectedIndex]!;
      const prev = button("Prev", undefined, () => select(selectedIndex - 1)); prev.disabled = selectedIndex === 0;
      const next = button("Next", undefined, () => select(selectedIndex + 1)); next.disabled = selectedIndex === threatIds.length - 1;
      identity.append(el("strong", undefined, `${id} - Missile ${selectedIndex + 1} of ${threatIds.length}`),
        el("small", undefined, `Optimised outcome: ${threatDetail(results.optimised, id).outcome}`));
      const selector = el("select", "missile-selector");
      selector.setAttribute("aria-label", "Select missile");
      threatIds.forEach((item, index) => { const option = el("option", undefined, item); option.value = String(index); option.selected = index === selectedIndex; selector.append(option); });
      selector.onchange = () => select(Number(selector.value));
      identity.append(selector);
      navigator.append(prev, identity, next);
      root.append(navigator, stepper(), stage === "improvement" ? improvementView(id) : outcomeView(id, stage));
    }
    renderMap();
  }

  const onKey = (event: KeyboardEvent): void => {
    const target = event.target;
    if (!results || (target instanceof HTMLElement && target.matches("button, input, select, textarea")) || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key === "ArrowLeft") select(selectedIndex - 1);
    if (event.key === "ArrowRight") select(selectedIndex + 1);
  };
  window.addEventListener("keydown", onKey);
  render();

  return {
    setPair(next) {
      pair = next;
      results = next?.results ?? null;
      threatIds = results ? results.optimised.trajectories.map(t => t.threatId) : [];
      selectedIndex = 0; stage = "baseline"; scope = "missile";
      buildLayers();
      render();
    },
    selectThreat(threatId) {
      const index = threatIds.indexOf(threatId);
      if (index >= 0 && (index !== selectedIndex || scope === "all")) select(index, false);
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      window.removeEventListener("keydown", onKey);
      layers?.dispose();
      root.remove();
    },
  };
}
