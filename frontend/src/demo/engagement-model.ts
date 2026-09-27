/** Pure logic for the engagement screen: threat states over time, the replay clock, and the two-run comparison. No DOM, no Cesium. */
import { formatNumber } from "./decision-model.ts";
import type { FrozenPolicy } from "./scenario-manifest-model.ts";
import type { SimulationFootprint, SimulationOutcome, SimulationResult, SimulationResultV2, SimulationTrajectory } from "./simulation-model.ts";
import { BASES, groundDistanceM, INTERCEPTOR_SPEED_MPS, interceptorSamples } from "./interceptor-model.ts";
import type { InterceptorBase, InterceptTarget } from "./interceptor-model.ts";

export type ThreatState = "unseen" | "detected" | "locked" | "intercepted" | "unhandled";
export const STATE_LABELS: Record<ThreatState, string> = {
  unseen: "Not detected", detected: "Detected", locked: "Interceptor locked", intercepted: "Intercepted", unhandled: "Unhandled",
};
export const POLICY_NAMES: Record<string, string> = {
  "naive-launch-on-detection/1": "Naive",
  "optimal-fixed-rank-assignment/1": "Exact",
  "structured-behavior-cloning/1": "Imitation",
  "feasible-immediate-matching/1": "Matching",
};
export const BASELINE_POLICY: FrozenPolicy = "naive-launch-on-detection/1";

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" && v ? v : null);

/** simulation-result/2 carries outcomes; /1 has one successful assignment per threat, so every threat was intercepted. */
export function outcomesOf(result: SimulationResult): SimulationOutcome[] {
  if (result.schemaVersion === "simulation-result/2") return [...result.outcomes];
  return result.assignments.map(row => {
    const snapshot = row.consequence_snapshot as Record<string, unknown> | undefined;
    return {
      threatId: str(row.threat_id) ?? "", outcome: "intercepted" as const,
      resolvedTimeS: num(row.interception_time_s), resolvedTime: str(row.interceptionTime),
      interceptorId: str(row.interceptor_id), opportunityId: str(row.opportunity_id),
      trainingCost: num(snapshot?.training_cost),
    };
  });
}

/** Assignments are untyped records; the lock time is read when present under either spelling. */
export function lockTimeOf(result: SimulationResult, threatId: string): number | null {
  const row = result.assignments.find(a => a.threat_id === threatId || a.threatId === threatId);
  if (!row) return null;
  const s = num(row.lock_time_s);
  if (s !== null) return s;
  const iso = str(row.lockTime);
  return iso ? (new Date(iso).getTime() - new Date(result.start).getTime()) / 1000 : null;
}

export function threatStateAt(t: SimulationTrajectory, outcome: SimulationOutcome | undefined, lockAtS: number | null, elapsedS: number): ThreatState {
  if (elapsedS < t.detectionTimeS) return "unseen";
  const endS = outcome?.resolvedTimeS ?? t.samples.at(-1)?.timeFromEpisodeStartS ?? t.detectionTimeS;
  if (elapsedS >= endS) return outcome?.outcome === "intercepted" ? "intercepted" : "unhandled";
  if (lockAtS !== null && elapsedS >= lockAtS) return "locked";
  return "detected";
}

/** The clock runs until every track has ended and every outcome has resolved. */
export function clockEndS(result: SimulationResult): number {
  const episode = (new Date(result.end).getTime() - new Date(result.start).getTime()) / 1000;
  const tracks = result.trajectories.map(t => t.samples.at(-1)?.timeFromEpisodeStartS ?? 0);
  const resolved = outcomesOf(result).map(o => o.resolvedTimeS ?? 0);
  return Math.max(0, episode, ...tracks, ...resolved);
}

export const elapsedOf = (result: SimulationResult, now: Date): number => (now.getTime() - new Date(result.start).getTime()) / 1000;

