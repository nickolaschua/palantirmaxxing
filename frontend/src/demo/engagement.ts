import type { CircleStyle, MarkerStyle, SingaporeCanvas } from "../lib/index.js";
import { circleBounds, formatT, framePose } from "./decision-model.js";
import {
  BASELINE_POLICY, clockEndS, DESCENT_S, descentSamples, elapsedOf, lockTimeOf, mapInsets, outcomesOf, pairFailure, pairPhase, pairProblem,
  planIntercepts, POLICY_NAMES, positionAt, STATE_LABELS, threatStateAt, viewAspect,
} from "./engagement-model.js";
import { BASES } from "./interceptor-model.js";
import type { RunPair, RunRef, ThreatState } from "./engagement-model.js";
import { mountOutcomePanel } from "./outcome-panel.js";
import { mountResultLoader } from "./result-loader.js";
import { ResultResources } from "./result-resources.js";
import { mountRunControls } from "./run-controls.js";
import { awaitRun, submitRun } from "./runs.js";
import { parseSimulationResult } from "./simulation-model.js";
import type { SimulationResult, SimulationResultV2 } from "./simulation-model.js";
import { isSnapshot, loadSimulationResult } from "./source.js";
import type { ResultLoader, Snapshot } from "./source.js";

export interface Engagement { retry(): void; snapshot(): Snapshot | undefined; dispose(): void }

const REPLAY_SPEED = 1; // real time, as the frontend branch played it
const STANDBY_PITCH = -70;
const FOLLOW_RADIUS_M = 3000;
const BIRDS_EYE_S = 0.6;
const COLOURS = ["#ff6b6b", "#ffd166", "#06d6a0", "#4cc9f0", "#7b61ff", "#f72585", "#90be6d", "#f8961e"];
const UNHANDLED = "#ff3b30";
const SELECTED = "#06d6a0";
const INTERCEPTOR = "#35c78a";
const BASE_MARKER = "#c9d1d9";

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (className) e.className = className;
  if (text !== undefined) e.textContent = text;
  return e;
}
/** Per-frame writes go through this: unchanged text touches nothing. */
const setText = (e: HTMLElement, text: string): void => { if (e.textContent !== text) e.textContent = text; };
const alpha = (hex: string, a: number): string => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
};
const errorText = (error: unknown): string => (error instanceof Error ? error.message : String(error));
const ignoreCancel = (err: unknown): void => { if (!(err instanceof Error && err.name === "FlightCancelled")) throw err; };

type Phase = "standby" | "submitting" | "loading" | "live" | "done";

/** One loaded result on the map and in the Threats list. Its layers and rows belong to `resources`. */
interface ScenarioView {
  result: SimulationResult;
  start: Date;
  endS: number;
  framePoints: readonly { lon: number; lat: number }[];
  /** Pushes states for `elapsed` to the layers and rows; returns the counts for the standby bar. */
  render(elapsed: number, live: boolean, focus: string | null): { detected: number; resolved: number; total: number };
  reset(): void;
  stateOf(threatId: string, elapsed: number): ThreatState | undefined;
  positionOf(threatId: string, elapsed: number): { lon: number; lat: number; height: number } | undefined;
  dispose(): void;
}

