/**
 * Pure logic for the decision demo: planning-result/1 validation, wording,
 * colours, countdowns, deadline positions, flow states and camera framing.
 * No DOM, no Cesium — tests run it directly.
 */
import type { CameraPose, GeoPoint } from "../lib/index.js";

// --- planning-result/1 wire types (frontend/docs/API-DESIGN.md is the source of truth) ---

export interface PlanningTimedSample { time: string; lon: number; lat: number; height: number }
export interface PlanningCandidate {
  id: string;
  sampleIndex: number;
  timeFromStartS: number;
  time: string;
  position: { lon: number; lat: number; height: number };
  reachable: boolean;
  requiredTravelTimeS: number | null;
  timeMarginS: number | null;
  suppliedSuccessProbability?: number;
  exposure?: {
    status: "complete" | "partial_coverage";
    peoplePotentiallyExposed: number | null;
    knownAreaExposure: number;
    coveredAreaFraction: number | null;
  };
  footprint?: { id: string; radiusM: number };
  paretoEfficient: boolean;
  /** The contract lists three values; unknown future ones still render. */
  categories: readonly string[];
  eligibleForRecommendation: boolean;
  ineligibilityReasons: readonly string[];
}
export interface CandidateComparison {
  referenceCandidateId: string;
  comparisonCandidateId: string;
  deltaTimeS: number;
  deltaSuccessProbability: number | null;
  deltaSuccessPercentagePoints: number | null;
  deltaPeoplePotentiallyExposed: number | null;
  relativeExposureChange: number | null;
}
export interface PlanningResult {
  schemaVersion: "planning-result/1";
  scenarioId: string;
  start: string;
  end: string;
  threat: { id: string; samples: readonly PlanningTimedSample[] };
  candidates: readonly PlanningCandidate[];
  paretoCandidateIds: readonly string[];
  categoryAssignments: Record<string, string | null>;
  representativeCandidateIds: readonly string[];
  comparisons: readonly CandidateComparison[];
  diagnostics: Record<string, number>;
  assumptions: {
    successModel: string;
    footprintModel: string;
    footprintRadiusM: number;
    populationExposureMeaning: string;
    kinematicsCalibration: string;
    visualizationHeightM: number;
    heightMeaning: string;
    scenarioTimeMeaning: string;
  };
  populationProvenance: Record<string, string>;
}

/** A representative option, ready to draw: footprint guaranteed. */
export type Option = PlanningCandidate & { footprint: { id: string; radiusM: number } };

// --- validation ---

const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);
const finiteOrNull = (n: unknown): boolean => n === null || finite(n);
const time = (s: unknown): number => (typeof s === "string" ? Date.parse(s) : NaN);

/** Throws with a presenter-readable reason. Runs once, in Standby. */
export function parseResult(value: unknown): { result: PlanningResult; options: Option[] } {
  const r = value as PlanningResult;
  function fail(why: string): never { throw new Error(why); }
  if (r?.schemaVersion !== "planning-result/1") fail(`Unsupported schema "${String(r?.schemaVersion)}" — expected planning-result/1`);
  if (!Number.isFinite(time(r.start)) || !Number.isFinite(time(r.end))) fail("start/end are not valid timestamps");
  const samples = r.threat?.samples;
  if (!Array.isArray(samples) || samples.length < 2) fail("The threat needs at least two samples");
  let previous = -Infinity;
  samples.forEach((s, i) => {
    if (!(time(s.time) > previous) || ![s.lon, s.lat, s.height].every(finite)) fail(`Threat sample ${i} has an invalid time or position`);
    previous = time(s.time);
  });
  if (!Array.isArray(r.candidates) || !Array.isArray(r.representativeCandidateIds) || !Array.isArray(r.comparisons)) fail("Missing candidates, representatives or comparisons");
  const byId = new Map(r.candidates.map(c => [c.id, c]));
  if (byId.size !== r.candidates.length) fail("Candidate IDs are not unique");
  if (!finite(r.assumptions?.footprintRadiusM) || r.assumptions.footprintRadiusM <= 0) fail("assumptions.footprintRadiusM is not a positive number");
  for (const [key, id] of Object.entries(r.categoryAssignments ?? {})) {
    if (id !== null && !byId.has(id)) fail(`categoryAssignments.${key} names an unknown candidate`);
  }
  const options = r.representativeCandidateIds.map(id => {
    const c = byId.get(id) ?? fail(`Representative "${id}" is not a candidate`);
    if (!finite(c.timeFromStartS) || !finiteOrNull(c.timeMarginS) || ![c.position?.lon, c.position?.lat, c.position?.height].every(finite)) fail(`Option "${id}" has non-finite timing or position`);
    if (!c.footprint || !finite(c.footprint.radiusM) || c.footprint.radiusM <= 0) fail(`Option "${id}" has no supplied area`);
    if (c.suppliedSuccessProbability !== undefined && !finite(c.suppliedSuccessProbability)) fail(`Option "${id}" has a non-finite success value`);
    if (c.exposure && (!finiteOrNull(c.exposure.peoplePotentiallyExposed) || !finiteOrNull(c.exposure.coveredAreaFraction))) fail(`Option "${id}" has non-finite exposure`);
    if (!Array.isArray(c.categories)) fail(`Option "${id}" has no categories list`);
    return c as Option;
  });
  for (const cmp of r.comparisons) {
    if (!byId.has(cmp.referenceCandidateId) || !byId.has(cmp.comparisonCandidateId)) fail("A comparison names an unknown candidate");
    if (!finite(cmp.deltaTimeS) || ![cmp.deltaSuccessPercentagePoints, cmp.deltaPeoplePotentiallyExposed, cmp.relativeExposureChange].every(finiteOrNull)) fail("A comparison has non-finite numbers");
  }
  return { result: r, options };
}