/** Linear interpolation along the supplied samples by episode time; clamped to the ends. */
export function positionAt(t: SimulationTrajectory, atS: number): { lon: number; lat: number; height: number } {
  const first = t.samples[0]!, last = t.samples.at(-1)!;
  if (atS <= first.timeFromEpisodeStartS) return { lon: first.position.lon, lat: first.position.lat, height: first.position.heightM };
  if (atS >= last.timeFromEpisodeStartS) return { lon: last.position.lon, lat: last.position.lat, height: last.position.heightM };
  const i = t.samples.findIndex(s => s.timeFromEpisodeStartS > atS);
  const a = t.samples[i - 1]!, b = t.samples[i]!;
  const f = (atS - a.timeFromEpisodeStartS) / Math.max(1e-9, b.timeFromEpisodeStartS - a.timeFromEpisodeStartS);
  return {
    lon: a.position.lon + (b.position.lon - a.position.lon) * f,
    lat: a.position.lat + (b.position.lat - a.position.lat) * f,
    height: a.position.heightM + (b.position.heightM - a.position.heightM) * f,
  };
}

export interface Insets { left: number; right: number; top: number; bottom: number }
/** Width over height, or null when the view has no size (display: none, not laid out yet): framing must wait. */
export const viewAspect = (width: number, height: number): number | null => (width > 0 && height > 0 ? width / height : null);
/** What covers the map, as fractions of it: only the open drawer, from the map's left edge to the drawer's right edge. */
export function mapInsets(map: { left: number; right: number }, panel: { right: number } | null): Insets {
  const width = map.right - map.left;
  const covered = panel ? Math.min(panel.right, map.right) - map.left : 0;
  return { left: width > 0 ? Math.max(0, covered) / width : 0, right: 0, top: 0, bottom: 0 };
}

/** ▼ where it went down, ▲ where it went up; `worse` marks a trade-off given which direction is better. */
export function changeText(baseline: number, optimised: number, higherIsBetter: boolean): { text: string; worse: boolean } {
  const diff = optimised - baseline;
  if (Math.abs(diff) < 1e-9) return { text: "no change", worse: false };
  const size = baseline === 0 ? formatNumber(Math.abs(diff), 3) : `${Math.round((Math.abs(diff) / Math.abs(baseline)) * 100)}%`;
  return { text: `${diff < 0 ? "▼" : "▲"} ${size}`, worse: higherIsBetter ? diff < 0 : diff > 0 };
}

export interface SummaryRow { id: string; label: string; baseline: string; optimised: string; change: string; worse: boolean; unavailable: boolean }

const interceptedCount = (r: SimulationResult): number => outcomesOf(r).filter(o => o.outcome === "intercepted").length;

/** The all-missiles rows. Every figure is a backend total; a missing one is "unavailable" and gets no change. */
export function summaryRows(baseline: SimulationResult, optimised: SimulationResult): SummaryRow[] {
  const row = (id: string, label: string, b: number | undefined, o: number | undefined, higherIsBetter: boolean, digits = 0, suffix = (_r: SimulationResult) => ""): SummaryRow => {
    const show = (v: number | undefined, r: SimulationResult) => (v === undefined ? "unavailable" : formatNumber(v, digits) + suffix(r));
    const change = b === undefined || o === undefined ? { text: "", worse: false } : changeText(b, o, higherIsBetter);
    return { id, label, baseline: show(b, baseline), optimised: show(o, optimised), change: change.text, worse: change.worse, unavailable: b === undefined || o === undefined };
  };
  const pc = (r: SimulationResult, key: string) => r.consequenceSummary.physicalComponents[key];
  return [
    row("people", "People potentially exposed", pc(baseline, "people_potentially_exposed_total"), pc(optimised, "people_potentially_exposed_total"), false),
    row("casualties", "Assumption-grade expected casualties", pc(baseline, "expected_casualties_central_total"), pc(optimised, "expected_casualties_central_total"), false),
    row("cost", "Ordinal objective cost", baseline.consequenceSummary.ordinalObjectiveCost, optimised.consequenceSummary.ordinalObjectiveCost, false, 3),
    row("intercepted", "Threats intercepted", interceptedCount(baseline), interceptedCount(optimised), true, 0, r => ` of ${r.trajectories.length}`),
  ];
}

/** The optimised run records the naive cost it was scored against; the separate naive run should agree. */
export const naiveCostMismatch = (baseline: SimulationResultV2, optimised: SimulationResultV2): boolean =>
  Math.abs(baseline.policyComparison.active.ordinalCost - optimised.policyComparison.naive.ordinalCost) > 1e-6;

