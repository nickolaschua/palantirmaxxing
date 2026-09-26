import type {
  BasemapKind, CircleLayer, CircleStyle, LabelLayer, LightingPreset, MarkerLayer, MarkerStyle, SingaporeCanvas,
} from "../lib/index.js";
import { circleBounds, framePose } from "./decision-model.js";
import { DIMENSIONS } from "./comparison-contract.js";
import type { MultiThreatComparisonResult, Outcome, OutcomeMetric, RangeValue, Stage, ThreatComparison } from "./comparison-contract.js";
import { loadComparisonResult } from "./comparison-source.js";

export interface Decision {
  setBasemap(kind: BasemapKind): void;
  setLighting(preset: LightingPreset): void;
  dispose(): void;
}

const BASELINE = "#f0a04b";
const OPTIMISED = "#35c78a";
const DIM = "rgba(189, 198, 209, 0.28)";
const STAGES: readonly Stage[] = ["baseline", "optimised", "improvement"];

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string, text?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

const samplesOf = (threat: ThreatComparison, start: Date) => threat.samples.map(sample => ({
  lon: sample.lon,
  lat: sample.lat,
  height: sample.height,
  time: new Date(start.getTime() + sample.seconds * 1000),
}));

const formatInteger = (value: number): string => value.toLocaleString("en-SG", { maximumFractionDigits: 0 });
const formatCompact = (value: number): string => value.toLocaleString("en-SG", { notation: "compact", maximumFractionDigits: 1 });
const rangeText = (range: RangeValue, unit = ""): string => `${formatInteger(range.low)}-${formatInteger(range.high)}${unit}`;

function metricValue(metric: OutcomeMetric): string {
  if (metric.unit === "person-hours") return `${formatCompact(metric.central)} person-hours`;
  if (metric.unit === "days") return `${formatInteger(metric.central)} days`;
  if (metric.unit === "minutes") return `${formatInteger(metric.central)} min`;
  return formatInteger(metric.central);
}

function metricRange(metric: OutcomeMetric): string {
  if (metric.unit === "person-hours") return `${formatCompact(metric.low)}-${formatCompact(metric.high)} person-hours`;
  if (metric.unit === "days") return rangeText(metric, " days");
  if (metric.unit === "minutes") return rangeText(metric, " min");
  return rangeText(metric);
}

function metricById(outcome: Outcome, id: string): OutcomeMetric {
  const metric = outcome.metrics.find(item => item.id === id);
  if (!metric) throw new Error(`Synthetic outcome is missing metric ${id}`);
  return metric;
}

const optionalMetric = (outcome: Outcome, id: string): OutcomeMetric | undefined => outcome.metrics.find(item => item.id === id);

function improvementText(baseline: number, optimised: number, unit: string): { text: string; improved: boolean } {
  const delta = baseline - optimised;
  const percent = baseline === 0 ? null : Math.abs(delta / baseline) * 100;
  const amount = unit === "person-hours" ? formatCompact(Math.abs(delta)) : formatInteger(Math.abs(delta));
  const suffix = unit === "people" ? "" : unit === "days" ? " days" : unit === "minutes" ? " min" : unit === "score" ? " points" : " person-hours";
  if (delta > 0) return { text: `${amount}${suffix} lower${percent === null ? "" : ` (${percent.toFixed(0)}%)`}`, improved: true };
  if (delta < 0) return { text: `${amount}${suffix} higher${percent === null ? "" : ` (${percent.toFixed(0)}%)`}`, improved: false };
  return { text: "No change", improved: true };
}

