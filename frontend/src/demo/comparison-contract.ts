export type Stage = "baseline" | "optimised" | "improvement";
export type DimensionCode = "H" | "E" | "D" | "X" | "R" | "A";
export type MetricUnit = "people" | "person-hours" | "days" | "minutes";
export type ExplanationKind = "benefit" | "tradeoff" | "constraint";
export type ExplanationReferenceType = "metric" | "dimension" | "success_probability" | "intercept_time" | "category" | "constraint";

export interface RangeValue {
  low: number;
  central: number;
  high: number;
}

export interface OutcomeMetric extends RangeValue {
  id: string;
  label: string;
  description: string;
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

export interface ExplanationReference {
  type: ExplanationReferenceType;
  id?: string;
}

export interface ComparisonExplanation {
  code: string;
  kind: ExplanationKind;
  references: readonly ExplanationReference[];
  sourceIds: readonly string[];
}

export interface RobustnessEvidence {
  lowerConsequenceSamples: number;
  sampleCount: number;
  method: string;
  sourceIds: readonly string[];
}

export interface ThreatComparison {
  id: string;
  displayId: string;
  condition: string;
  samples: readonly { seconds: number; lon: number; lat: number; height: number }[];
  baseline: Outcome;
  optimised: Outcome;
  explanations: readonly ComparisonExplanation[];
  robustness: RobustnessEvidence;
}

export interface MultiThreatComparisonResult {
  schemaVersion: "multi-threat-comparison/2";
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
  { code: "R", label: "Recovery effort" },
  { code: "A", label: "Additional hazards" },
];

export const DIMENSION_DESCRIPTIONS: Readonly<Record<DimensionCode, string>> = {
  H: "Potential harm to people in the affected area.",
  E: "Loss of healthcare, water, power, transport or other essential services.",
  D: "Reduction in the ability to continue defence and emergency operations.",
  X: "Knock-on disruption caused through connected systems and dependencies.",
  R: "Difficulty and resources required to restore normal operations.",
  A: "Fire, hazardous materials and other secondary dangers.",
};

const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const object = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null;
const referenceTypes: readonly ExplanationReferenceType[] = ["metric", "dimension", "success_probability", "intercept_time", "category", "constraint"];
const knownExplanationKinds: Readonly<Record<string, ExplanationKind>> = {
  human_exposure_reduced: "benefit",
  essential_service_avoided: "benefit",
  capability_continuity_preserved: "benefit",
  capability_continuity_tradeoff: "tradeoff",
  cascade_reduced: "benefit",
  recovery_shortened: "benefit",
  recovery_effort_reduced: "benefit",
  additional_hazard_avoided: "benefit",
  additional_hazard_tradeoff: "tradeoff",
  success_probability_tradeoff: "tradeoff",
  intercept_time_tradeoff: "tradeoff",
  hard_constraint_applied: "constraint",
  uncertainty_preference: "benefit",
};
const requiredExplanationReferences: Readonly<Record<string, readonly ExplanationReferenceType[]>> = {
  human_exposure_reduced: ["metric"],
  essential_service_avoided: ["dimension"],
  capability_continuity_preserved: ["dimension"],
  capability_continuity_tradeoff: ["dimension"],
  cascade_reduced: ["dimension"],
  recovery_shortened: ["metric"],
  recovery_effort_reduced: ["dimension"],
  additional_hazard_avoided: ["dimension"],
  additional_hazard_tradeoff: ["dimension"],
  success_probability_tradeoff: ["success_probability"],
  intercept_time_tradeoff: ["intercept_time"],
  hard_constraint_applied: ["constraint"],
};

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
    if (!object(metric) || typeof metric.id !== "string" || !metric.id || typeof metric.label !== "string" || !metric.label || typeof metric.description !== "string" || !metric.description) throw new Error(`${path}.metrics[${index}] is invalid`);
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
  if (!object(value) || value.schemaVersion !== "multi-threat-comparison/2") throw new Error("Expected multi-threat-comparison/2");
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
  const provenanceSourceIds = new Set(value.provenance.sourceIds as string[]);
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
    const metricSignature = (outcome: Outcome): string => outcome.metrics.map(metric => `${metric.id}:${metric.unit}:${metric.label}:${metric.description}`).join("|");
    const baselineSignature = metricSignature(threat.baseline as Outcome);
    const optimisedSignature = metricSignature(threat.optimised as Outcome);
    if (baselineSignature !== optimisedSignature) throw new Error(`${path} outcomes must contain matching metrics in the same order`);
    const signature = baselineSignature;
    if (expectedMetricSignature === undefined) expectedMetricSignature = signature;
    else if (signature !== expectedMetricSignature) throw new Error(`${path} metrics must match the other threats for scenario aggregation`);
    if (!Array.isArray(threat.explanations) || !threat.explanations.length) throw new Error(`${path}.explanations must not be empty`);
    for (const [explanationIndex, explanation] of threat.explanations.entries()) {
      const explanationPath = `${path}.explanations[${explanationIndex}]`;
      if (!object(explanation) || typeof explanation.code !== "string" || !explanation.code || !["benefit", "tradeoff", "constraint"].includes(String(explanation.kind))) {
        throw new Error(`${explanationPath} identity is invalid`);
      }
      const expectedKind = knownExplanationKinds[explanation.code];
      if (expectedKind && explanation.kind !== expectedKind) throw new Error(`${explanationPath}.kind must be ${expectedKind} for ${explanation.code}`);
      if (!Array.isArray(explanation.references) || !explanation.references.length) throw new Error(`${explanationPath}.references must not be empty`);
      for (const [referenceIndex, reference] of explanation.references.entries()) {
        const referencePath = `${explanationPath}.references[${referenceIndex}]`;
        if (!object(reference) || !referenceTypes.includes(reference.type as ExplanationReferenceType)) throw new Error(`${referencePath} is invalid`);
        if (["metric", "dimension", "category", "constraint"].includes(String(reference.type)) && (typeof reference.id !== "string" || !reference.id)) {
          throw new Error(`${referencePath}.id is required`);
        }
        if (reference.type === "metric" && !(threat.baseline as Outcome).metrics.some(metric => metric.id === reference.id)) throw new Error(`${referencePath} names an unknown metric`);
        if (reference.type === "dimension" && !DIMENSIONS.some(item => item.code === reference.id)) throw new Error(`${referencePath} names an unknown dimension`);
        if (reference.type === "category") {
          const categoryLabels = [...(threat.baseline as Outcome).categories, ...(threat.optimised as Outcome).categories].map(category => category.label);
          if (!categoryLabels.includes(String(reference.id))) throw new Error(`${referencePath} names an unknown category`);
        }
      }
      const presentReferenceTypes = new Set((explanation.references as ExplanationReference[]).map(reference => reference.type));
      for (const requiredType of requiredExplanationReferences[explanation.code] ?? []) {
        if (!presentReferenceTypes.has(requiredType)) throw new Error(`${explanationPath} requires a ${requiredType} reference`);
      }
      if (!Array.isArray(explanation.sourceIds) || !explanation.sourceIds.length || !explanation.sourceIds.every(sourceId => typeof sourceId === "string" && provenanceSourceIds.has(sourceId))) {
        throw new Error(`${explanationPath}.sourceIds must reference provenance.sourceIds`);
      }
    }
    if (!object(threat.robustness) || !Number.isInteger(threat.robustness.lowerConsequenceSamples) || !Number.isInteger(threat.robustness.sampleCount)
      || (threat.robustness.sampleCount as number) < 1 || (threat.robustness.lowerConsequenceSamples as number) < 0
      || (threat.robustness.lowerConsequenceSamples as number) > (threat.robustness.sampleCount as number)
      || typeof threat.robustness.method !== "string" || !threat.robustness.method) throw new Error(`${path}.robustness is invalid`);
    if (!Array.isArray(threat.robustness.sourceIds) || !threat.robustness.sourceIds.length || !threat.robustness.sourceIds.every(sourceId => typeof sourceId === "string" && provenanceSourceIds.has(sourceId))) {
      throw new Error(`${path}.robustness.sourceIds must reference provenance.sourceIds`);
    }
  }
  return value as unknown as MultiThreatComparisonResult;
}
