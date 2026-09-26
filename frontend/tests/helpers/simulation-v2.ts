import result from "../../../data/results/demo-simulation-result.json";

const hash = (digit: string) => `sha256:${digit.repeat(64)}`;

/** A valid simulation-result/2 payload built from the checked-in /1 example. Test input only. */
export function v2Result(options: {
  policy?: string; active?: number; naive?: number; scenarioRef?: string; physical?: Record<string, number>; unhandledLast?: boolean;
} = {}): any {
  const policy = options.policy ?? "optimal-fixed-rank-assignment/1";
  const active = options.active ?? 1.5, naive = options.naive ?? 2.5, exact = 1.0;
  const value = structuredClone(result) as any;
  value.schemaVersion = "simulation-result/2";
  value.outcomes = value.assignments.map((row: any) => ({
    threatId: row.threat_id, outcome: "intercepted", resolvedTimeS: row.interception_time_s, resolvedTime: row.interceptionTime,
    interceptorId: row.interceptor_id, opportunityId: row.opportunity_id, trainingCost: row.consequence_snapshot.training_cost,
  }));
  if (options.unhandledLast) {
    const last = value.outcomes.at(-1);
    value.assignments = value.assignments.filter((row: any) => row.threat_id !== last.threatId);
    value.selectedFootprints = value.selectedFootprints.filter((row: any) => row.threatId !== last.threatId);
    Object.assign(last, { outcome: "unhandled", interceptorId: null, opportunityId: null, resolvedTimeS: null, resolvedTime: null, trainingCost: null });
  }
  const scenarioRef = options.scenarioRef ?? "sg2:validation:000000";
  const split = scenarioRef.split(":")[1];
  const failed = options.unhandledLast === true;
  const reason = failed ? "constraint_violation:test_fixture" : "all_threats_resolved";
  if (options.physical) value.consequenceSummary.physicalComponents = options.physical;
  value.consequenceSummary.ordinalObjectiveCost = active;
  value.policy = { identity: policy, informationScope: policy === "naive-launch-on-detection/1" ? "online-detected-only" : "offline-full-episode" };
  value.policyComparison = {
    active: { policyIdentity: policy, informationScope: value.policy.informationScope, ordinalCost: active, completed: !failed, terminationReason: reason },
    naive: { policyIdentity: "naive-launch-on-detection/1", informationScope: "online-detected-only", ordinalCost: naive, completed: !failed, terminationReason: reason },
    exactReference: { policyIdentity: "optimal-fixed-rank-assignment/1", informationScope: "offline-full-episode", ordinalCost: exact, completed: true,
      terminationReason: "all_threats_resolved", predictedOrdinalCost: exact, exact: true, proofScope: "immutable additive fixed-rank scope", predictedCostMatchesReplay: true },
    activeMinusNaiveCost: active - naive, exactRegret: failed ? null : active - exact,
  };
  value.termination = failed
    ? { reason, completed: false, constraintStatus: "violated", constraintViolation: "test_fixture", terminationTimeS: 100 }
    : { reason, completed: true, constraintStatus: "satisfied", constraintViolation: null, terminationTimeS: 100 };
  value.provenance = {
    scenarioRef, split, profile: "full-standard", seed: value.seed,
    generatorVersion: "singapore-scenario/2", distributionVersion: "singapore-scenario-distribution/1", distributionChecksum: hash("1"),
    providerIdentity: "singapore-demo-v2", providerRuntimeIdentity: "singapore-consequence-provider", providerVersion: "singapore-demo-v2-fixed-rank/2",
    providerConfigChecksum: hash("2"), providerDataChecksum: hash("3"), scenarioConfigChecksum: hash("4"), generatorConfigurationChecksum: hash("5"),
    boundarySourceChecksum: hash("6"), mainIslandGeometryChecksum: hash("7"), simulatorVersion: "centralized-event-simulator/2",
    canonicalEpisodeHash: hash("8"), hashVerified: true, policyIdentity: policy,
  };
  delete value.policyVersusBaseline;
  return value;
}

export const manifest = {
  schemaVersion: "rl-scenario-suites/5", generatorVersion: "singapore-scenario/2",
  distributionVersion: "singapore-scenario-distribution/1", distributionChecksum: hash("0"), providerIdentity: "singapore-demo-v2",
  entries: [{ scenarioRef: "sg2:validation:000000", split: "validation", index: 0, seed: 10000, profile: "balanced", canonicalEpisodeHash: hash("1") }],
};