function renderScenario(
  canvas: SingaporeCanvas, result: SimulationResult, resources: ResultResources,
  list: { threatList: HTMLOListElement; listEmpty: HTMLElement }, onPick: (threatId: string) => void,
): ScenarioView {
  const start = new Date(result.start);
  const endS = clockEndS(result);
  const outcomes = new Map(outcomesOf(result).map(o => [o.threatId, o]));
  const threats = result.trajectories.map((t, i) => ({
    t, outcome: outcomes.get(t.threatId), lockAtS: lockTimeOf(result, t.threatId),
    colour: outcomes.get(t.threatId)?.outcome === "unhandled" ? UNHANDLED : COLOURS[i % COLOURS.length]!,
  }));
  const byId = new Map(threats.map(x => [x.t.threatId, x]));
  const paths = new Map(threats.map(({ t, colour }) => [t.threatId, canvas.addPath(
    t.samples.map(s => ({ lon: s.position.lon, lat: s.position.lat, height: s.position.heightM, time: new Date(s.time) })),
    { color: colour, trailColor: alpha(colour, 0.35), width: 3, markerSize: 30, markerShape: "craft", markerPulse: true },
  )]));
  const unhandledFootprints = result.schemaVersion === "simulation-result/2"
    ? result.terminalCounterfactualFootprints.filter(f => outcomes.get(f.threatId)?.outcome === "unhandled") : [];
  const footprints = [...result.selectedFootprints, ...unhandledFootprints];
  const circles = canvas.addGroundCircles(
    footprints.map(f => ({ id: f.id, center: { lon: f.center.lon, lat: f.center.lat }, radiusM: f.radiusM })),
    { hover() {}, click(id) { const f = footprints.find(r => r.id === id); if (f) onPick(f.threatId); } },
  );
  const markers = canvas.addMarkers(footprints.map(f => ({ id: f.id, position: { lon: f.center.lon, lat: f.center.lat } })));

  // Interceptors: an illustration worked backwards from the backend's intercept point and time (see planIntercepts).
  const { plans } = planIntercepts(result);
  const baseMarkers = canvas.addMarkers(BASES.map(b => ({ id: `base:${b.id}`, position: b.position })));
  const flights = new Map([...plans.values()].map(p => [p.threatId, canvas.addPath(p.samples, {
    color: INTERCEPTOR, trailColor: alpha(INTERCEPTOR, 0.4), width: 3, markerSize: 25, markerShape: "craft", markerPulse: true,
  })]));
  // After the meet the threat falls onto its supplied area; the burst is on the ground, where it lands.
  const landing = new Map([...plans.values()].map(p => {
    const f = result.selectedFootprints.find(row => row.threatId === p.threatId);
    return [p.threatId, f ? { lon: f.center.lon, lat: f.center.lat } : { lon: p.target.position.lon, lat: p.target.position.lat }];
  }));
  const descents = new Map([...plans.values()].map(p => [p.threatId, canvas.addPath(
    descentSamples(p.target.position, landing.get(p.threatId)!, p.interceptS, start),
    { color: "#ff7043", trailColor: "#ff7043", width: 2, markerSize: 30, markerShape: "craft", markerPulse: true },
  )]));
  const bursts = new Map([...plans.values()].map(p => [p.threatId, canvas.addBurst(landing.get(p.threatId)!, { color: "#ff7043", radiusM: 600, durationS: 2.2 })]));

  // Rows, built once; the list shows the detected ones in detection order.
  const rows = new Map(threats.map(({ t, colour }) => {
    const li = el("li");
    li.style.setProperty("--threat", colour);
    li.dataset.threatId = t.threatId;
    const pick = el("button", "row");
    pick.type = "button";
    pick.title = "Focus this threat";
    const name = el("span", "name");
    name.append(el("i"), el("b", undefined, t.threatId), el("code", undefined, `detected ${formatT(t.detectionTimeS)}`));
    const status = el("span", "status");
    pick.append(name, status);
    li.append(pick);
    pick.onclick = () => onPick(t.threatId);
    return [t.threatId, { li, status }] as const;
  }));
  resources.use(() => { for (const r of rows.values()) r.li.remove(); if (!list.threatList.childElementCount) list.listEmpty.hidden = false; });

  const shown = new Map<string, boolean>();
  const flightShown = new Map<string, boolean>();
  const descentShown = new Map<string, boolean>();
  const landed = new Set<string>();
  let lastOrder = "", lastCircles = "", lastMarkers = "", lastBases = "";
  const stateOf = (threatId: string, elapsed: number, live = true): ThreatState | undefined => {
    const x = byId.get(threatId);
    return x ? (live ? threatStateAt(x.t, x.outcome, x.lockAtS, elapsed) : "unseen") : undefined;
  };

  function render(elapsed: number, live: boolean, focus: string | null) {
    const states = new Map(threats.map(x => [x.t.threatId, stateOf(x.t.threatId, elapsed, live)!]));
    for (const x of threats) {
      const s = states.get(x.t.threatId)!;
      const flying = s === "detected" || s === "locked";
      if (shown.get(x.t.threatId) !== flying) { shown.set(x.t.threatId, flying); paths.get(x.t.threatId)!.setVisible(flying); }
      // The interceptor flies from its launch to the meet; the struck threat then falls for DESCENT_S and bursts where it lands.
      const plan = plans.get(x.t.threatId);
      if (plan) {
        const away = live && elapsed >= plan.launchS && elapsed < plan.interceptS;
        if (flightShown.get(x.t.threatId) !== away) { flightShown.set(x.t.threatId, away); flights.get(x.t.threatId)!.setVisible(away); }
        const falling = live && elapsed >= plan.interceptS && elapsed < plan.interceptS + DESCENT_S;
        if (descentShown.get(x.t.threatId) !== falling) { descentShown.set(x.t.threatId, falling); descents.get(x.t.threatId)!.setVisible(falling); }
        if (live && elapsed >= plan.interceptS + DESCENT_S && !landed.has(x.t.threatId)) { landed.add(x.t.threatId); const b = bursts.get(x.t.threatId)!; b.setVisible(true); b.play(); }
      }
    }
    // Base labels: stock left once every launch up to now has gone.
    const baseStyles = new Map<string, MarkerStyle>(BASES.map(b => {
      const launched = live ? [...plans.values()].filter(p => p.base.id === b.id && elapsed >= p.launchS).length : 0;
      return [`base:${b.id}`, { color: BASE_MARKER, size: 10, visible: true, label: `${b.label} · ${b.stock - launched}/${b.stock} ready` }];
    }));
    const baseKey = JSON.stringify([...baseStyles]);
    if (baseKey !== lastBases) { lastBases = baseKey; baseMarkers.setStyles(baseStyles); }
    const circleStyles = new Map<string, CircleStyle>(footprints.map(f => {
      const s = states.get(f.threatId)!;
      const strong = f.threatId === focus;
      const visible = f.kind === "selected" ? s === "locked" || s === "intercepted" : s === "unhandled";
      const colour = f.kind === "selected" ? SELECTED : UNHANDLED;
      return [f.id, { fill: alpha(colour, strong ? 0.5 : 0.3), outline: strong ? "#ffffff" : colour, visible }];
    }));
    const circleKey = JSON.stringify([...circleStyles]);
    if (circleKey !== lastCircles) { lastCircles = circleKey; circles.setStyles(circleStyles); }
    const markerStyles = new Map<string, MarkerStyle>(footprints.map(f => {
      const s = states.get(f.threatId)!;
      const visible = f.kind === "selected" ? s === "locked" || s === "intercepted" : s === "unhandled";
      return [f.id, { color: f.kind === "selected" ? SELECTED : UNHANDLED, size: f.kind === "selected" ? 12 : 16, visible,
        label: `${f.kind === "selected" ? "Intercept" : "Unhandled"} · ${f.threatId}` }];
    }));
    const markerKey = JSON.stringify([...markerStyles]);
    if (markerKey !== lastMarkers) { lastMarkers = markerKey; markers.setStyles(markerStyles); }

    const visibleRows = threats.filter(x => states.get(x.t.threatId) !== "unseen");
    const order = visibleRows.map(x => x.t.threatId).join(",");
    if (order !== lastOrder) {
      lastOrder = order;
      list.threatList.replaceChildren(...visibleRows.map(x => rows.get(x.t.threatId)!.li));
      list.listEmpty.hidden = visibleRows.length > 0;
    }
    let resolved = 0;
    for (const x of visibleRows) {
      const row = rows.get(x.t.threatId)!;
      const s = states.get(x.t.threatId)!;
      if (s === "intercepted" || s === "unhandled") resolved++;
      const at = s === "intercepted" && x.outcome?.resolvedTimeS !== null && x.outcome?.resolvedTimeS !== undefined ? ` · ${formatT(x.outcome.resolvedTimeS)}` : "";
      const who = (s === "locked" || s === "intercepted") && x.outcome?.interceptorId ? ` · ${x.outcome.interceptorId}` : "";
      const plan = plans.get(x.t.threatId);
      const away = plan && (s === "detected" || s === "locked") && elapsed >= plan.launchS;
      setText(row.status, away ? `Interceptor away · ${plan.base.label} · intercept ${formatT(plan.interceptS)}` : `${STATE_LABELS[s]}${who}${at}`);
      row.li.classList.toggle("focused", x.t.threatId === focus);
      if (row.li.dataset.state !== s) row.li.dataset.state = s;
    }
    return { detected: visibleRows.length, resolved, total: threats.length };
  }

  function reset(): void {
    shown.clear(); flightShown.clear(); descentShown.clear(); landed.clear();
    for (const p of paths.values()) p.setVisible(false);
    for (const f of flights.values()) f.setVisible(false);
    for (const d of descents.values()) d.setVisible(false);
    for (const b of bursts.values()) b.setVisible(false);
    lastCircles = lastMarkers = lastOrder = lastBases = "";
    circles.setStyles(new Map());
    markers.setStyles(new Map());
    list.threatList.replaceChildren();
    list.listEmpty.hidden = false;
  }

  const framePoints = [
    ...threats.flatMap(x => x.t.samples.map(s => ({ lon: s.position.lon, lat: s.position.lat }))),
    ...footprints.flatMap(f => circleBounds({ lon: f.center.lon, lat: f.center.lat }, f.radiusM)),
    ...BASES.map(b => b.position),
  ];
  reset();
  // Last, once every layer has built: a construction that throws must leave the shared clock alone.
  canvas.time.setRange(start, new Date(start.getTime() + endS * 1000));
  return {
    result, start, endS, framePoints, render, reset,
    stateOf: (id, elapsed) => stateOf(id, elapsed),
    positionOf: (id, elapsed) => { const x = byId.get(id); return x ? positionAt(x.t, elapsed) : undefined; },
    dispose: () => resources.dispose(),
  };
}