/** Why two results cannot be compared, or null when they can. */
export function pairProblem(baseline: SimulationResult, optimised: SimulationResult): string | null {
  if (baseline.schemaVersion !== "simulation-result/2" || optimised.schemaVersion !== "simulation-result/2") return "Comparison needs simulation-result/2 on both sides";
  if (baseline.provenance.scenarioRef !== optimised.provenance.scenarioRef) return "Runs are on different scenarios";
  if (baseline.policy.identity !== BASELINE_POLICY) return `Baseline run is ${baseline.policy.identity}, not ${BASELINE_POLICY}`;
  return null;
}

export interface ThreatDetail {
  outcome: "intercepted" | "unhandled" | "unknown";
  interceptorId: string | null; opportunityId: string | null; resolvedTimeS: number | null; trainingCost: number | null;
  footprint: SimulationFootprint | undefined;
}
export function threatDetail(result: SimulationResult, threatId: string): ThreatDetail {
  const o = outcomesOf(result).find(row => row.threatId === threatId);
  return {
    outcome: o?.outcome ?? "unknown",
    interceptorId: o?.interceptorId ?? null, opportunityId: o?.opportunityId ?? null,
    resolvedTimeS: o?.resolvedTimeS ?? null, trainingCost: o?.trainingCost ?? null,
    footprint: result.selectedFootprints.find(f => f.threatId === threatId),
  };
}

/** A consequence snapshot has no fixed shape by contract, so it is shown as the key/value pairs it holds. */
export function flattenSnapshot(value: unknown, prefix = ""): { key: string; value: string }[] {
  if (value === null || value === undefined) return [{ key: prefix || "value", value: "unavailable" }];
  if (typeof value === "number") return [{ key: prefix || "value", value: formatNumber(value, 3) }];
  if (typeof value === "boolean") return [{ key: prefix || "value", value: value ? "yes" : "no" }];
  if (typeof value === "string") return [{ key: prefix || "value", value }];
  if (Array.isArray(value)) return [{ key: prefix || "value", value: value.length ? value.map(v => (typeof v === "object" && v !== null ? JSON.stringify(v) : String(v))).join(", ") : "none" }];
  return Object.entries(value as Record<string, unknown>).flatMap(([k, v]) => flattenSnapshot(v, prefix ? `${prefix} · ${k}` : k));
}

export interface RunRef {
  policy: FrozenPolicy;
  status: "submitting" | "queued" | "running" | "succeeded" | "failed";
  runId?: string; resultId?: string; error?: { code: string; message: string };
}
export interface RunPair {
  id: number; scenarioRef: string; baseline: RunRef; optimised: RunRef;
  results?: { baseline: SimulationResultV2; optimised: SimulationResultV2 };
  problem?: string;
}
export const pairPhase = (p: RunPair): "pending" | "ready" | "failed" =>
  p.baseline.status === "failed" || p.optimised.status === "failed" ? "failed"
  : p.baseline.status === "succeeded" && p.optimised.status === "succeeded" ? "ready" : "pending";
export function pairFailure(p: RunPair): string | null {
  for (const [side, ref] of [["Baseline", p.baseline], ["Optimised", p.optimised]] as const) {
    if (ref.status === "failed") return `${side} run failed · ${ref.error?.code ?? "UNKNOWN"}: ${ref.error?.message ?? "no message"}`;
  }
  return p.problem ?? null;
}

/** Seconds after detection before a base can launch. */
export const REACTION_S = 1;

/**
 * Where and when the backend met this threat: the assignment's intercept position and time, or, for a
 * record without one, the threat's own position at its resolved time. Null for threats not intercepted.
 */
export function interceptTargetOf(result: SimulationResult, threatId: string): InterceptTarget | null {
  const o = outcomesOf(result).find(row => row.threatId === threatId);
  if (!o || o.outcome !== "intercepted" || o.resolvedTimeS === null) return null;
  const row = result.assignments.find(a => a.threat_id === threatId || a.threatId === threatId);
  const p = row?.position as { lon?: unknown; lat?: unknown; heightM?: unknown } | undefined;
  const timeS = num(row?.interception_time_s) ?? o.resolvedTimeS;
  if (p && typeof p.lon === "number" && typeof p.lat === "number") {
    return { position: { lon: p.lon, lat: p.lat, height: num(p.heightM) ?? num(row?.position_z_m) ?? 0 }, timeFromStartS: timeS };
  }
  const t = result.trajectories.find(row => row.threatId === threatId);
  return t ? { position: positionAt(t, timeS), timeFromStartS: timeS } : null;
}

