import assert from "node:assert/strict";
import test from "node:test";
import result from "../../data/results/demo-simulation-result.json" with { type: "json" };
import { parseSimulationResult } from "../../frontend/src/demo/simulation-model.ts";

test("checked-in simulation-result/1 parses as eight complete trajectories", () => {
  const parsed = parseSimulationResult(result);
  assert.equal(parsed.trajectories.length, 8);
  assert.equal(parsed.assignments.length, 8);
  assert.ok(parsed.trajectories.every(row => row.samples.length === 20));
  assert.ok(parsed.trajectories.every(row => row.samples.at(-1)?.position.heightM === 0));
  assert.equal(parsed.consequenceSummary.wording.area, "supplied 100 m area");
  assert.ok(!parsed.policyVersusBaseline.claim.startsWith("optimal"));
});

test("parser rejects legacy planning results and validated-blast wording", () => {
  assert.throws(() => parseSimulationResult({ schemaVersion: "planning-result/1" }), /unsupported/);
  const changed = structuredClone(result) as any;
  changed.consequenceSummary.wording.area = "validated blast radius";
  assert.throws(() => parseSimulationResult(changed), /wording/);
});

test("parser rejects radius, assignment, coordinate, and policy contract drift", () => {
  const radius = structuredClone(result) as any;
  radius.selectedFootprints[0].radiusM = 101;
  assert.throws(() => parseSimulationResult(radius), /100/);
  const missing = structuredClone(result) as any;
  missing.assignments.pop();
  assert.throws(() => parseSimulationResult(missing), /eight assignments/);
  const coordinate = structuredClone(result) as any;
  coordinate.trajectories[0].samples[0].position.lon = 181;
  assert.throws(() => parseSimulationResult(coordinate), /coordinate bounds/);
  const policy = structuredClone(result) as any;
  policy.policyVersusBaseline.policyIdentity = "unknown-policy/9";
  assert.throws(() => parseSimulationResult(policy), /unknown policy/);
});

const hash = (digit: string) => `sha256:${digit.repeat(64)}`;
function v2Fixture(count = 8): any {
  const value = structuredClone(result) as any;
  value.schemaVersion = "simulation-result/2";
  value.trajectories = value.trajectories.slice(0, count);
  const threats = new Set(value.trajectories.map((row: any) => row.threatId));
  value.assignments = value.assignments.filter((row: any) => threats.has(row.threat_id));
  value.selectedFootprints = value.selectedFootprints.filter((row: any) => threats.has(row.threatId));
  value.terminalCounterfactualFootprints = value.terminalCounterfactualFootprints.filter((row: any) => threats.has(row.threatId));
  value.outcomes = value.assignments.map((row: any) => ({
    threatId: row.threat_id, outcome: "intercepted", resolvedTimeS: row.interception_time_s,
    resolvedTime: row.interceptionTime, interceptorId: row.interceptor_id,
    opportunityId: row.opportunity_id, trainingCost: row.consequence_snapshot.training_cost,
  }));
  const active = 1.5, naive = 1.7, exact = 1.0;
  value.consequenceSummary.ordinalObjectiveCost = active;
  value.policy = { identity: "feasible-immediate-matching/1", informationScope: "offline-full-episode" };
  value.policyComparison = {
    active: { policyIdentity: value.policy.identity, informationScope: value.policy.informationScope,
      ordinalCost: active, completed: true, terminationReason: "all_threats_resolved" },
    naive: { policyIdentity: "naive-launch-on-detection/1", informationScope: "online-detected-only",
      ordinalCost: naive, completed: true, terminationReason: "all_threats_resolved" },
    exactReference: { policyIdentity: "optimal-fixed-rank-assignment/1", informationScope: "offline-full-episode",
      ordinalCost: exact, completed: true, terminationReason: "all_threats_resolved",
      predictedOrdinalCost: exact, exact: true, proofScope: "immutable additive fixed-rank scope",
      predictedCostMatchesReplay: true },
    activeMinusNaiveCost: active - naive, exactRegret: active - exact,
  };
  value.termination = { reason: "all_threats_resolved", completed: true, constraintStatus: "satisfied",
    constraintViolation: null, terminationTimeS: 100 };
  value.provenance = {
    scenarioRef: "sg2:validation:000017", split: "validation", profile: count === 2 ? "warmup" : "full-standard",
    seed: value.seed, generatorVersion: "singapore-scenario/2", distributionVersion: "singapore-scenario-distribution/1",
    distributionChecksum: hash("1"), providerIdentity: "singapore-demo-v2",
    providerRuntimeIdentity: "singapore-consequence-provider", providerVersion: "singapore-demo-v2-fixed-rank/2",
    providerConfigChecksum: hash("2"), providerDataChecksum: hash("3"), scenarioConfigChecksum: hash("4"),
    generatorConfigurationChecksum: hash("5"), boundarySourceChecksum: hash("6"),
    mainIslandGeometryChecksum: hash("7"), simulatorVersion: "centralized-event-simulator/2",
    canonicalEpisodeHash: hash("8"), hashVerified: true, policyIdentity: value.policy.identity,
  };
  return value;
}

