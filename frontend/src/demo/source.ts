import simulationJson from "../../../data/results/demo-simulation-result.json";
import resultJson from "../../../data/results/demo-planning-result.json";
import type { Consequence, DimensionId } from "./decision-model.js";

/**
 * The one way data comes in. Today: the bundled demo result. When the backend
 * serves it, replace the body with a fetch; `parseResult` still validates.
 */
export async function loadPlanningResult(): Promise<unknown> {
  // ponytail: stand-in until the backend supplies `consequence`; delete this line and illustrativeConsequence then.
  return withIllustrativeConsequence(structuredClone(resultJson));
}

const WEIGHTS: [DimensionId, number][] = [["H", 0.35], ["E", 0.2], ["D", 0.2], ["X", 0.15], ["R", 0.05], ["A", 0.05]];

/**
 * Illustration, not backend output: stable made-up figures per candidate so the
 * panel has something to show. Flagged `illustrative`, which the panel labels.
 * D stays unavailable, as it will be in public data (authorised input only).
 */
function illustrativeConsequence(id: string): Consequence {
  let seed = [...id].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) >>> 0, 7);
  const next = (): number => ((seed = (seed * 1103515245 + 12345) >>> 0) % 1000) / 1000;
  const dimensions = WEIGHTS.map(([dim, weight]) => {
    if (dim === "D") return { id: dim, weight, value: null };
    const central = Math.round(15 + next() * 70);
    const spread = Math.round(5 + next() * 15);
    return { id: dim, weight, value: { low: Math.max(0, central - spread), central, high: Math.min(100, central + spread), confidence: "Illustrative" } };
  });
  // Weighted mean over the dimensions that have a value, so the unavailable D is left out rather than counted as 0.
  const known = dimensions.flatMap(d => (d.value ? [{ weight: d.weight, value: d.value }] : []));
  const sum = known.reduce((s, d) => s + d.weight, 0);
  const mean = (pick: (v: { low: number; central: number; high: number }) => number): number =>
    Math.round(known.reduce((s, d) => s + d.weight * pick(d.value), 0) / sum);
  const total = { low: mean(v => v.low), central: mean(v => v.central), high: mean(v => v.high), confidence: "Illustrative" };
  return { total, scenario: "Weekday evening", illustrative: true, dimensions };
}

function withIllustrativeConsequence<T extends { candidates: { id: string; consequence?: unknown }[] }>(result: T): T {
  for (const c of result.candidates) c.consequence ??= illustrativeConsequence(c.id);
  return result;
}

export type ResultLoader = () => Promise<unknown>;

export async function loadSimulationResult(): Promise<unknown> {
  return structuredClone(simulationJson);
}