function aggregateOutcome(result: MultiThreatComparisonResult, side: "baseline" | "optimised"): Outcome {
  const outcomes = result.threats.map(threat => threat[side]);
  const first = outcomes[0]!;
  const metrics = first.metrics.map(template => {
    const values = outcomes.map(outcome => metricById(outcome, template.id));
    const useMaximum = template.id === "recovery" || template.id === "delay";
    const combine = (key: keyof RangeValue): number => useMaximum
      ? Math.max(...values.map(value => value[key]))
      : values.reduce((sum, value) => sum + value[key], 0);
    return { ...template, low: combine("low"), central: combine("central"), high: combine("high") };
  });
  const vector = Object.fromEntries(DIMENSIONS.map(({ code }) => {
    const average = (key: keyof RangeValue): number => Math.round(outcomes.reduce((sum, outcome) => sum + outcome.vector[code][key], 0) / outcomes.length);
    return [code, { low: average("low"), central: average("central"), high: average("high") }];
  })) as Outcome["vector"];
  const categoryTotals = new Map<string, { contribution: number; mechanism: string }>();
  for (const outcome of outcomes) {
    for (const category of outcome.categories) {
      const current = categoryTotals.get(category.label) ?? { contribution: 0, mechanism: category.mechanism };
      current.contribution += category.contribution;
      categoryTotals.set(category.label, current);
    }
  }
  const categories = [...categoryTotals].map(([label, value]) => ({ label, ...value })).sort((a, b) => b.contribution - a.contribution).slice(0, 5);
  return {
    policyLabel: side === "baseline" ? "Combined baseline" : "Combined optimised",
    policyDetail: side === "baseline" ? "Aggregate of every baseline result." : "Aggregate of every optimised result.",
    position: first.position,
    timeFromStartS: Math.max(...outcomes.map(outcome => outcome.timeFromStartS)),
    successProbability: outcomes.reduce((sum, outcome) => sum + outcome.successProbability, 0) / outcomes.length,
    metrics,
    vector,
    categories,
    sourcedPercent: Math.round(outcomes.reduce((sum, outcome) => sum + outcome.sourcedPercent, 0) / outcomes.length),
    assumedPercent: Math.round(outcomes.reduce((sum, outcome) => sum + outcome.assumedPercent, 0) / outcomes.length),
  };
}

function aggregateComparison(result: MultiThreatComparisonResult): ThreatComparison {
  const baseline = aggregateOutcome(result, "baseline");
  const optimised = aggregateOutcome(result, "optimised");
  const exposedBaseline = optionalMetric(baseline, "exposed");
  const exposedOptimised = optionalMetric(optimised, "exposed");
  const serviceBaseline = optionalMetric(baseline, "service");
  const serviceOptimised = optionalMetric(optimised, "service");
  const simulationCount = result.threats.reduce((sum, threat) => sum + threat.simulationCount, 0);
  const robustnessPercent = Math.round(result.threats.reduce((sum, threat) => sum + threat.robustnessPercent * threat.simulationCount, 0) / simulationCount);
  const tradeoffs: string[] = [];
  for (const { code, label } of DIMENSIONS) {
    if (optimised.vector[code].central > baseline.vector[code].central) tradeoffs.push(`${label} is ${optimised.vector[code].central - baseline.vector[code].central} points higher on average.`);
  }
  const successDelta = (baseline.successProbability - optimised.successProbability) * 100;
  if (successDelta > 0) tradeoffs.push(`Mean supplied success is ${successDelta.toFixed(1)} percentage points lower.`);
  if (!tradeoffs.length) tradeoffs.push("No material aggregate trade-off is present in the supplied results.");
  const reasons = [
    ...(exposedBaseline && exposedOptimised ? [`Reduces summed potential exposure by ${formatInteger(exposedBaseline.central - exposedOptimised.central)} people before overlap adjustment.`] : []),
    ...(serviceBaseline && serviceOptimised ? [`Reduces summed service disruption by ${formatCompact(serviceBaseline.central - serviceOptimised.central)} person-hours.`] : []),
    `Lowers average human-exposure score H from ${baseline.vector.H.central} to ${optimised.vector.H.central}.`,
  ];
  return {
    id: "all-threats",
    displayId: "ALL",
    condition: `${result.threats.length} missiles in ${result.scenarioId}`,
    samples: result.threats[0]!.samples,
    baseline,
    optimised,
    reasons,
    tradeoffs,
    robustnessPercent,
    simulationCount,
  };
}

function outcomeMarkers(canvas: SingaporeCanvas, threats: readonly ThreatComparison[]): MarkerLayer {
  const points = threats.flatMap(threat => [
    { id: `${threat.id}:baseline`, position: threat.baseline.position },
    { id: `${threat.id}:optimised`, position: threat.optimised.position },
  ]);
  return canvas.addMarkers(points);
}

