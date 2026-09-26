/** Pure validation for the versioned simulation-result wire contracts. */

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
export interface SimulationResultV1 {
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
export type SimulationPolicyIdentity = "naive-launch-on-detection/1"
  | "feasible-immediate-matching/1" | "optimal-fixed-rank-assignment/1"
  | "structured-behavior-cloning/1";
export type SimulationInformationScope = "online-detected-only" | "online-observation-only" | "offline-full-episode";
export interface SimulationPolicyRecord {
  policyIdentity: SimulationPolicyIdentity;
  informationScope: SimulationInformationScope;
  ordinalCost: number;
  completed: boolean;
  terminationReason: string;
}
export interface SimulationOutcome {
  threatId: string;
  outcome: "intercepted" | "unhandled";
  resolvedTimeS: number | null;
  resolvedTime: string | null;
  interceptorId: string | null;
  opportunityId: string | null;
  trainingCost: number | null;
}
export interface SimulationResultV2 {
  schemaVersion: "simulation-result/2";
  episodeSchemaVersion: "simulation-episode/2";
  episodeId: string;
  seed: number;
  start: string;
  end: string;
  trajectories: readonly SimulationTrajectory[];
  outcomes: readonly SimulationOutcome[];
  assignments: readonly Record<string, unknown>[];
  selectedFootprints: readonly SimulationFootprint[];
  terminalCounterfactualFootprints: readonly SimulationFootprint[];
  consequenceSummary: SimulationResultV1["consequenceSummary"];
  policy: { identity: SimulationPolicyIdentity; informationScope: SimulationInformationScope;
    artifactIdentity?: string; deploymentStatus?: "experimental-unpromoted" };
  policyComparison: {
    active: SimulationPolicyRecord;
    naive: SimulationPolicyRecord;
    exactReference: SimulationPolicyRecord & {
      predictedOrdinalCost: number;
      exact: true;
      proofScope: string;
      predictedCostMatchesReplay: true;
    };
    activeMinusNaiveCost: number;
    exactRegret: number | null;
  };
  termination: {
    reason: string;
    completed: boolean;
    constraintStatus: "satisfied" | "violated";
    constraintViolation: string | null;
    terminationTimeS: number;
  };
  provenance: {
    scenarioRef: string;
    split: "validation" | "held-out" | "stress" | "ood-geography" | "ood-cadence" | "assignment-reference";
    profile: "warmup" | "balanced" | "full-standard" | "burst-contention" | "low-slack" | "consequence-contrast" | "geographic-shift" | "cadence-shift";
    seed: number;
    generatorVersion: "singapore-scenario/2";
    distributionVersion: "singapore-scenario-distribution/1";
    distributionChecksum: string;
    providerIdentity: "singapore-demo-v2";
    providerRuntimeIdentity: string;
    providerVersion: string;
    providerConfigChecksum: string;
    providerDataChecksum: string;
    scenarioConfigChecksum: string;
    generatorConfigurationChecksum: string;
    boundarySourceChecksum: string;
    mainIslandGeometryChecksum: string;
    simulatorVersion: string;
    canonicalEpisodeHash: string;
    hashVerified: true;
    policyIdentity: SimulationPolicyIdentity;
    policyArtifactIdentity?: string;
    policyDeploymentStatus?: "experimental-unpromoted";
  };
  limitations: readonly string[];
}
export type SimulationResult = SimulationResultV1 | SimulationResultV2;
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

function parseSimulationResultV1(root: Record<string, unknown>): SimulationResultV1 {
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
  const threatIds = new Set(trajectories.map(row => row.threatId));
  const assignmentThreats = new Set<string>(), assignmentInterceptors = new Set<string>();
  const assignmentOpportunities = new Set<string>();
  for (const [i, row] of assignments.entries()) {
    const threatId = text(row.threat_id, `assignments[${i}].threat_id`);
    const interceptorId = text(row.interceptor_id, `assignments[${i}].interceptor_id`);
    const opportunityId = text(row.opportunity_id, `assignments[${i}].opportunity_id`);
    if (!threatIds.has(threatId) || row.status !== "locked") throw new Error(`assignments[${i}] is not a locked known threat`);
    if (assignmentThreats.has(threatId) || assignmentInterceptors.has(interceptorId)
        || assignmentOpportunities.has(opportunityId)) throw new Error("assignment IDs must resolve uniquely");
    assignmentThreats.add(threatId); assignmentInterceptors.add(interceptorId);
    assignmentOpportunities.add(opportunityId);
  }
  for (const [i, row] of selectedFootprints.entries()) {
    if (!assignmentThreats.has(row.threatId) || !row.opportunityId
        || !assignments.some(a => a.threat_id === row.threatId && a.opportunity_id === row.opportunityId)) throw new Error(`selectedFootprints[${i}] does not resolve to an assignment`);
  }
  for (const [items, kind] of [[selectedFootprints, "selected"], [terminalCounterfactualFootprints, "terminal_counterfactual"]] as const) {
    if (new Set(items.map(row => row.id)).size !== 8 || new Set(items.map(row => row.threatId)).size !== 8
        || items.some(row => row.kind !== kind)) throw new Error("Footprint identities or kinds are invalid");
  }
  if (new Set(terminalCounterfactualFootprints.map(row => row.threatId)).size !== 8
      || terminalCounterfactualFootprints.some(row => !threatIds.has(row.threatId))) {
    throw new Error("terminal footprint threat IDs must resolve uniquely");
  }
  const consequence = object(root.consequenceSummary, "consequenceSummary");
  const physical = object(consequence.physicalComponents, "physicalComponents");
  for (const [key, number] of Object.entries(physical)) finite(number, `physicalComponents.${key}`);
  const wording = object(consequence.wording, "wording");
  if (wording.area !== "supplied 100 m area" || wording.population !== "people potentially exposed"
      || wording.casualties !== "assumption-grade expected casualties") throw new Error("simulation consequence wording is not compliant");
  const comparison = object(root.policyVersusBaseline, "policyVersusBaseline");
  const policyIdentity = text(comparison.policyIdentity, "policyIdentity");
  const baselineIdentity = text(comparison.baselineIdentity, "baselineIdentity");
  if (!["feasible-immediate-matching/1", "optimal-fixed-rank-assignment/1"].includes(policyIdentity)
      || baselineIdentity !== "feasible-immediate-matching/1") throw new Error("unknown policy identity/version");
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
      wording: wording as SimulationResultV1["consequenceSummary"]["wording"],
    },
    policyVersusBaseline: {
      policyIdentity,
      policyOrdinalCost: finite(comparison.policyOrdinalCost, "policyOrdinalCost"),
      baselineIdentity,
      baselineOrdinalCost: finite(comparison.baselineOrdinalCost, "baselineOrdinalCost"),
      measuredRelativeImprovement: measured as number | null,
      claim: text(comparison.claim, "claim"),
    },
    provenance: object(root.provenance, "provenance"),
    limitations: array(root.limitations, "limitations").map((row, i) => text(row, `limitations[${i}]`)),
  };
}

