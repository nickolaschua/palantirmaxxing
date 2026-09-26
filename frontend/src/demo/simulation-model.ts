/** Pure validation for the separate simulation-result/1 wire contract. */

export interface SimulationPosition { lon: number; lat: number; heightM: number }
export interface SimulationSample {
  sampleIndex: number;
  timeFromDetectionS: number;
  timeFromEpisodeStartS: number;
  time: string;
  position: SimulationPosition;
  verticalVelocityMps: number;
}
export interface SimulationTrajectory {
  threatId: string;
  detectionTimeS: number;
  detectionTime: string;
  samples: readonly SimulationSample[];
}
export interface SimulationFootprint {
  id: string;
  threatId: string;
  opportunityId?: string;
  kind: "selected" | "terminal_counterfactual";
  label: "supplied 100 m area";
  center: SimulationPosition;
  radiusM: number;
  consequence: unknown;
}
export interface SimulationResult {
  schemaVersion: "simulation-result/1";
  episodeSchemaVersion: "simulation-episode/2";
  episodeId: string;
  seed: number;
  start: string;
  end: string;
  trajectories: readonly SimulationTrajectory[];
  assignments: readonly Record<string, unknown>[];
  selectedFootprints: readonly SimulationFootprint[];
  terminalCounterfactualFootprints: readonly SimulationFootprint[];
  consequenceSummary: {
    ordinalObjectiveCost: number;
    physicalComponents: Record<string, number>;
    wording: {
      area: "supplied 100 m area";
      population: "people potentially exposed";
      casualties: "assumption-grade expected casualties";
    };
  };
  policyVersusBaseline: {
    policyIdentity: string;
    policyOrdinalCost: number;
    baselineIdentity: string;
    baselineOrdinalCost: number;
    measuredRelativeImprovement: number | null;
    claim: string;
  };
  provenance: Record<string, unknown>;
  limitations: readonly string[];
}
const object = (value: unknown, name: string): Record<string, unknown> => {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error(`${name} must be an object`);
  return value as Record<string, unknown>;
};
const finite = (value: unknown, name: string): number => {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`${name} must be finite`);
  return value;
};
const text = (value: unknown, name: string): string => {
  if (typeof value !== "string" || value.length === 0) throw new Error(`${name} must be a nonempty string`);
  return value;
};
const array = (value: unknown, name: string): readonly unknown[] => {
  if (!Array.isArray(value)) throw new Error(`${name} must be an array`);
  return value;
};
const instant = (value: unknown, name: string): string => {
  const result = text(value, name);
  if (!Number.isFinite(Date.parse(result))) throw new Error(`${name} must be ISO 8601`);
  return result;
};

function position(value: unknown, name: string): SimulationPosition {
  const row = object(value, name);
  const lon = finite(row.lon, `${name}.lon`), lat = finite(row.lat, `${name}.lat`), heightM = finite(row.heightM, `${name}.heightM`);
  if (lon < -180 || lon > 180 || lat < -90 || lat > 90 || heightM < 0) throw new Error(`${name} is outside coordinate bounds`);
  return { lon, lat, heightM };
}

function footprint(value: unknown, name: string): SimulationFootprint {
  const row = object(value, name);
  const kind = text(row.kind, `${name}.kind`);
  if (kind !== "selected" && kind !== "terminal_counterfactual") throw new Error(`${name}.kind is unsupported`);
  if (row.label !== "supplied 100 m area") throw new Error(`${name}.label must use supplied-area wording`);
  const radiusM = finite(row.radiusM, `${name}.radiusM`);
  if (radiusM !== 100) throw new Error(`${name}.radiusM must be 100`);
  return {
    id: text(row.id, `${name}.id`), threatId: text(row.threatId, `${name}.threatId`),
    ...(row.opportunityId === undefined ? {} : { opportunityId: text(row.opportunityId, `${name}.opportunityId`) }),
    kind, label: row.label, center: position(row.center, `${name}.center`), radiusM,
    consequence: row.consequence,
  };
}