// --- wording, colours, formatting ---

/** On-screen labels come from `assumptions`; unknown models get neutral wording. */
export function wording(a: PlanningResult["assumptions"]) {
  return {
    exposure: a.populationExposureMeaning === "estimated_people_potentially_exposed" ? "People potentially exposed" : "Exposure estimate",
    success: a.successModel === "synthetic_linear_decay" ? "Supplied success (synthetic)" : "Supplied success",
    area: a.footprintModel === "supplied_fixed_circle" ? `Supplied ${formatNumber(a.footprintRadiusM)} m area` : "Supplied area",
  };
}

const CATEGORY_LABELS: Record<string, string> = {
  earliest_viable: "Earliest viable", highest_success: "Highest success", lowest_exposure: "Lowest exposure",
};
/** One colour per area, picked in this order. Military green awaits a contract change. */
const CATEGORY_COLOURS: [string, string][] = [
  ["highest_success", "#3d8bff"], ["lowest_exposure", "#ff4d4d"], ["earliest_viable", "#ffb020"],
];
export const FALLBACK_COLOUR = "#b58cff";

export const categoryLabel = (c: string): string =>
  CATEGORY_LABELS[c] ?? (c.replaceAll("_", " ").replace(/^\w/, ch => ch.toUpperCase()) || "Uncategorised");
export const categoryColour = (c: string): string => CATEGORY_COLOURS.find(([k]) => k === c)?.[1] ?? FALLBACK_COLOUR;
export const optionColour = (o: { categories: readonly string[] }): string =>
  CATEGORY_COLOURS.find(([k]) => o.categories.includes(k))?.[1] ?? FALLBACK_COLOUR;

/** The ID's last `__` segment, e.g. "k46". Display only. */
export const shortId = (id: string): string => { const i = id.lastIndexOf("__"); return i < 0 ? id : id.slice(i + 2); };

const MINUS = "−";
export const formatNumber = (n: number, digits = 0): string => n.toLocaleString("en-SG", { maximumFractionDigits: digits });
export const formatT = (s: number): string => `T+${s.toFixed(1)} s`;
export const formatPercent = (p: number): string => `${(p * 100).toFixed(1)}%`;
const signed = (n: number, text: string): string => `${n < 0 ? MINUS : "+"}${text}`;

/** "vs" lines for the outcome summary: chosen minus each other option, from `comparisons`. */
export function comparisonLines(result: PlanningResult, chosenId: string, words = wording(result.assumptions)): { otherId: string; text: string }[] {
  return result.representativeCandidateIds.filter(id => id !== chosenId).map(otherId => {
    const c = result.comparisons.find(x => x.referenceCandidateId === otherId && x.comparisonCandidateId === chosenId);
    if (!c) return { otherId, text: "No comparison supplied" };
    const parts: string[] = [];
    const people = c.deltaPeoplePotentiallyExposed;
    parts.push(people === null
      ? `${words.exposure.toLowerCase()}: not comparable`
      : `${signed(people, formatNumber(Math.abs(people)))} ${words.exposure.toLowerCase()}${c.relativeExposureChange === null ? "" : ` (${signed(c.relativeExposureChange, `${Math.abs(c.relativeExposureChange * 100).toFixed(1)}%`)})`}`);
    if (c.deltaSuccessPercentagePoints !== null) parts.push(`${signed(c.deltaSuccessPercentagePoints, Math.abs(c.deltaSuccessPercentagePoints).toFixed(1))} pp ${words.success.toLowerCase()}`);
    parts.push(`${signed(c.deltaTimeS, Math.abs(c.deltaTimeS).toFixed(1))} s intercept time`);
    return { otherId, text: parts.join(" · ") };
  });
}