const POLICIES = new Map<SimulationPolicyIdentity, SimulationInformationScope>([
  ["naive-launch-on-detection/1", "online-detected-only"],
  ["feasible-immediate-matching/1", "offline-full-episode"],
  ["optimal-fixed-rank-assignment/1", "offline-full-episode"],
  ["structured-behavior-cloning/1", "online-observation-only"],
]);
const SPLITS = new Set(["validation", "held-out", "stress", "ood-geography", "ood-cadence", "assignment-reference"] as const);
const PROFILES = new Set(["warmup", "balanced", "full-standard", "burst-contention", "low-slack", "consequence-contrast", "geographic-shift", "cadence-shift"] as const);
const HASH = /^sha256:[0-9a-f]{64}$/;
const SCENARIO_REF = /^sg2:(validation|held-out|stress|ood-geography|ood-cadence|assignment-reference):[0-9]{6}$/;

function boolean(value: unknown, name: string): boolean {
  if (typeof value !== "boolean") throw new Error(`${name} must be boolean`);
  return value;
}

function nullableFinite(value: unknown, name: string): number | null {
  return value === null ? null : finite(value, name);
}

function parseTrajectoriesV2(value: unknown): readonly SimulationTrajectory[] {
  const trajectories = array(value, "trajectories").map((value, i): SimulationTrajectory => {
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
  if (trajectories.length < 2 || trajectories.length > 8
      || new Set(trajectories.map(row => row.threatId)).size !== trajectories.length) {
    throw new Error("simulation-result/2 requires two through eight distinct trajectories");
  }
  return trajectories;
}

function parsePolicyRecord(value: unknown, name: string, expected?: SimulationPolicyIdentity): SimulationPolicyRecord {
  const row = object(value, name);
  const policyIdentity = text(row.policyIdentity, `${name}.policyIdentity`) as SimulationPolicyIdentity;
  const informationScope = text(row.informationScope, `${name}.informationScope`) as SimulationInformationScope;
  if (!POLICIES.has(policyIdentity) || POLICIES.get(policyIdentity) !== informationScope
      || (expected !== undefined && expected !== policyIdentity)) throw new Error(`${name} has an unsupported policy or information label`);
  return { policyIdentity, informationScope, ordinalCost: finite(row.ordinalCost, `${name}.ordinalCost`),
    completed: boolean(row.completed, `${name}.completed`), terminationReason: text(row.terminationReason, `${name}.terminationReason`) };
}

function parseSimulationResultV2(root: Record<string, unknown>): SimulationResultV2 {
  if (root.episodeSchemaVersion !== "simulation-episode/2") throw new Error("simulation-result/2 requires simulation-episode/2");
  const seed = finite(root.seed, "seed");
  if (!Number.isInteger(seed) || seed < 0 || seed > 2147483647) throw new Error("seed must be a supported integer");
  const trajectories = parseTrajectoriesV2(root.trajectories);
  const threatIds = new Set(trajectories.map(row => row.threatId));
  const assignments = array(root.assignments, "assignments").map((row, i) => object(row, `assignments[${i}]`));
  if (assignments.length > trajectories.length) throw new Error("assignment count exceeds trajectory count");
  const assignmentThreats = new Set<string>(), assignmentInterceptors = new Set<string>(), assignmentOpportunities = new Set<string>();
  for (const [i, row] of assignments.entries()) {
    const threatId = text(row.threat_id, `assignments[${i}].threat_id`);
    const interceptorId = text(row.interceptor_id, `assignments[${i}].interceptor_id`);
    const opportunityId = text(row.opportunity_id, `assignments[${i}].opportunity_id`);
    if (!threatIds.has(threatId) || row.status !== "locked" || assignmentThreats.has(threatId)
        || assignmentInterceptors.has(interceptorId) || assignmentOpportunities.has(opportunityId)) {
      throw new Error("assignment IDs and statuses must resolve uniquely");
    }
    assignmentThreats.add(threatId); assignmentInterceptors.add(interceptorId); assignmentOpportunities.add(opportunityId);
  }
  const selectedFootprints = array(root.selectedFootprints, "selectedFootprints").map((row, i) => footprint(row, `selectedFootprints[${i}]`));
  const terminalCounterfactualFootprints = array(root.terminalCounterfactualFootprints, "terminalCounterfactualFootprints")
    .map((row, i) => footprint(row, `terminalCounterfactualFootprints[${i}]`));
  if (selectedFootprints.length !== assignments.length || terminalCounterfactualFootprints.length !== trajectories.length) {
    throw new Error("trajectory, assignment, and footprint counts do not agree");
  }
  for (const [items, kind, expectedCount] of [[selectedFootprints, "selected", assignments.length],
    [terminalCounterfactualFootprints, "terminal_counterfactual", trajectories.length]] as const) {
    if (new Set(items.map(row => row.id)).size !== expectedCount
        || new Set(items.map(row => row.threatId)).size !== expectedCount
        || items.some(row => row.kind !== kind || !threatIds.has(row.threatId))) {
      throw new Error("footprint identities, kinds, or threat references are invalid");
    }
  }
  if (new Set(selectedFootprints.map(row => row.threatId)).size !== assignmentThreats.size
      || selectedFootprints.some(row => !row.opportunityId || !assignments.some(a => a.threat_id === row.threatId && a.opportunity_id === row.opportunityId))) {
    throw new Error("selected footprints must resolve to assignments exactly");
  }
  const outcomes = array(root.outcomes, "outcomes").map((value, i): SimulationOutcome => {
    const row = object(value, `outcomes[${i}]`);
    const outcome = text(row.outcome, `outcomes[${i}].outcome`);
    if (outcome !== "intercepted" && outcome !== "unhandled") throw new Error("invalid simulation outcome");
    const resolvedTimeS = nullableFinite(row.resolvedTimeS, "resolvedTimeS");
    const resolvedTime = row.resolvedTime === null ? null : instant(row.resolvedTime, "resolvedTime");
    const interceptorId = row.interceptorId === null ? null : text(row.interceptorId, "interceptorId");
    const opportunityId = row.opportunityId === null ? null : text(row.opportunityId, "opportunityId");
    const trainingCost = nullableFinite(row.trainingCost, "trainingCost");
    if ((resolvedTime === null) !== (resolvedTimeS === null)) throw new Error("outcome resolution times must agree");
    if (outcome === "intercepted" && (interceptorId === null || opportunityId === null || resolvedTimeS === null)) throw new Error("intercepted outcome is incomplete");
    if (outcome === "unhandled" && (interceptorId !== null || opportunityId !== null)) throw new Error("unhandled outcome claims an assignment");
    return { threatId: text(row.threatId, "outcome.threatId"), outcome, resolvedTimeS, resolvedTime,
      interceptorId, opportunityId, trainingCost };
  });
  if (outcomes.length !== trajectories.length || new Set(outcomes.map(row => row.threatId)).size !== trajectories.length
      || outcomes.some(row => !threatIds.has(row.threatId))) throw new Error("outcomes must cover every trajectory exactly once");
  const intercepted = new Set(outcomes.filter(row => row.outcome === "intercepted").map(row => row.threatId));
  if (intercepted.size !== assignmentThreats.size || [...intercepted].some(id => !assignmentThreats.has(id))) {
    throw new Error("intercepted outcomes must equal locked assignments");
  }
  for (const row of outcomes.filter(row => row.outcome === "intercepted")) {
    if (!assignments.some(a => a.threat_id === row.threatId && a.interceptor_id === row.interceptorId
      && a.opportunity_id === row.opportunityId)) throw new Error("outcome does not resolve to its assignment");
  }

  const consequence = object(root.consequenceSummary, "consequenceSummary");
  const physical = object(consequence.physicalComponents, "physicalComponents");
  for (const [key, number] of Object.entries(physical)) finite(number, `physicalComponents.${key}`);
  const wording = object(consequence.wording, "wording");
  if (wording.area !== "supplied 100 m area" || wording.population !== "people potentially exposed"
      || wording.casualties !== "assumption-grade expected casualties") throw new Error("simulation consequence wording is not compliant");
  const policy = object(root.policy, "policy");
  const policyIdentity = text(policy.identity, "policy.identity") as SimulationPolicyIdentity;
  const informationScope = text(policy.informationScope, "policy.informationScope") as SimulationInformationScope;
  if (!POLICIES.has(policyIdentity) || POLICIES.get(policyIdentity) !== informationScope) throw new Error("unsupported active policy or information label");
  let artifactIdentity: string | undefined;
  let deploymentStatus: "experimental-unpromoted" | undefined;
  if (policyIdentity === "structured-behavior-cloning/1") {
    artifactIdentity = text(policy.artifactIdentity, "policy.artifactIdentity");
    if (!HASH.test(artifactIdentity)) throw new Error("policy.artifactIdentity must be SHA-256");
    if (policy.deploymentStatus !== "experimental-unpromoted") throw new Error("structured imitation deployment status mismatch");
    deploymentStatus = "experimental-unpromoted";
  }
  const comparison = object(root.policyComparison, "policyComparison");
  const active = parsePolicyRecord(comparison.active, "policyComparison.active", policyIdentity);
  const naive = parsePolicyRecord(comparison.naive, "policyComparison.naive", "naive-launch-on-detection/1");
  const exactRaw = object(comparison.exactReference, "policyComparison.exactReference");
  const exactBase = parsePolicyRecord(exactRaw, "policyComparison.exactReference", "optimal-fixed-rank-assignment/1");
  const predictedOrdinalCost = finite(exactRaw.predictedOrdinalCost, "predictedOrdinalCost");
  if (exactRaw.exact !== true || exactRaw.predictedCostMatchesReplay !== true || !exactBase.completed
      || Math.abs(predictedOrdinalCost - exactBase.ordinalCost) > 1e-12) throw new Error("false exactness or mismatched exact replay");
  const activeMinusNaiveCost = finite(comparison.activeMinusNaiveCost, "activeMinusNaiveCost");
  if (Math.abs(activeMinusNaiveCost - (active.ordinalCost - naive.ordinalCost)) > 1e-12) throw new Error("active/naive comparison mismatch");
  const exactRegret = nullableFinite(comparison.exactRegret, "exactRegret");
  if (active.completed) {
    if (exactRegret === null || exactRegret < -1e-12 || Math.abs(exactRegret - (active.ordinalCost - exactBase.ordinalCost)) > 1e-12) {
      throw new Error("exact regret mismatch");
    }
  } else if (exactRegret !== null) throw new Error("incomplete policy cannot claim exact regret");

  const terminationRaw = object(root.termination, "termination");
  const reason = text(terminationRaw.reason, "termination.reason");
  const completed = boolean(terminationRaw.completed, "termination.completed");
  const constraintStatus = text(terminationRaw.constraintStatus, "constraintStatus");
  const constraintViolation = terminationRaw.constraintViolation === null ? null : text(terminationRaw.constraintViolation, "constraintViolation");
  if (completed !== active.completed || reason !== active.terminationReason) throw new Error("active policy and termination disagree");
  if (completed) {
    if (reason !== "all_threats_resolved" || constraintStatus !== "satisfied" || constraintViolation !== null
        || intercepted.size !== trajectories.length) throw new Error("completed result has inconsistent constraint status");
  } else if (!reason.startsWith("constraint_violation:") || constraintStatus !== "violated" || constraintViolation === null
      || intercepted.size === trajectories.length) throw new Error("failed result has inconsistent constraint status");

  const provenanceRaw = object(root.provenance, "provenance");
  const scenarioRef = text(provenanceRaw.scenarioRef, "scenarioRef");
  const split = text(provenanceRaw.split, "split") as SimulationResultV2["provenance"]["split"];
  const profile = text(provenanceRaw.profile, "profile") as SimulationResultV2["provenance"]["profile"];
  if (!SCENARIO_REF.test(scenarioRef) || !SPLITS.has(split) || !PROFILES.has(profile)
      || !scenarioRef.startsWith(`sg2:${split}:`)) throw new Error("unsupported scenario reference, split, or profile");
  const digestFields = ["distributionChecksum", "providerConfigChecksum", "providerDataChecksum", "scenarioConfigChecksum",
    "generatorConfigurationChecksum", "boundarySourceChecksum", "mainIslandGeometryChecksum", "canonicalEpisodeHash"] as const;
  const digests = Object.fromEntries(digestFields.map(key => {
    const digest = text(provenanceRaw[key], key);
    if (!HASH.test(digest)) throw new Error(`${key} must be a canonical SHA-256 identity`);
    return [key, digest];
  })) as Record<(typeof digestFields)[number], string>;
  if (provenanceRaw.seed !== seed || provenanceRaw.generatorVersion !== "singapore-scenario/2"
      || provenanceRaw.distributionVersion !== "singapore-scenario-distribution/1"
      || provenanceRaw.providerIdentity !== "singapore-demo-v2" || provenanceRaw.hashVerified !== true
      || provenanceRaw.policyIdentity !== policyIdentity) throw new Error("scenario provenance mismatch");
  if (artifactIdentity !== undefined && (provenanceRaw.policyArtifactIdentity !== artifactIdentity
      || provenanceRaw.policyDeploymentStatus !== "experimental-unpromoted")) {
    throw new Error("policy artifact provenance mismatch");
  }
  const provenance: SimulationResultV2["provenance"] = {
    scenarioRef, split, profile, seed,
    generatorVersion: "singapore-scenario/2", distributionVersion: "singapore-scenario-distribution/1",
    distributionChecksum: digests.distributionChecksum, providerIdentity: "singapore-demo-v2",
    providerRuntimeIdentity: text(provenanceRaw.providerRuntimeIdentity, "providerRuntimeIdentity"),
    providerVersion: text(provenanceRaw.providerVersion, "providerVersion"),
    providerConfigChecksum: digests.providerConfigChecksum, providerDataChecksum: digests.providerDataChecksum,
    scenarioConfigChecksum: digests.scenarioConfigChecksum,
    generatorConfigurationChecksum: digests.generatorConfigurationChecksum,
    boundarySourceChecksum: digests.boundarySourceChecksum,
    mainIslandGeometryChecksum: digests.mainIslandGeometryChecksum,
    simulatorVersion: text(provenanceRaw.simulatorVersion, "simulatorVersion"),
    canonicalEpisodeHash: digests.canonicalEpisodeHash, hashVerified: true, policyIdentity,
    ...(artifactIdentity === undefined ? {} : {
      policyArtifactIdentity: artifactIdentity,
      policyDeploymentStatus: deploymentStatus,
    }),
  };
  const exactReference = { ...exactBase, predictedOrdinalCost, exact: true as const,
    proofScope: text(exactRaw.proofScope, "proofScope"), predictedCostMatchesReplay: true as const };
  return {
    schemaVersion: "simulation-result/2", episodeSchemaVersion: "simulation-episode/2",
    episodeId: text(root.episodeId, "episodeId"), seed, start: instant(root.start, "start"), end: instant(root.end, "end"),
    trajectories, outcomes, assignments, selectedFootprints, terminalCounterfactualFootprints,
    consequenceSummary: { ordinalObjectiveCost: finite(consequence.ordinalObjectiveCost, "ordinalObjectiveCost"),
      physicalComponents: physical as Record<string, number>, wording: wording as SimulationResultV1["consequenceSummary"]["wording"] },
    policy: { identity: policyIdentity, informationScope,
      ...(artifactIdentity === undefined ? {} : { artifactIdentity, deploymentStatus }) },
    policyComparison: { active, naive, exactReference, activeMinusNaiveCost, exactRegret },
    termination: { reason, completed, constraintStatus: constraintStatus as "satisfied" | "violated", constraintViolation,
      terminationTimeS: finite(terminationRaw.terminationTimeS, "terminationTimeS") },
    provenance,
    limitations: array(root.limitations, "limitations").map((row, i) => text(row, `limitations[${i}]`)),
  };
}

export function parseSimulationResult(value: unknown): SimulationResult {
  const root = object(value, "result");
  const checkNumbers = (v: unknown): void => {
    if (typeof v === "number") finite(v, "result number");
    if (v && typeof v === "object") Object.values(v).forEach(checkNumbers);
  };
  checkNumbers(root);
  if (root.schemaVersion === "simulation-result/1") return parseSimulationResultV1(root);
  if (root.schemaVersion === "simulation-result/2") return parseSimulationResultV2(root);
  throw new Error("unsupported simulation result schema");
}