export function parseSimulationResult(value: unknown): SimulationResult {
  const root = object(value, "result");
  if (root.schemaVersion !== "simulation-result/1") throw new Error("unsupported simulation result schema");
  if (root.episodeSchemaVersion !== "simulation-episode/2") throw new Error("simulation-result/1 requires simulation-episode/2");
  const trajectories = array(root.trajectories, "trajectories").map((value, i): SimulationTrajectory => {
    const row = object(value, `trajectories[${i}]`);
    const samples = array(row.samples, `trajectories[${i}].samples`).map((value, j): SimulationSample => {
      const sample = object(value, `trajectories[${i}].samples[${j}]`);
      return {
        sampleIndex: finite(sample.sampleIndex, "sampleIndex"),
        timeFromDetectionS: finite(sample.timeFromDetectionS, "timeFromDetectionS"),
        timeFromEpisodeStartS: finite(sample.timeFromEpisodeStartS, "timeFromEpisodeStartS"),
        time: instant(sample.time, "sample.time"), position: position(sample.position, "sample.position"),
        verticalVelocityMps: finite(sample.verticalVelocityMps, "verticalVelocityMps"),
      };
    });
    if (samples.length !== 20 || samples.some((sample, j) => sample.sampleIndex !== j + 1)) {
      throw new Error(`trajectories[${i}] must contain 20 ordered samples`);
    }
    if (samples[samples.length - 1]?.position.heightM !== 0) throw new Error(`trajectories[${i}] must terminate at height zero`);
    return { threatId: text(row.threatId, "threatId"), detectionTimeS: finite(row.detectionTimeS, "detectionTimeS"),
      detectionTime: instant(row.detectionTime, "detectionTime"), samples };
  });
  if (trajectories.length !== 8 || new Set(trajectories.map(row => row.threatId)).size !== 8) {
    throw new Error("simulation-result/1 requires eight distinct trajectories");
  }
  const selectedFootprints = array(root.selectedFootprints, "selectedFootprints").map((row, i) => footprint(row, `selectedFootprints[${i}]`));
  const terminalCounterfactualFootprints = array(root.terminalCounterfactualFootprints, "terminalCounterfactualFootprints")
    .map((row, i) => footprint(row, `terminalCounterfactualFootprints[${i}]`));
  const assignments = array(root.assignments, "assignments").map((row, i) => object(row, `assignments[${i}]`));
  if (selectedFootprints.length !== 8 || terminalCounterfactualFootprints.length !== 8 || assignments.length !== 8) {
    throw new Error("simulation-result/1 requires eight assignments and both eight-footprint sets");
  }
  const consequence = object(root.consequenceSummary, "consequenceSummary");
  const physical = object(consequence.physicalComponents, "physicalComponents");
  for (const [key, number] of Object.entries(physical)) finite(number, `physicalComponents.${key}`);
  const wording = object(consequence.wording, "wording");
  if (wording.area !== "supplied 100 m area" || wording.population !== "people potentially exposed"
      || wording.casualties !== "assumption-grade expected casualties") throw new Error("simulation consequence wording is not compliant");
  const comparison = object(root.policyVersusBaseline, "policyVersusBaseline");
  const measured = comparison.measuredRelativeImprovement;
  if (measured !== null) finite(measured, "measuredRelativeImprovement");
  return {
    schemaVersion: "simulation-result/1", episodeSchemaVersion: "simulation-episode/2",
    episodeId: text(root.episodeId, "episodeId"), seed: finite(root.seed, "seed"),
    start: instant(root.start, "start"), end: instant(root.end, "end"), trajectories, assignments,
    selectedFootprints, terminalCounterfactualFootprints,
    consequenceSummary: {
      ordinalObjectiveCost: finite(consequence.ordinalObjectiveCost, "ordinalObjectiveCost"),
      physicalComponents: physical as Record<string, number>,
      wording: wording as SimulationResult["consequenceSummary"]["wording"],
    },
    policyVersusBaseline: {
      policyIdentity: text(comparison.policyIdentity, "policyIdentity"),
      policyOrdinalCost: finite(comparison.policyOrdinalCost, "policyOrdinalCost"),
      baselineIdentity: text(comparison.baselineIdentity, "baselineIdentity"),
      baselineOrdinalCost: finite(comparison.baselineOrdinalCost, "baselineOrdinalCost"),
      measuredRelativeImprovement: measured as number | null,
      claim: text(comparison.claim, "claim"),
    },
    provenance: object(root.provenance, "provenance"),
    limitations: array(root.limitations, "limitations").map((row, i) => text(row, `limitations[${i}]`)),
  };
}