export interface InterceptPlan {
  threatId: string; base: InterceptorBase; launchS: number; interceptS: number; speedMps: number; distanceM: number;
  target: InterceptTarget; samples: { lon: number; lat: number; height: number; time: Date }[];
}

/**
 * One interceptor per backend-intercepted threat, in intercept order, from the nearest base with stock.
 * Illustration, not backend output: the sites are fixed, and the flight launches as late as 400 m/s
 * allows (never sooner than REACTION_S after detection) or, when that cannot make the meet, at
 * detection + REACTION_S at whatever speed the backend's intercept time requires.
 */
export function planIntercepts(result: SimulationResult, bases: readonly InterceptorBase[] = BASES): { plans: Map<string, InterceptPlan>; stock: Map<string, number> } {
  const start = new Date(result.start);
  const stock = new Map(bases.map(b => [b.id, b.stock]));
  const plans = new Map<string, InterceptPlan>();
  const detection = new Map(result.trajectories.map(t => [t.threatId, t.detectionTimeS]));
  const targets = result.trajectories.flatMap(t => { const target = interceptTargetOf(result, t.threatId); return target ? [{ threatId: t.threatId, target }] : []; })
    .sort((a, b) => a.target.timeFromStartS - b.target.timeFromStartS);
  for (const { threatId, target } of targets) {
    const ready = bases.filter(b => (stock.get(b.id) ?? 0) > 0);
    if (!ready.length) break;
    const base = ready.reduce((best, b) => (groundDistanceM(b.position, target.position) < groundDistanceM(best.position, target.position) ? b : best));
    const distanceM = groundDistanceM(base.position, target.position);
    const interceptS = target.timeFromStartS;
    const earliestS = (detection.get(threatId) ?? 0) + REACTION_S;
    let launchS = Math.max(earliestS, interceptS - distanceM / INTERCEPTOR_SPEED_MPS);
    if (launchS >= interceptS) launchS = Math.max(0, Math.min(earliestS - REACTION_S, interceptS - 0.5));
    const flightS = Math.max(1e-3, interceptS - launchS);
    stock.set(base.id, (stock.get(base.id) ?? 0) - 1);
    plans.set(threatId, { threatId, base, launchS, interceptS, speedMps: distanceM / flightS, distanceM, target,
      samples: interceptorSamples(base, target, { launchS, flightS }, start) });
  }
  return { plans, stock };
}

/** Seconds the struck threat takes to fall from the meet to the supplied area. */
export const DESCENT_S = 3;

/**
 * Where the threat falls after the meet: from the intercept point onto the supplied area's centre,
 * easing into the drop. Illustration: the result supplies no debris model, only the area.
 */
export function descentSamples(
  from: { lon: number; lat: number; height: number }, to: { lon: number; lat: number }, atS: number, start: Date, steps = 6,
): { lon: number; lat: number; height: number; time: Date }[] {
  return Array.from({ length: steps + 1 }, (_, i) => {
    const f = i / steps;
    return {
      lon: from.lon + (to.lon - from.lon) * f,
      lat: from.lat + (to.lat - from.lat) * f,
      height: from.height * (1 - f * f), // accelerating fall
      time: new Date(start.getTime() + (atS + f * DESCENT_S) * 1000),
    };
  });
}

/** Height and 3-D speed of a threat at `atS`, from the second before it (or after, at the very start). */
export function kinematicsAt(t: SimulationTrajectory, atS: number): { heightM: number; speedMps: number } {
  const here = positionAt(t, atS);
  const before = atS - 1 >= t.samples[0]!.timeFromEpisodeStartS ? positionAt(t, atS - 1) : positionAt(t, atS + 1);
  const mPerDegLon = 111_320 * Math.cos((here.lat * Math.PI) / 180);
  const d = Math.hypot((here.lon - before.lon) * mPerDegLon, (here.lat - before.lat) * 110_574, here.height - before.height);
  return { heightM: here.height, speedMps: d };
}
export const formatHeight = (m: number): string => (m < 1000 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toFixed(1)} km`);
export const formatSpeed = (mps: number): string => `${Math.round(mps / 10) * 10} m/s`;