test("simulation-result/2 accepts valid two- and eight-threat replays", () => {
  for (const count of [2, 8]) {
    const parsed = parseSimulationResult(v2Fixture(count));
    assert.equal(parsed.schemaVersion, "simulation-result/2");
    assert.equal(parsed.trajectories.length, count);
    assert.equal(parsed.assignments.length, count);
  }
});

test("simulation-result/2 accepts a recorded naive constraint failure", () => {
  const failure = v2Fixture(2);
  failure.policy = { identity: "naive-launch-on-detection/1", informationScope: "online-detected-only" };
  failure.provenance.policyIdentity = failure.policy.identity;
  failure.assignments.pop(); failure.selectedFootprints.pop();
  failure.outcomes[1] = { threatId: failure.trajectories[1].threatId, outcome: "unhandled",
    resolvedTimeS: 45, resolvedTime: "2026-09-26T04:00:45.000000Z", interceptorId: null,
    opportunityId: null, trainingCost: 9 };
  failure.policyComparison.active = { policyIdentity: failure.policy.identity, informationScope: failure.policy.informationScope,
    ordinalCost: 9, completed: false, terminationReason: "constraint_violation:unhandled_threat" };
  failure.policyComparison.naive = structuredClone(failure.policyComparison.active);
  failure.policyComparison.activeMinusNaiveCost = 0;
  failure.policyComparison.exactRegret = null;
  failure.termination = { reason: "constraint_violation:unhandled_threat", completed: false,
    constraintStatus: "violated", constraintViolation: "unhandled_threat", terminationTimeS: 45 };
  const parsed = parseSimulationResult(failure);
  assert.equal(parsed.schemaVersion, "simulation-result/2");
  assert.equal(parsed.outcomes.filter(row => row.outcome === "unhandled").length, 1);
});

test("simulation-result/2 accepts the provenance-bound structured imitation policy", () => {
  const imitation = v2Fixture(2);
  imitation.policy = { identity: "structured-behavior-cloning/1", informationScope: "online-observation-only",
    artifactIdentity: hash("9"), deploymentStatus: "experimental-unpromoted" };
  imitation.policyComparison.active.policyIdentity = imitation.policy.identity;
  imitation.policyComparison.active.informationScope = imitation.policy.informationScope;
  imitation.provenance.policyIdentity = imitation.policy.identity;
  imitation.provenance.policyArtifactIdentity = imitation.policy.artifactIdentity;
  imitation.provenance.policyDeploymentStatus = imitation.policy.deploymentStatus;
  const parsed = parseSimulationResult(imitation);
  assert.equal(parsed.schemaVersion, "simulation-result/2");
  assert.equal(parsed.policy.identity, "structured-behavior-cloning/1");
  assert.equal(parsed.policy.artifactIdentity, hash("9"));
  assert.equal(parsed.policy.deploymentStatus, "experimental-unpromoted");
});

test("simulation-result/2 accepts the exact fixed-rank policy identity", () => {
  const exact = v2Fixture(2);
  exact.policy = { identity: "optimal-fixed-rank-assignment/1", informationScope: "offline-full-episode" };
  exact.policyComparison.active.policyIdentity = exact.policy.identity;
  exact.provenance.policyIdentity = exact.policy.identity;
  const parsed = parseSimulationResult(exact);
  assert.equal(parsed.schemaVersion, "simulation-result/2");
  assert.equal(parsed.policy.identity, "optimal-fixed-rank-assignment/1");
});

test("simulation-result/2 rejects count, identity, exactness, provenance, and finite-number drift", () => {
  const count = v2Fixture(2); count.outcomes.pop();
  assert.throws(() => parseSimulationResult(count), /outcomes must cover/);
  const duplicate = v2Fixture(2); duplicate.trajectories[1].threatId = duplicate.trajectories[0].threatId;
  assert.throws(() => parseSimulationResult(duplicate), /distinct trajectories/);
  const outcome = v2Fixture(2); outcome.outcomes[0].outcome = "escaped";
  assert.throws(() => parseSimulationResult(outcome), /invalid simulation outcome/);
  const policy = v2Fixture(2); policy.policy.identity = "unknown-policy/9";
  assert.throws(() => parseSimulationResult(policy), /unsupported active policy/);
  const scope = v2Fixture(2); scope.policy.informationScope = "online-detected-only";
  assert.throws(() => parseSimulationResult(scope), /information label/);
  const exact = v2Fixture(2); exact.policyComparison.exactReference.exact = false;
  assert.throws(() => parseSimulationResult(exact), /false exactness/);
  const provenance = v2Fixture(2); provenance.provenance.canonicalEpisodeHash = "sha256:nope";
  assert.throws(() => parseSimulationResult(provenance), /SHA-256/);
  const split = v2Fixture(2); split.provenance.split = "training";
  assert.throws(() => parseSimulationResult(split), /split/);
  const profile = v2Fixture(2); profile.provenance.profile = "unknown";
  assert.throws(() => parseSimulationResult(profile), /profile/);
  const nonfinite = v2Fixture(2); nonfinite.policyComparison.active.ordinalCost = Number.NaN;
  assert.throws(() => parseSimulationResult(nonfinite), /finite/);
});