/**
 * The engagement screen. Standby → [Space] submits a Naive and an optimised run on the drawer's
 * scenario, loads both, then replays the optimised result: threats appear as the clock passes their
 * detection. Space after a finished replay starts over. History lists this session's run pairs.
 */
export function mountEngagement(canvas: SingaporeCanvas, panel: HTMLElement, loader: ResultLoader = loadSimulationResult): Engagement {
  // --- fixed screen ---
  const ops = el("aside"); ops.id = "ops"; ops.dataset.view = "live"; ops.setAttribute("aria-label", "Threats and history");
  const listArea = el("section", "list-area"); listArea.setAttribute("aria-label", "Threats");
  const listEmpty = el("p", "empty", "No threats detected.");
  const threatList = el("ol", "threats");
  listArea.append(el("h2", undefined, "Threats"), listEmpty, threatList,
    el("p", "note", "Interceptor bases and flights are illustrative: three fixed sites, speed fitted to the backend's intercept time."));
  const historyView = el("section", "history-view"); historyView.setAttribute("aria-label", "History");
  const historyEmpty = el("p", "empty", "No runs yet.");
  const historyList = el("ul");
  historyView.append(el("h2", undefined, "History"), historyEmpty, historyList);
  ops.append(listArea, historyView);

  const presenter = el("div"); presenter.id = "presenter";
  // Only History: there is no demo to play, Space on detection submits live runs.
  const historyBtn = el("button", undefined, "History");
  historyBtn.type = "button";
  historyBtn.setAttribute("aria-expanded", "false");
  presenter.append(historyBtn);
  const birdsEyeBtn = el("button", undefined, "Bird's-eye view"); birdsEyeBtn.id = "birds-eye"; birdsEyeBtn.type = "button";

  const standby = el("section", "standby-bar"); standby.id = "standby"; standby.setAttribute("aria-label", "Engagement");
  const phaseEl = el("span", "phase"), clockEl = el("span", "clock");
  const head = el("header"); head.append(phaseEl, clockEl);
  const message = el("p", "message"); message.setAttribute("role", "status");
  standby.append(head, message);
  document.body.append(ops, presenter, birdsEyeBtn, standby);

  const setView = (view: "live" | "history"): void => { ops.dataset.view = view; historyBtn.setAttribute("aria-expanded", String(view === "history")); };
  historyBtn.onclick = () => setView(ops.dataset.view === "history" ? "live" : "history");

  // --- state ---
  let phase: Phase = "standby";
  let scenario: ScenarioView | undefined;
  let focus: string | null = null;
  let follow = false;
  const pairs: RunPair[] = [];
  let active: RunPair | null = null;
  let abort = new AbortController();
  let disposed = false;

  const outcome = mountOutcomePanel(canvas, { onSelect: id => pick(id), onReplay: () => { if (phase === "done") reset(); startReplay(); } });

  const loading = mountResultLoader(panel, "Simulation", loader, parseSimulationResult, (result, snapshot) => {
    const resources = new ResultResources(canvas);
    try {
      const view = renderScenario(resources.canvas, result, resources, { threatList, listEmpty }, pick);
      scenario = view; focus = null; follow = false;
      standby.dataset.resultId = snapshot?.resultId ?? "";
      // A pair in flight keeps its phase. Otherwise a result that is not the active pair's optimised run
      // (Refresh, a drawer run) leaves the pair behind.
      if (phase !== "submitting" && phase !== "loading") {
        phase = "standby";
        if (active && snapshot?.resultId !== active.optimised.resultId) { active = null; outcome.setPair(null); renderHistory(); }
      }
      queueMicrotask(() => { if (!disposed && scenario === view) { render(); frameAll(); } });
      return { dispose() { resources.dispose(); if (scenario === view) scenario = undefined; } };
    } catch (error) { resources.dispose(); throw error; }
  });
  const runs = mountRunControls(loading.controls, "simulation", loading.loadIdentity, () => { if (!disposed) render(); });

  // --- framing and focus ---
  const mapRect = () => document.getElementById("scene")?.getBoundingClientRect();
  // Measured on pick, replay start and resize, never per tick: render() does no layout reads.
  let aspect: number | null = null;
  function measure(): void { const map = mapRect(); aspect = map ? viewAspect(map.width, map.height) : null; }
  function frameAll(duration = 1.2): void {
    const map = mapRect();
    measure();
    if (!scenario?.framePoints.length || !map || aspect === null) return;
    const open = document.getElementById("panel-toggle")?.getAttribute("aria-expanded") === "true";
    const drawer = open ? document.getElementById("panel")?.getBoundingClientRect() ?? null : null;
    canvas.camera.flyTo(framePose(scenario.framePoints, STANDBY_PITCH, aspect, 1.15, mapInsets(map, drawer)), { duration }).catch(ignoreCancel);
  }
  function followFocus(elapsed: number): void {
    if (!scenario || !focus) return;
    const p = scenario.positionOf(focus, elapsed);
    if (aspect === null || !p) return;
    const state = scenario.stateOf(focus, elapsed);
    if (state === "intercepted" || state === "unhandled") follow = false; // hold the last pose
    canvas.camera.flyTo(framePose([p, ...circleBounds(p, FOLLOW_RADIUS_M)], -45, aspect, 1), { duration: 0 }).catch(ignoreCancel);
  }
  function pick(threatId: string): void {
    if (!scenario?.result.trajectories.some(t => t.threatId === threatId)) return;
    focus = threatId; follow = true;
    measure();
    outcome.selectThreat(threatId);
    followFocus(elapsedOf(scenario.result, canvas.time.current));
    render();
  }

  // --- run pairs ---
  function standbyText(counts: { detected: number; resolved: number; total: number } | null): string {
    if (!scenario) return "No simulation result loaded";
    if (phase === "loading") return "Loading both results…";
    if (phase === "live" && counts) return `${counts.detected} of ${counts.total} threats detected · ${counts.resolved} resolved`;
    if (phase === "done") {
      const sel = comparable();
      const next = !sel || activeMatches() ? "replay" : `submit Naive + ${POLICY_NAMES[sel.policy] ?? sel.policy} on ${sel.scenarioRef}`;
      return `All threats resolved · press Space to ${next}`;
    }
    if (active && (phase === "submitting" || pairPhase(active) !== "ready" || active.problem || activeMatches())) {
      if (phase === "submitting" || pairPhase(active) === "pending") {
        const side = (label: string, r: RunRef) => `${label} ${r.runId ?? "…"} · ${r.status}`;
        return `${side("Baseline", active.baseline)} · ${side("Optimised", active.optimised)}`;
      }
      const failure = pairFailure(active);
      if (failure) return `Failed · ${failure}`;
      return "Standby — press Space on detection";
    }
    const sel = runs.selection();
    if (!sel) return "Standby — press Space to replay this result alone · pick a frozen scenario in the drawer for a comparison";
    if (sel.policy === BASELINE_POLICY) return "Standby — press Space to replay this result alone · pick a policy other than Naive for a comparison";
    return `Standby — press Space on detection · submits Naive + ${POLICY_NAMES[sel.policy] ?? sel.policy} on ${sel.scenarioRef}`;
  }

  function renderHistory(): void {
    historyList.replaceChildren(...pairs.map(p => {
      const li = el("li");
      const entry = el("button", "entry", `#${p.id} · ${p.scenarioRef} · Naive vs ${POLICY_NAMES[p.optimised.policy] ?? p.optimised.policy} · ${pairPhase(p)}`);
      entry.type = "button";
      entry.setAttribute("aria-pressed", String(p === active));
      entry.disabled = pairPhase(p) !== "ready";
      entry.onclick = () => {
        if (phase !== "standby" && phase !== "done") return;
        abort.abort(); abort = new AbortController();
        setView("live");
        void openPair(p, abort.signal);
      };
      li.append(entry, el("small", undefined, `${p.baseline.runId ?? "…"} · ${p.optimised.runId ?? "…"}`));
      return li;
    }));
    historyEmpty.hidden = pairs.length > 0;
  }

  async function loadParsed(id: string, signal: AbortSignal): Promise<SimulationResult> {
    const raw = await loader(id, signal);
    return parseSimulationResult(isSnapshot(raw) ? raw.result : raw);
  }

  async function run(pair: RunPair, ref: RunRef, signal: AbortSignal): Promise<void> {
    try {
      const first = await submitRun({ kind: "simulation", scenarioRef: pair.scenarioRef, policy: ref.policy }, "simulation", signal);
      Object.assign(ref, first); render();
      Object.assign(ref, await awaitRun(first, "simulation", signal, update => { Object.assign(ref, update); render(); }));
    } catch (error) {
      if (signal.aborted) return;
      ref.status = "failed"; ref.error = { code: "REQUEST_FAILED", message: errorText(error) };
    }
    render();
  }

  async function startPair(): Promise<void> {
    const sel = runs.selection();
    // No comparison possible from the drawer's selection: replay the loaded result on its own.
    if (!sel || sel.policy === BASELINE_POLICY) { startReplay(); return; }
    const pair: RunPair = { id: pairs.length + 1, scenarioRef: sel.scenarioRef,
      baseline: { policy: BASELINE_POLICY, status: "submitting" }, optimised: { policy: sel.policy, status: "submitting" } };
    pairs.push(pair); active = pair; phase = "submitting";
    abort.abort(); abort = new AbortController();
    const signal = abort.signal;
    renderHistory(); render();
    await Promise.all([run(pair, pair.baseline, signal), run(pair, pair.optimised, signal)]);
    if (disposed || signal.aborted) return;
    if (pairPhase(pair) !== "ready") { phase = "standby"; renderHistory(); render(); return; }
    await openPair(pair, signal);
  }

  async function openPair(pair: RunPair, signal: AbortSignal): Promise<void> {
    phase = "loading"; active = pair; renderHistory(); render();
    try {
      const [baseline, optimised] = await Promise.all([pair.baseline.resultId!, pair.optimised.resultId!].map(id => loadParsed(id, signal)));
      const problem = pairProblem(baseline!, optimised!);
      if (problem) throw new Error(problem);
      pair.results = { baseline: baseline as SimulationResultV2, optimised: optimised as SimulationResultV2 };
      delete pair.problem;
      await loading.loadIdentity(pair.optimised.resultId!);
      if (disposed || signal.aborted) return;
      outcome.setPair(pair);
      phase = "standby"; renderHistory(); render();
      if (scenario) startReplay();
    } catch (error) {
      if (disposed || signal.aborted) return;
      pair.problem = errorText(error);
      delete pair.results;
      phase = "standby"; outcome.setPair(pair); renderHistory(); render();
    }
  }

  // --- replay ---
  function startReplay(): void {
    if (!scenario || phase !== "standby") return;
    phase = "live"; setView("live");
    measure();
    canvas.time.seek(scenario.start);
    canvas.time.play(REPLAY_SPEED);
    render();
  }
  /** The drawer's selection, when it can be compared (a frozen scenario with a policy other than Naive). */
  function comparable(): { scenarioRef: string; policy: string } | null {
    const sel = runs.selection();
    return sel && sel.policy !== BASELINE_POLICY ? sel : null;
  }
  /** True when the active pair is what the drawer currently asks for, so Space replays it instead of submitting again. */
  function activeMatches(): boolean {
    if (!active || pairPhase(active) !== "ready" || !active.results) return false;
    const sel = comparable();
    return !sel || (active.scenarioRef === sel.scenarioRef && active.optimised.policy === sel.policy);
  }
  /** Space: a finished replay is reset first; a running one is left alone. */
  function detectNow(): void {
    if (phase === "done") reset();
    if (phase !== "standby") return;
    if (activeMatches()) { startReplay(); return; }
    void startPair();
  }
  function reset(): void {
    if (!scenario || phase === "submitting" || phase === "loading") return;
    phase = "standby"; focus = null; follow = false;
    canvas.time.pause();
    canvas.time.seek(scenario.start);
    scenario.reset();
    render();
    frameAll();
  }

  function setPhaseAttr(): void { if (standby.dataset.phase !== phase) standby.dataset.phase = phase; }
  function render(): void {
    setPhaseAttr();
    if (!scenario) {
      setText(phaseEl, "STANDBY"); setText(clockEl, formatT(0)); setText(message, standbyText(null));
      return;
    }
    const elapsed = elapsedOf(scenario.result, canvas.time.current);
    if (phase === "live" && elapsed >= scenario.endS) { phase = "done"; canvas.time.pause(); setPhaseAttr(); }
    const live = phase === "live" || phase === "done";
    const counts = scenario.render(elapsed, live, focus);
    if (phase === "live" && live && counts.resolved === counts.total && counts.total > 0) { phase = "done"; canvas.time.pause(); setPhaseAttr(); }
    if (follow && phase === "live") followFocus(elapsed);
    setText(clockEl, formatT(Math.max(0, live ? elapsed : 0)));
    setText(phaseEl, phase === "live" ? (focus ? `FOCUS · ${focus}` : "LIVE") : phase.toUpperCase());
    setText(message, standbyText(counts));
  }

  birdsEyeBtn.onclick = () => { follow = false; frameAll(BIRDS_EYE_S); };
  const onKey = (e: KeyboardEvent): void => {
    if (e.ctrlKey || e.metaKey || e.altKey || e.repeat) return;
    if (e.target instanceof HTMLElement && e.target.closest("input, textarea, select")) return; // typing is not a shortcut
    if (e.code === "Space") { e.preventDefault(); detectNow(); }
  };
  window.addEventListener("keydown", onKey);
  window.addEventListener("resize", measure);
  const mapEl = document.getElementById("scene");
  const letGo = (): void => { follow = false; };
  mapEl?.addEventListener("pointerdown", letGo);
  mapEl?.addEventListener("wheel", letGo, { passive: true });
  const offTick = canvas.on("clockTick", () => render());
  render();

  return {
    retry: loading.retry,
    snapshot: loading.snapshot,
    dispose() {
      if (disposed) return;
      disposed = true;
      abort.abort();
      offTick();
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", measure);
      mapEl?.removeEventListener("pointerdown", letGo);
      mapEl?.removeEventListener("wheel", letGo);
      outcome.dispose();
      runs.dispose();
      loading.dispose();
      for (const node of [ops, presenter, birdsEyeBtn, standby]) node.remove();
    },
  };
}