// --- time ---

export const elapsedS = (result: PlanningResult, now: Date): number => (now.getTime() - time(result.start)) / 1000;
/** Countdown = timeMarginS − elapsed. Null when the backend supplied no margin. */
export const remainingS = (o: { timeMarginS: number | null }, elapsed: number): number | null =>
  o.timeMarginS === null ? null : o.timeMarginS - elapsed;
export const isOpen = (o: { timeMarginS: number | null }, elapsed: number): boolean => (remainingS(o, elapsed) ?? 0) > 0;
/** 0 with the whole window ahead, 1 at close; 0 when no window was supplied. */
export const urgency = (o: { timeMarginS: number | null }, elapsed: number): number =>
  o.timeMarginS === null || o.timeMarginS <= 0 ? 0 : 1 - Math.max(0, Math.min(1, (o.timeMarginS - elapsed) / o.timeMarginS));

// --- grading, for colour at a glance ---

export type Grade = "good" | "fair" | "poor";
/** Supplied success is a probability, so the marks are fixed: 80% and 50%. */
export const successGrade = (p: number): Grade => (p >= 0.8 ? "good" : p >= 0.5 ? "fair" : "poor");
/**
 * The contract has no absolute scale for people potentially exposed, so a figure
 * is graded only against the other options in the same result: the lowest third
 * of the range is good, the highest third poor. Null when there is nothing to
 * compare with.
 */
export function exposureGrade(value: number, all: readonly number[]): Grade | null {
  const lo = Math.min(...all);
  const hi = Math.max(...all);
  if (!(hi > lo)) return null;
  const t = (value - lo) / (hi - lo);
  return t <= 1 / 3 ? "good" : t >= 2 / 3 ? "poor" : "fair";
}

/** Where the threat is at `atS` seconds after start, holding at the ends like the canvas path. */
export function threatPositionAt(result: PlanningResult, atS: number): { position: GeoPoint; beforePath: boolean } {
  const samples = result.threat.samples;
  const t = time(result.start) + atS * 1000;
  const first = samples[0]!, last = samples[samples.length - 1]!;
  const point = (s: PlanningTimedSample): GeoPoint => ({ lon: s.lon, lat: s.lat, height: s.height });
  if (t <= time(first.time)) return { position: point(first), beforePath: t < time(first.time) };
  if (t >= time(last.time)) return { position: point(last), beforePath: false };
  const i = samples.findIndex(s => time(s.time) >= t);
  const a = samples[i - 1]!, b = samples[i]!;
  const f = (t - time(a.time)) / (time(b.time) - time(a.time));
  return { position: { lon: a.lon + f * (b.lon - a.lon), lat: a.lat + f * (b.lat - a.lat), height: a.height + f * (b.height - a.height) }, beforePath: false };
}

/**
 * Where the threat would have come from: the first two samples' heading and
 * speed, run backwards until `marginKm` outside `bounds`.
 *
 * Illustration only. planning-result/1 supplies no launch origin, so this is
 * drawn dashed and labelled, never presented as planner output. Returns null
 * if the first samples do not move.
 */
export function approachOrigin(
  result: PlanningResult, bounds: { west: number; south: number; east: number; north: number }, marginKm = 6,
): { lon: number; lat: number; height: number; timeFromStartS: number } | null {
  const [a, b] = result.threat.samples;
  if (!a || !b) return null;
  const seconds = (time(b.time) - time(a.time)) / 1000;
  const mPerDegLon = 111_320 * Math.cos((a.lat * Math.PI) / 180);
  // Metres per second, pointing back the way it came.
  const vx = -((b.lon - a.lon) * mPerDegLon) / seconds;
  const vy = -((b.lat - a.lat) * 110_574) / seconds;
  const speed = Math.hypot(vx, vy);
  if (!(speed > 0)) return null;
  // Seconds until the backwards ray leaves the box, then a margin beyond it.
  const edges = [
    vx < 0 ? ((bounds.west - a.lon) * mPerDegLon) / vx : vx > 0 ? ((bounds.east - a.lon) * mPerDegLon) / vx : Infinity,
    vy < 0 ? ((bounds.south - a.lat) * 110_574) / vy : vy > 0 ? ((bounds.north - a.lat) * 110_574) / vy : Infinity,
  ].filter(t => t > 0);
  const travel = Math.min(...edges) + (marginKm * 1000) / speed;
  return {
    lon: a.lon + (vx * travel) / mPerDegLon,
    lat: a.lat + (vy * travel) / 110_574,
    height: a.height,
    timeFromStartS: (time(a.time) - time(result.start)) / 1000 - travel,
  };
}

// --- flow ---

/** Seconds the threat takes to come down into the chosen area after the intercept. */
export const DESCENT_S = 2;