export async function mountDecision(
  canvas: SingaporeCanvas,
  _setup: { ionToken?: string; googleApiKey?: string; lighting: LightingPreset },
): Promise<Decision> {
  const root = el("aside", "comparison-panel");
  root.id = "comparison-panel";
  root.tabIndex = -1;
  root.setAttribute("aria-label", "Synthetic outcome comparison");
  root.innerHTML = `<p class="outcome-kicker">Synthetic research demo</p><h1>Preparing comparison...</h1>`;
  const restorePanel = el("button", "restore-comparison-panel", "Show comparison");
  restorePanel.type = "button";
  restorePanel.hidden = true;
  restorePanel.setAttribute("aria-controls", "comparison-panel");
  document.body.append(root, restorePanel);

  let loaded: Awaited<ReturnType<typeof loadComparisonResult>>;
  try {
    loaded = await loadComparisonResult();
  } catch (error) {
    root.innerHTML = `<p class="outcome-kicker">Comparison unavailable</p><h1>Result could not be loaded</h1><p class="source-error"></p>`;
    root.querySelector<HTMLElement>(".source-error")!.textContent = error instanceof Error ? error.message : String(error);
    return { setBasemap() {}, setLighting() {}, dispose() { root.remove(); restorePanel.remove(); } };
  }
  const { result, sourceLabel, usingFallback } = loaded;
  const threats = result.threats;
  const aggregate = aggregateComparison(result);
  const start = new Date(result.start);
  const durationS = Math.max(...threats.flatMap(threat => threat.samples.map(sample => sample.seconds)));
  const stop = new Date(start.getTime() + durationS * 1000);

  canvas.time.setRange(start, stop);
  const trackLayers = threats.map(threat => {
    const samples = samplesOf(threat, start);
    return canvas.addPath(samples, {
      color: DIM, trailColor: DIM, width: 2, markerSize: 14, markerShape: "craft",
    });
  });
  resources.use(() => inspector.dispose());
  // Everything that belongs to this threat's flight. Once it is down, this goes
  // and only the struck area stays, as a mark of where an intercept has been.
  const setRouteVisible = (visible: boolean): void => {
    path.setVisible(visible);
    approach?.setVisible(visible);
    approachLabel?.setVisible(visible);
    descent?.setVisible(visible);
    inspector.setRouteVisible(visible);
  };
  const setLayersVisible = (visible: boolean): void => {
    setRouteVisible(visible);
    markers.setVisible(visible);
    circles.setVisible(visible);
  };
  setLayersVisible(false);

  const labels: LabelLayer = canvas.addLabels(threats.map(threat => ({
    position: threat.samples[0]!, text: threat.displayId,
  })), { font: "700 12px sans-serif" });

  const markers = outcomeMarkers(canvas, threats);
  let selectedIndex = 0;
  let stage: Stage = "baseline";
  let scope: "missile" | "all" = "missile";
  let comparisonExpanded = false;
  let panelCollapsed = false;
  let disposed = false;
  const activeStyle = { color: "#f4f7fb", trailColor: "rgba(244, 247, 251, 0.38)", width: 4, markerSize: 25, markerShape: "craft" as const, markerPulse: true };
  let activeTrack = canvas.addPath(samplesOf(threats[0]!, start), activeStyle);
  const createSelectedCircles = (threat: ThreatComparison): CircleLayer => canvas.addGroundCircles([
    { id: `${threat.id}:baseline`, center: threat.baseline.position, radiusM: 650 },
    { id: `${threat.id}:optimised`, center: threat.optimised.position, radiusM: 650 },
  ]);
  let circles = createSelectedCircles(threats[0]!);

  const framePoints = threats.flatMap(threat => [
    ...samplesOf(threat, start),
    ...circleBounds(threat.baseline.position, 650),
    ...circleBounds(threat.optimised.position, 650),
  ]);
  const frameAll = (): void => {
    canvas.camera.flyTo(framePose(framePoints, -72, innerWidth / innerHeight, 1.45), { duration: 0.8 }).catch(() => undefined);
  };

  function selectThreat(index: number): void {
    if (index < 0 || index >= threats.length) return;
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    const changed = index !== selectedIndex;
    scope = "missile";
    panelCollapsed = false;
    selectedIndex = index;
    if (changed) {
      activeTrack.destroy();
      activeTrack = canvas.addPath(samplesOf(threats[selectedIndex]!, start), activeStyle);
      circles.destroy();
      circles = createSelectedCircles(threats[selectedIndex]!);
      void circles.ready.then(() => { if (!disposed) renderMap(); });
    }
    stage = "baseline";
    comparisonExpanded = false;
    render();
    root.scrollTop = 0;
    requestAnimationFrame(() => { root.scrollTop = 0; });
  }

  function setStage(next: Stage): void {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    stage = next;
    if (stage !== "improvement") comparisonExpanded = false;
    render();
    root.scrollTop = 0;
    requestAnimationFrame(() => { root.scrollTop = 0; });
  }

  function showAllMissiles(): void {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    scope = "all";
    stage = "improvement";
    comparisonExpanded = false;
    panelCollapsed = false;
    render();
    root.scrollTop = 0;
    requestAnimationFrame(() => { root.scrollTop = 0; });
  }

  function sectionTitle(text: string): HTMLElement {
    return el("h3", "comparison-section-title", text);
  }

  function stepper(): HTMLElement {
    const nav = el("nav", "story-steps");
    nav.setAttribute("aria-label", "Comparison stages");
    STAGES.forEach((item, index) => {
      const label = item === "improvement" ? "Compare" : item[0]!.toUpperCase() + item.slice(1);
      const button = el("button", undefined, `${index + 1} ${label}`);
      button.type = "button";
      button.dataset.active = String(item === stage);
      button.setAttribute("aria-current", item === stage ? "step" : "false");
      button.onclick = () => setStage(item);
      nav.append(button);
    });
    return nav;
  }

  function metricList(outcome: Outcome): HTMLElement {
    const section = el("section", "outcome-metrics");
    section.append(sectionTitle("Outcome estimates"));
    const list = el("dl");
    for (const metric of outcome.metrics) {
      const row = el("div", "metric-row");
      const value = el("dd");
      value.append(el("strong", undefined, metricValue(metric)), el("small", undefined, metricRange(metric)));
      row.append(el("dt", undefined, metric.label), value);
      list.append(row);
    }
    const success = el("div", "metric-row");
    const successValue = el("dd");
    successValue.append(el("strong", undefined, `${(outcome.successProbability * 100).toFixed(1)}%`), el("small", undefined, "Supplied synthetic probability"));
    success.append(el("dt", undefined, "Intercept success"), successValue);
    list.append(success);
    section.append(list);
    return section;
  }

  function vector(outcome: Outcome): HTMLElement {
    const section = el("section", "vector-section");
    section.append(sectionTitle("Consequence vector"));
    const rows = el("div", "vector-rows");
    for (const item of DIMENSIONS) {
      const value = outcome.vector[item.code];
      const row = el("div", "vector-row");
      row.title = `${item.label}: ${value.low}-${value.high}, central ${value.central}`;
      row.append(el("strong", "vector-code", item.code), el("span", "vector-label", item.label));
      const track = el("span", "vector-track");
      const fill = el("i");
      fill.style.width = `${value.central}%`;
      track.append(fill);
      row.append(track, el("b", "vector-value", String(value.central)), el("small", "vector-range", `${value.low}-${value.high}`));
      rows.append(row);
    }
    section.append(rows);
    return section;
  }

  function categories(outcome: Outcome): HTMLElement {
    const section = el("section", "category-section");
    section.append(sectionTitle("Main affected categories"));
    const list = el("ol");
    for (const category of outcome.categories) {
      const item = el("li");
      const top = el("span");
      top.append(el("strong", undefined, category.label), el("b", undefined, `${category.contribution}%`));
      item.append(top, el("small", undefined, category.mechanism));
      list.append(item);
    }
    section.append(list);
    return section;
  }

  function evidence(outcome: Outcome): HTMLElement {
    const section = el("section", "evidence-section");
    section.append(sectionTitle("Evidence quality"));
    const bar = el("div", "evidence-bar");
    const sourced = el("i"); sourced.style.width = `${outcome.sourcedPercent}%`;
    const assumed = el("i"); assumed.style.width = `${outcome.assumedPercent}%`;
    bar.append(sourced, assumed);
    section.append(bar, el("p", undefined, `${outcome.sourcedPercent}% sourced / derived - ${outcome.assumedPercent}% assumed`));
    return section;
  }

  function outcomeView(threat: ThreatComparison, outcome: Outcome): DocumentFragment {
    const fragment = document.createDocumentFragment();
    const hero = el("section", "outcome-heading");
    hero.append(el("p", "outcome-kicker", stage === "baseline" ? "Unoptimised reference" : "Optimised result"));
    hero.append(el("h2", undefined, outcome.policyLabel), el("p", undefined, outcome.policyDetail));
    fragment.append(hero, metricList(outcome), vector(outcome), categories(outcome), evidence(outcome));
    fragment.append(el("p", "synthetic-note", "Synthetic demonstration values. Not observed outcomes or operational estimates."), stageActions(threat));
    return fragment;
  }

  function tableRow(label: string, baseline: string, optimised: string, change: string, improved: boolean): HTMLTableRowElement {
    const row = el("tr");
    row.append(el("th", undefined, label), el("td", undefined, baseline), el("td", undefined, optimised), el("td", improved ? "delta-good" : "delta-cost", change));
    return row;
  }

  function comparisonTable(threat: ThreatComparison): HTMLElement {
    const wrap = el("div", "comparison-table-wrap");
    const table = el("table", "comparison-table");
    const head = el("thead");
    const headRow = el("tr");
    ["Measure", "Baseline", "Optimised", "Improvement"].forEach(label => headRow.append(el("th", undefined, label)));
    head.append(headRow);
    const body = el("tbody");
    const outcomeGroup = el("tr", "table-group");
    const outcomeTitle = el("th", undefined, "Outcome metrics"); outcomeTitle.colSpan = 4; outcomeGroup.append(outcomeTitle);
    body.append(outcomeGroup);
    for (const baselineMetric of threat.baseline.metrics) {
      const optimisedMetric = metricById(threat.optimised, baselineMetric.id);
      const improvement = improvementText(baselineMetric.central, optimisedMetric.central, baselineMetric.unit);
      body.append(tableRow(baselineMetric.label, metricValue(baselineMetric), metricValue(optimisedMetric), improvement.text, improvement.improved));
    }
    const successDelta = (threat.optimised.successProbability - threat.baseline.successProbability) * 100;
    body.append(tableRow("Intercept success", `${(threat.baseline.successProbability * 100).toFixed(1)}%`, `${(threat.optimised.successProbability * 100).toFixed(1)}%`, `${Math.abs(successDelta).toFixed(1)} percentage points ${successDelta < 0 ? "lower" : "higher"}`, successDelta >= 0));
    const vectorGroup = el("tr", "table-group");
    const vectorTitle = el("th", undefined, "H / E / D / X / R / A"); vectorTitle.colSpan = 4; vectorGroup.append(vectorTitle);
    body.append(vectorGroup);
    for (const item of DIMENSIONS) {
      const baseline = threat.baseline.vector[item.code];
      const optimised = threat.optimised.vector[item.code];
      const improvement = improvementText(baseline.central, optimised.central, "score");
      body.append(tableRow(`${item.code} - ${item.label}`, String(baseline.central), String(optimised.central), improvement.text, improvement.improved));
    }
    table.append(head, body);
    wrap.append(table);
    return wrap;
  }

  function explanation(title: string, items: readonly string[], className: string): HTMLElement {
    const section = el("section", `explanation ${className}`);
    section.append(sectionTitle(title));
    const list = el("ul");
    items.forEach(item => list.append(el("li", undefined, item)));
    section.append(list);
    return section;
  }

  function improvementView(threat: ThreatComparison): DocumentFragment {
    const fragment = document.createDocumentFragment();
    const heading = el("section", "improvement-heading");
    heading.append(el("p", "outcome-kicker", "Retrospective comparison"), el("h2", undefined, "Measured improvement"));
    const expand = el("button", "expand-comparison", comparisonExpanded ? "Restore panel" : "Full screen");
    expand.type = "button";
    expand.setAttribute("aria-pressed", String(comparisonExpanded));
    expand.onclick = () => { comparisonExpanded = !comparisonExpanded; render(); };
    heading.append(expand);
    fragment.append(heading, comparisonTable(threat));
    fragment.append(explanation("Why this was selected", threat.reasons, "benefits"), explanation("Accepted trade-offs", threat.tradeoffs, "tradeoffs"));
    const robustness = el("section", "robustness-section");
    robustness.append(sectionTitle("Robustness and evidence"));
    robustness.append(el("strong", undefined, `Lower consequence in ${threat.robustnessPercent}% of simulations`), el("p", undefined, `${formatInteger(threat.simulationCount)} sampled scenarios - ${threat.optimised.sourcedPercent}% sourced / derived - ${threat.optimised.assumedPercent}% assumed`));
    fragment.append(robustness, el("p", "synthetic-note", "Synthetic demonstration values. Not observed outcomes or operational estimates."), stageActions(threat));
    return fragment;
  }

  function missileBreakdown(): HTMLElement {
    const section = el("section", "missile-breakdown");
    section.append(sectionTitle("Improvement by missile"));
    const wrap = el("div", "comparison-table-wrap");
    const table = el("table", "comparison-table missile-table");
    const head = el("thead");
    const headRow = el("tr");
    const comparisonMetric = optionalMetric(aggregate.baseline, "exposed") ?? aggregate.baseline.metrics[0]!;
    ["Missile", `Baseline ${comparisonMetric.label}`, `Optimised ${comparisonMetric.label}`, "Reduction", "Robustness"].forEach(label => headRow.append(el("th", undefined, label)));
    head.append(headRow);
    const body = el("tbody");
    for (const threat of threats) {
      const baselineMetric = metricById(threat.baseline, comparisonMetric.id);
      const optimisedMetric = metricById(threat.optimised, comparisonMetric.id);
      const baseline = baselineMetric.central;
      const optimised = optimisedMetric.central;
      const reduction = improvementText(baseline, optimised, baselineMetric.unit);
      const row = el("tr");
      const select = el("button", "missile-link", threat.displayId);
      select.type = "button";
      select.title = `Open ${threat.displayId} comparison`;
      select.onclick = () => {
        const index = threats.indexOf(threat);
        selectThreat(index);
        setStage("improvement");
      };
      const missile = el("th"); missile.append(select);
      row.append(
        missile,
        el("td", undefined, formatInteger(baseline)),
        el("td", undefined, formatInteger(optimised)),
        el("td", reduction.improved ? "delta-good" : "delta-cost", reduction.text),
        el("td", undefined, `${threat.robustnessPercent}%`),
      );
      body.append(row);
    }
    table.append(head, body);
    wrap.append(table);
    section.append(wrap);
    return section;
  }

  function allMissilesView(): DocumentFragment {
    const fragment = document.createDocumentFragment();
    const heading = el("section", "improvement-heading");
    heading.append(el("p", "outcome-kicker", "Scenario-wide comparison"), el("h2", undefined, `All ${threats.length} missiles`));
    const close = el("button", "close-comparison", "Close panel");
    close.type = "button";
    close.setAttribute("aria-label", "Close comparison panel and show the full map");
    close.onclick = () => {
      panelCollapsed = true;
      render();
      requestAnimationFrame(frameAll);
    };
    heading.append(close);
    const method = el("p", "aggregation-note", "Aggregation: exposure, fatalities and service-person-hours are summed; recovery and delay use the scenario maximum; success and H/E/D/X/R/A use the mean. Exposure totals are not deduplicated across overlapping outcome areas.");
    fragment.append(heading, method, comparisonTable(aggregate), missileBreakdown());
    fragment.append(explanation("Why the combined result improved", aggregate.reasons, "benefits"), explanation("Combined trade-offs", aggregate.tradeoffs, "tradeoffs"));
    const evidence = el("section", "robustness-section");
    evidence.append(sectionTitle("Scenario robustness and provenance"));
    evidence.append(
      el("strong", undefined, `Weighted robustness: ${aggregate.robustnessPercent}% across ${formatInteger(aggregate.simulationCount)} samples`),
      el("p", undefined, `Policy ${result.scorePolicy.id} v${result.scorePolicy.version} - ${sourceLabel}`),
      el("p", undefined, result.provenance.limitations.join(" ")),
    );
    const actions = el("footer", "stage-actions");
    const back = el("button", "secondary-action", `Back to ${threats[selectedIndex]!.displayId}`);
    back.type = "button";
    back.onclick = () => { scope = "missile"; render(); root.scrollTop = 0; };
    actions.append(back);
    fragment.append(evidence, actions);
    return fragment;
  }

  function stageActions(_threat: ThreatComparison): HTMLElement {
    const actions = el("footer", "stage-actions");
    const back = el("button", "secondary-action", stage === "optimised" ? "Back to baseline" : "Back to optimised");
    back.type = "button";
    back.hidden = stage === "baseline";
    back.onclick = () => setStage(stage === "improvement" ? "optimised" : "baseline");
    const nextLabel = stage === "baseline" ? "Show optimised outcome" : stage === "optimised" ? "Compare outcomes" : selectedIndex < threats.length - 1 ? "Next missile" : "View all missiles";
    const next = el("button", "primary-action", nextLabel);
    next.type = "button";
    next.onclick = () => {
      if (stage === "baseline") setStage("optimised");
      else if (stage === "optimised") setStage("improvement");
      else if (selectedIndex < threats.length - 1) selectThreat(selectedIndex + 1);
      else showAllMissiles();
    };
    actions.append(back, next);
    return actions;
  }

  function renderMap(): void {
    trackLayers.forEach((layer, index) => {
      const selected = index === selectedIndex;
      layer.setVisible(scope === "all" || !selected);
    });
    activeTrack.setVisible(scope === "missile");
    const threat = threats[selectedIndex]!;
    const markerStyles = new Map<string, MarkerStyle>();
    const circleStyles = new Map<string, CircleStyle>();
    for (const item of threats) {
      const baselineId = `${item.id}:baseline`;
      const optimisedId = `${item.id}:optimised`;
      const selected = scope === "missile" && item.id === threat.id;
      const showBaseline = selected && (stage === "baseline" || stage === "improvement");
      const showOptimised = selected && (stage === "optimised" || stage === "improvement");
      markerStyles.set(baselineId, { color: BASELINE, size: 12, visible: showBaseline, label: "Baseline" });
      markerStyles.set(optimisedId, { color: OPTIMISED, size: 12, visible: showOptimised, label: "Optimised" });
      if (selected) {
        circleStyles.set(baselineId, { fill: "rgba(240, 160, 75, 0.24)", outline: BASELINE, visible: showBaseline });
        circleStyles.set(optimisedId, { fill: "rgba(53, 199, 138, 0.22)", outline: OPTIMISED, visible: showOptimised });
      }
    }
    markers.setStyles(markerStyles);
    circles.setStyles(circleStyles);
  }

  function render(): void {
    if (disposed) return;
    const threat = threats[selectedIndex]!;
    root.dataset.stage = scope === "all" ? "improvement" : stage;
    root.dataset.scope = scope;
    root.dataset.expanded = String(comparisonExpanded);
    root.hidden = scope === "all" && panelCollapsed;
    restorePanel.hidden = scope !== "all" || !panelCollapsed;
    root.replaceChildren();
    const header = el("header", "comparison-header");
    const title = el("div");
    title.append(el("span", "synthetic-badge", usingFallback ? "Bundled research fixture" : "Validated simulation result"), el("h1", undefined, "Outcome comparison"));
    const headerActions = el("div", "header-actions");
    const all = el("button", "all-missiles-button", scope === "all" ? "Selected missile" : `All missiles (${threats.length})`);
    all.type = "button";
    all.onclick = () => {
      if (scope === "all") { scope = "missile"; panelCollapsed = false; render(); root.scrollTop = 0; }
      else showAllMissiles();
    };
    const replay = el("button", "replay-button", "Replay tracks");
    replay.type = "button";
    replay.onclick = () => { canvas.time.seek(start); canvas.time.play(); };
    headerActions.append(all, replay);
    header.append(title, headerActions);
    const navigator = el("div", "threat-navigator");
    const identity = el("div");
    if (scope === "all") {
      identity.append(el("strong", undefined, `All missiles - ${threats.length} threats`), el("small", undefined, result.scenarioId));
      navigator.append(identity);
      root.append(header, navigator, allMissilesView());
    } else {
      const prev = el("button", undefined, "Prev"); prev.type = "button"; prev.disabled = selectedIndex === 0; prev.title = "Previous missile"; prev.onclick = () => selectThreat(selectedIndex - 1);
      identity.append(el("strong", undefined, `${threat.displayId} - Missile ${selectedIndex + 1} of ${threats.length}`), el("small", undefined, threat.condition));
      const selector = el("select", "missile-selector");
      selector.setAttribute("aria-label", "Select missile");
      threats.forEach((item, index) => {
        const option = el("option", undefined, `${item.displayId} - ${item.condition}`);
        option.value = String(index);
        option.selected = index === selectedIndex;
        selector.append(option);
      });
      selector.onchange = () => selectThreat(Number(selector.value));
      identity.append(selector);
      const next = el("button", undefined, "Next"); next.type = "button"; next.disabled = selectedIndex === threats.length - 1; next.title = "Next missile"; next.onclick = () => selectThreat(selectedIndex + 1);
      navigator.append(prev, identity, next);
      root.append(header, navigator, stepper());
      root.append(stage === "improvement" ? improvementView(threat) : outcomeView(threat, stage === "baseline" ? threat.baseline : threat.optimised));
    }
    renderMap();
  }

  const onKey = (event: KeyboardEvent): void => {
    const target = event.target as HTMLElement | null;
    if (target?.matches("button, input, select, textarea") || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key === "ArrowLeft") selectThreat(selectedIndex - 1);
    if (event.key === "ArrowRight") selectThreat(selectedIndex + 1);
  };
  window.addEventListener("keydown", onKey);
  restorePanel.onclick = () => {
    panelCollapsed = false;
    render();
    root.focus({ preventScroll: true });
  };

  render();
  frameAll();
  canvas.time.play();
  void circles.ready.then(() => {
    if (!disposed) renderMap();
  });

  return {
    setBasemap() {},
    setLighting() {},
    dispose() {
      disposed = true;
      window.removeEventListener("keydown", onKey);
      trackLayers.forEach(layer => layer.destroy());
      activeTrack.destroy();
      labels.destroy();
      markers.destroy();
      circles.destroy();
      root.remove();
      restorePanel.remove();
    },
  };
}

/** Returns immediately so navigation can dispose even a pending load. */
export function mountDecision(
  canvas: SingaporeCanvas,
  setup: { ionToken?: string; googleApiKey?: string; lighting: LightingPreset },
  loader: ResultLoader = loadPlanningResult,
): Decision & { retry(): void; snapshot(): Snapshot | undefined } {
  let basemap = canvas.scene.basemap;
  let lighting = setup.lighting;
  const loading = mountResultLoader(document.body, "Planning", loader, parseResult,
    (parsed, snapshot) => {
      const resources = new ResultResources(canvas);
      try {
        const view = renderDecision(resources.canvas, { ...setup, lighting }, parsed, resources, snapshot);
        view.setBasemap(basemap);
        return view;
      } catch (error) { resources.dispose(); throw error; }
    });
  const runs = mountRunControls(loading.controls, "planning", loading.loadIdentity);
  return {
    retry: loading.retry,
    snapshot: loading.snapshot,
    setBasemap(kind) { basemap = kind; loading.current()?.setBasemap(kind); },
    setLighting(preset) { lighting = preset; loading.current()?.setLighting(preset); },
    dispose() { runs.dispose(); loading.dispose(); },
  };
}
