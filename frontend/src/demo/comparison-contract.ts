export type Stage = "baseline" | "optimised" | "improvement";
export type DimensionCode = "H" | "E" | "D" | "X" | "R" | "A";
export type MetricUnit = "people" | "person-hours" | "days" | "minutes";

export interface RangeValue {
  low: number;
  central: number;
  high: number;
}

export interface OutcomeMetric extends RangeValue {
  id: string;
  label: string;
  unit: MetricUnit;
}

export interface Outcome {
  policyLabel: string;
  policyDetail: string;
  position: { lon: number; lat: number; height: number };
  timeFromStartS: number;
  successProbability: number;
  metrics: readonly OutcomeMetric[];
  vector: Record<DimensionCode, RangeValue>;
  categories: readonly { label: string; contribution: number; mechanism: string }[];
  sourcedPercent: number;
  assumedPercent: number;
}

export interface ThreatComparison {
  id: string;
  displayId: string;
  condition: string;
  samples: readonly { seconds: number; lon: number; lat: number; height: number }[];
  baseline: Outcome;
  optimised: Outcome;
  reasons: readonly string[];
  tradeoffs: readonly string[];
  robustnessPercent: number;
  simulationCount: number;
}

export interface MultiThreatComparisonResult {
  schemaVersion: "multi-threat-comparison/1";
  scenarioId: string;
  generatedAt: string;
  dataMode: "fixture" | "simulation";
  start: string;
  scorePolicy: { id: string; version: string; weights: Record<DimensionCode, number> };
  threats: readonly ThreatComparison[];
  provenance: { sourceIds: readonly string[]; limitations: readonly string[] };
}

export const DIMENSIONS: readonly { code: DimensionCode; label: string }[] = [
  { code: "H", label: "Human exposure" },
  { code: "E", label: "Essential services" },
  { code: "D", label: "Capability continuity" },
  { code: "X", label: "Cascading effects" },
  { code: "R", label: "Recovery burden" },
  { code: "A", label: "Additional hazards" },
];

const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const object = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null;

function validateRange(value: unknown, path: string, score = false): asserts value is RangeValue {
  if (!object(value) || !finite(value.low) || !finite(value.central) || !finite(value.high)) {
    throw new Error(`${path} must contain finite low, central and high values`);
  }
  if (value.low > value.central || value.central > value.high) throw new Error(`${path} has an invalid low/central/high order`);
  if (score && (value.low < 0 || value.high > 100)) throw new Error(`${path} must stay within 0-100`);
}

function validateOutcome(value: unknown, path: string): asserts value is Outcome {
  if (!object(value)) throw new Error(`${path} must be an object`);
  if (typeof value.policyLabel !== "string" || typeof value.policyDetail !== "string") throw new Error(`${path} needs policy labels`);
  if (!object(value.position) || ![value.position.lon, value.position.lat, value.position.height].every(finite)) throw new Error(`${path}.position is invalid`);
  if (!finite(value.timeFromStartS) || value.timeFromStartS < 0) throw new Error(`${path}.timeFromStartS is invalid`);
  if (!finite(value.successProbability) || value.successProbability < 0 || value.successProbability > 1) throw new Error(`${path}.successProbability must be within 0-1`);
  if (!Array.isArray(value.metrics) || !value.metrics.length) throw new Error(`${path}.metrics must not be empty`);
  const metricIds = new Set<string>();
  for (const [index, metric] of value.metrics.entries()) {
    if (!object(metric) || typeof metric.id !== "string" || !metric.id || typeof metric.label !== "string") throw new Error(`${path}.metrics[${index}] is invalid`);
    if (!["people", "person-hours", "days", "minutes"].includes(String(metric.unit))) throw new Error(`${path}.metrics[${index}].unit is unsupported`);
    if (metricIds.has(metric.id)) throw new Error(`${path} has duplicate metric id ${metric.id}`);
    metricIds.add(metric.id);
    validateRange(metric, `${path}.metrics[${index}]`);
  }
  if (!object(value.vector)) throw new Error(`${path}.vector is invalid`);
  for (const { code } of DIMENSIONS) validateRange(value.vector[code], `${path}.vector.${code}`, true);
  if (!Array.isArray(value.categories)) throw new Error(`${path}.categories must be an array`);
  for (const [index, category] of value.categories.entries()) {
    if (!object(category) || typeof category.label !== "string" || typeof category.mechanism !== "string" || !finite(category.contribution)) {
      throw new Error(`${path}.categories[${index}] is invalid`);
    }
  }
  if (!finite(value.sourcedPercent) || !finite(value.assumedPercent) || value.sourcedPercent < 0 || value.assumedPercent < 0 || Math.abs(value.sourcedPercent + value.assumedPercent - 100) > 0.01) {
    throw new Error(`${path} evidence percentages must total 100`);
  }
}