/**
 * Where the threat falls after an intercept: straight down onto the supplied
 * area's centre, easing into the drop.
 *
 * Illustration. planning-result/1 supplies no impact model, debris physics or
 * post-intercept path — only that the area is centred on the intercept point.
 */
export function descentSamples(option: Option, start: Date, steps = 6): { lon: number; lat: number; height: number; time: Date }[] {
  const from = option.timeFromStartS;
  return Array.from({ length: steps + 1 }, (_, i) => {
    const fraction = i / steps;
    return {
      lon: option.position.lon,
      lat: option.position.lat,
      height: option.position.height * (1 - fraction * fraction), // accelerating fall
      time: new Date(start.getTime() + (from + fraction * DESCENT_S) * 1000),
    };
  });
}

export type Phase = "standby" | "live" | "fired" | "impact" | "outcome" | "expired";
export interface Flow { phase: Phase; selected: string | null; fired: string | null }
export const STANDBY: Flow = { phase: "standby", selected: null, fired: null };

export const detect = (flow: Flow): Flow => (flow.phase === "standby" ? { ...flow, phase: "live" } : flow);

export const select = (flow: Flow, options: readonly Option[], id: string, elapsed: number): Flow =>
  flow.phase === "live" && options.some(o => o.id === id && isOpen(o, elapsed)) ? { ...flow, selected: id } : flow;

export const fire = (flow: Flow, options: readonly Option[], elapsed: number): Flow =>
  flow.phase === "live" && flow.selected !== null && options.some(o => o.id === flow.selected && isOpen(o, elapsed))
    ? { phase: "fired", selected: flow.selected, fired: flow.selected }
    : flow;

/** Time-driven transitions: closed windows clear selection, all closed expires, the intercept ends a firing. */
export function advance(flow: Flow, options: readonly Option[], elapsed: number): Flow {
  if (flow.phase === "live") {
    if (!options.some(o => isOpen(o, elapsed))) return { phase: "expired", selected: null, fired: null };
    const stillOpen = flow.selected !== null && options.some(o => o.id === flow.selected && isOpen(o, elapsed));
    return stillOpen || flow.selected === null ? flow : { ...flow, selected: null };
  }
  // Fired → the intercept, then the fall into the area, then the summary.
  if (flow.phase === "fired" || flow.phase === "impact") {
    const chosen = options.find(o => o.id === flow.fired);
    if (!chosen) return flow;
    if (elapsed >= chosen.timeFromStartS + DESCENT_S) return { ...flow, phase: "outcome" };
    if (elapsed >= chosen.timeFromStartS) return flow.phase === "impact" ? flow : { ...flow, phase: "impact" };
  }
  return flow;
}

// --- camera ---

/**
 * A camera pose, heading north at `pitchDeg`, that fits `points` (already padded
 * by the caller) on screen. Cesium's 60° field of view spans the wider screen side.
 */
export function framePose(points: readonly GeoPoint[], pitchDeg: number, aspect: number, margin = 1.2): CameraPose {
  const lons = points.map(p => p.lon), lats = points.map(p => p.lat);
  const lon = (Math.min(...lons) + Math.max(...lons)) / 2;
  const lat = (Math.min(...lats) + Math.max(...lats)) / 2;
  const mPerDegLat = 110_574, mPerDegLon = 111_320 * Math.cos((lat * Math.PI) / 180);
  const halfW = ((Math.max(...lons) - Math.min(...lons)) / 2) * mPerDegLon;
  const halfH = ((Math.max(...lats) - Math.min(...lats)) / 2) * mPerDegLat;
  const half = Math.PI / 6; // 60° / 2
  const [hHalf, vHalf] = aspect >= 1 ? [half, Math.atan(Math.tan(half) / aspect)] : [Math.atan(Math.tan(half) * aspect), half];
  const tilt = (Math.abs(pitchDeg) * Math.PI) / 180;
  const distance = margin * Math.max(halfW / Math.tan(hHalf), (halfH * Math.sin(tilt)) / Math.tan(vHalf));
  return {
    lon,
    lat: lat - (distance * Math.cos(tilt)) / mPerDegLat, // stand back to the south
    height: distance * Math.sin(tilt),
    heading: 0,
    pitch: -Math.abs(pitchDeg),
  };
}

/** Padding points for a circle, so framing includes its full radius. */
export function circleBounds(center: { lon: number; lat: number }, radiusM: number): GeoPoint[] {
  const dLat = radiusM / 110_574, dLon = radiusM / (111_320 * Math.cos((center.lat * Math.PI) / 180));
  return [{ lon: center.lon - dLon, lat: center.lat - dLat }, { lon: center.lon + dLon, lat: center.lat + dLat }];
}