export function parseComparisonResult(value: unknown): MultiThreatComparisonResult {
  if (!object(value) || value.schemaVersion !== "multi-threat-comparison/1") throw new Error("Expected multi-threat-comparison/1");
  if (typeof value.scenarioId !== "string" || !value.scenarioId) throw new Error("scenarioId is required");
  if (typeof value.generatedAt !== "string" || !Number.isFinite(Date.parse(value.generatedAt))) throw new Error("generatedAt is invalid");
  if (value.dataMode !== "fixture" && value.dataMode !== "simulation") throw new Error("dataMode must be fixture or simulation");
  if (typeof value.start !== "string" || !Number.isFinite(Date.parse(value.start))) throw new Error("start is invalid");
  if (!object(value.scorePolicy) || typeof value.scorePolicy.id !== "string" || typeof value.scorePolicy.version !== "string" || !object(value.scorePolicy.weights)) throw new Error("scorePolicy is invalid");
  let weightTotal = 0;
  for (const { code } of DIMENSIONS) {
    const weight = value.scorePolicy.weights[code];
    if (!finite(weight) || weight < 0) throw new Error(`scorePolicy.weights.${code} is invalid`);
    weightTotal += weight;
  }
  if (!(weightTotal > 0)) throw new Error("scorePolicy weights must include a positive value");
  if (!object(value.provenance) || !Array.isArray(value.provenance.sourceIds) || !value.provenance.sourceIds.every(item => typeof item === "string") || !Array.isArray(value.provenance.limitations) || !value.provenance.limitations.every(item => typeof item === "string")) {
    throw new Error("provenance is invalid");
  }
  if (!Array.isArray(value.threats) || !value.threats.length) throw new Error("threats must not be empty");
  const ids = new Set<string>();
  let expectedMetricSignature: string | undefined;
  for (const [index, threat] of value.threats.entries()) {
    const path = `threats[${index}]`;
    if (!object(threat) || typeof threat.id !== "string" || !threat.id || typeof threat.displayId !== "string" || typeof threat.condition !== "string") throw new Error(`${path} identity is invalid`);
    if (ids.has(threat.id)) throw new Error(`Duplicate threat id ${threat.id}`);
    ids.add(threat.id);
    if (!Array.isArray(threat.samples) || threat.samples.length < 2) throw new Error(`${path}.samples needs at least two points`);
    let previous = -Infinity;
    for (const [sampleIndex, sample] of threat.samples.entries()) {
      if (!object(sample) || ![sample.seconds, sample.lon, sample.lat, sample.height].every(finite) || (sample.seconds as number) <= previous) throw new Error(`${path}.samples[${sampleIndex}] is invalid or out of order`);
      previous = sample.seconds as number;
    }
    validateOutcome(threat.baseline, `${path}.baseline`);
    validateOutcome(threat.optimised, `${path}.optimised`);
    const baselineIds = (threat.baseline as Outcome).metrics.map(metric => metric.id).join("|");
    const optimisedIds = (threat.optimised as Outcome).metrics.map(metric => metric.id).join("|");
    if (baselineIds !== optimisedIds) throw new Error(`${path} outcomes must contain matching metrics in the same order`);
    const signature = (threat.baseline as Outcome).metrics.map(metric => `${metric.id}:${metric.unit}`).join("|");
    if (expectedMetricSignature === undefined) expectedMetricSignature = signature;
    else if (signature !== expectedMetricSignature) throw new Error(`${path} metrics must match the other threats for scenario aggregation`);
    if (!Array.isArray(threat.reasons) || !threat.reasons.every(item => typeof item === "string")) throw new Error(`${path}.reasons is invalid`);
    if (!Array.isArray(threat.tradeoffs) || !threat.tradeoffs.every(item => typeof item === "string")) throw new Error(`${path}.tradeoffs is invalid`);
    if (!finite(threat.robustnessPercent) || threat.robustnessPercent < 0 || threat.robustnessPercent > 100) throw new Error(`${path}.robustnessPercent is invalid`);
    if (!Number.isInteger(threat.simulationCount) || (threat.simulationCount as number) < 1) throw new Error(`${path}.simulationCount is invalid`);
  }
  return value as unknown as MultiThreatComparisonResult;
}
