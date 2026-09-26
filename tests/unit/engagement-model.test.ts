import assert from "node:assert/strict";
import test from "node:test";
import {
  changeText, clockEndS, flattenSnapshot, lockTimeOf, naiveCostMismatch, outcomesOf, pairFailure, pairPhase, pairProblem,
  positionAt, summaryRows, threatDetail, threatStateAt,
} from "../../frontend/src/demo/engagement-model.ts";
import type { RunPair } from "../../frontend/src/demo/engagement-model.ts";
import type { SimulationResult, SimulationResultV2, SimulationTrajectory } from "../../frontend/src/demo/simulation-model.ts";

const sample = (t: number, lon: number, lat: number, h: number) => ({
  sampleIndex: 0, timeFromDetectionS: t, timeFromEpisodeStartS: t, time: new Date(Date.UTC(2026, 8, 26, 4, 0, t)).toISOString(),
  position: { lon, lat, heightM: h }, verticalVelocityMps: -1,
});
const trajectory = (id: string, detect: number): SimulationTrajectory => ({
  threatId: id, detectionTimeS: detect, detectionTime: "", samples: [sample(detect, 103.8, 1.3, 1000), sample(detect + 10, 103.9, 1.4, 0)],
});
const outcome = (threatId: string, kind: "intercepted" | "unhandled", at: number | null) => ({
  threatId, outcome: kind, resolvedTimeS: at, resolvedTime: null, interceptorId: kind === "intercepted" ? "int-1" : null,
  opportunityId: kind === "intercepted" ? `${threatId}__int-1__k1` : null, trainingCost: 0.25,
});
function v2(policy: string, active: number, naive: number, physical: Record<string, number>, scenarioRef = "sg2:validation:000000"): SimulationResultV2 {
  return {
    schemaVersion: "simulation-result/2", start: "2026-09-26T04:00:00Z", end: "2026-09-26T04:01:40Z",
    trajectories: [trajectory("threat-01", 1), trajectory("threat-02", 5)],
    outcomes: [outcome("threat-01", "intercepted", 8), outcome("threat-02", "unhandled", null)],
    assignments: [{ threat_id: "threat-01", lock_time_s: 4 }],
    selectedFootprints: [{ id: "fp-1", threatId: "threat-01", kind: "selected", label: "supplied 100 m area", center: { lon: 103.85, lat: 1.35, heightM: 0 }, radiusM: 100, consequence: { people: 12, nested: { ok: true, none: null } } }],
    terminalCounterfactualFootprints: [],
    consequenceSummary: { ordinalObjectiveCost: active, physicalComponents: physical, wording: { area: "supplied 100 m area", population: "people potentially exposed", casualties: "assumption-grade expected casualties" } },
    policy: { identity: policy as SimulationResultV2["policy"]["identity"], informationScope: "online-detected-only" },
    policyComparison: {
      active: { policyIdentity: policy as never, informationScope: "online-detected-only", ordinalCost: active, completed: true, terminationReason: "done" },
      naive: { policyIdentity: "naive-launch-on-detection/1", informationScope: "online-detected-only", ordinalCost: naive, completed: true, terminationReason: "done" },
      exactReference: { policyIdentity: "optimal-fixed-rank-assignment/1", informationScope: "offline-full-episode", ordinalCost: 1, completed: true, terminationReason: "done", predictedOrdinalCost: 1, exact: true, proofScope: "scope", predictedCostMatchesReplay: true },
      activeMinusNaiveCost: active - naive, exactRegret: active - 1,
    },
    termination: { reason: "done", completed: true, constraintStatus: "satisfied", constraintViolation: null, terminationTimeS: 100 },
    provenance: { scenarioRef } as SimulationResultV2["provenance"],
    limitations: ["synthetic"],
  } as SimulationResultV2;
}
const naiveRun = v2("naive-launch-on-detection/1", 2.5, 2.5, { people_potentially_exposed_total: 100, expected_casualties_central_total: 0 });
const exactRun = v2("optimal-fixed-rank-assignment/1", 1.0, 2.5, { people_potentially_exposed_total: 40 });

test("threat state follows detection, lock, and outcome", () => {
  const t = trajectory("threat-01", 1);
  const hit = outcome("threat-01", "intercepted", 8);
  assert.equal(threatStateAt(t, hit, 4, 0.5), "unseen");
  assert.equal(threatStateAt(t, hit, 4, 1), "detected");
  assert.equal(threatStateAt(t, hit, 4, 4), "locked");
  assert.equal(threatStateAt(t, hit, null, 4), "detected");
  assert.equal(threatStateAt(t, hit, 4, 8), "intercepted");
  assert.equal(threatStateAt(t, outcome("threat-01", "unhandled", null), null, 11), "unhandled");
  assert.equal(threatStateAt(t, undefined, null, 11), "unhandled");
});

test("outcomes and lock times come from assignments on schema 1", () => {
  const v1 = {
    schemaVersion: "simulation-result/1", start: "2026-09-26T04:00:00Z", end: "2026-09-26T04:01:00Z",
    trajectories: [trajectory("threat-01", 1)],
    assignments: [{ threat_id: "threat-01", interception_time_s: 7, interceptor_id: "int-9", opportunity_id: "op", lockTime: "2026-09-26T04:00:03Z", consequence_snapshot: { training_cost: 0.5 } }],
    selectedFootprints: [], terminalCounterfactualFootprints: [],
    consequenceSummary: { ordinalObjectiveCost: 1, physicalComponents: {}, wording: { area: "supplied 100 m area", population: "people potentially exposed", casualties: "assumption-grade expected casualties" } },
    policyVersusBaseline: { policyIdentity: "p", policyOrdinalCost: 1, baselineIdentity: "b", baselineOrdinalCost: 2, measuredRelativeImprovement: 0.5, claim: "c" },
    provenance: {}, limitations: [],
  } as unknown as SimulationResult;
  assert.deepEqual(outcomesOf(v1)[0], { threatId: "threat-01", outcome: "intercepted", resolvedTimeS: 7, resolvedTime: null, interceptorId: "int-9", opportunityId: "op", trainingCost: 0.5 });
  assert.equal(lockTimeOf(v1, "threat-01"), 3);
  assert.equal(lockTimeOf(naiveRun, "threat-01"), 4);
  assert.equal(lockTimeOf(naiveRun, "threat-02"), null);
  assert.equal(clockEndS(v1), 60);
});

test("clock end covers the episode, the last sample, and the last resolution", () => {
  assert.equal(clockEndS(naiveRun), 100);
  const short = { ...naiveRun, end: "2026-09-26T04:00:05Z" };
  assert.equal(clockEndS(short), 15);
});

test("positionAt interpolates and clamps", () => {
  const t = trajectory("threat-01", 0);
  assert.deepEqual(positionAt(t, -1), { lon: 103.8, lat: 1.3, height: 1000 });
  assert.deepEqual(positionAt(t, 99), { lon: 103.9, lat: 1.4, height: 0 });
  const mid = positionAt(t, 5);
  assert.ok(Math.abs(mid.lon - 103.85) < 1e-9 && Math.abs(mid.height - 500) < 1e-9);
});

test("changeText marks direction and trade-offs", () => {
  assert.deepEqual(changeText(100, 40, false), { text: "▼ 60%", worse: false });
  assert.deepEqual(changeText(40, 100, false), { text: "▲ 150%", worse: true });
  assert.deepEqual(changeText(1, 2, true), { text: "▲ 100%", worse: false });
  assert.deepEqual(changeText(3, 3, true), { text: "no change", worse: false });
  assert.deepEqual(changeText(0, 0.5, false), { text: "▲ 0.5", worse: true });
});

test("summary rows show backend totals, unavailable figures, and counts", () => {
  const rows = summaryRows(naiveRun, exactRun);
  assert.deepEqual(rows.map(r => r.id), ["people", "casualties", "cost", "intercepted"]);
  assert.equal(rows[0]!.baseline, "100"); assert.equal(rows[0]!.optimised, "40"); assert.equal(rows[0]!.change, "▼ 60%");
  assert.equal(rows[1]!.baseline, "0"); assert.equal(rows[1]!.optimised, "unavailable"); assert.equal(rows[1]!.change, ""); assert.equal(rows[1]!.unavailable, true);
  assert.equal(rows[2]!.baseline, "2.5"); assert.equal(rows[2]!.optimised, "1"); assert.equal(rows[2]!.change, "▼ 60%");
  assert.equal(rows[3]!.baseline, "1 of 2"); assert.equal(rows[3]!.change, "no change");
});

test("pair checks: schema, scenario, baseline policy, naive cost", () => {
  assert.equal(pairProblem(naiveRun, exactRun), null);
  assert.equal(pairProblem(exactRun, naiveRun), "Baseline run is optimal-fixed-rank-assignment/1, not naive-launch-on-detection/1");
  assert.equal(pairProblem(naiveRun, { ...exactRun, provenance: { scenarioRef: "sg2:stress:000001" } as never }), "Runs are on different scenarios");
  assert.equal(pairProblem({ ...naiveRun, schemaVersion: "simulation-result/1" } as never, exactRun), "Comparison needs simulation-result/2 on both sides");
  assert.equal(naiveCostMismatch(naiveRun, exactRun), false);
  assert.equal(naiveCostMismatch({ ...naiveRun, policyComparison: { ...naiveRun.policyComparison, active: { ...naiveRun.policyComparison.active, ordinalCost: 9 } } }, exactRun), true);
});

test("threat detail and snapshot flattening", () => {
  const d = threatDetail(naiveRun, "threat-01");
  assert.equal(d.outcome, "intercepted"); assert.equal(d.interceptorId, "int-1"); assert.equal(d.resolvedTimeS, 8); assert.equal(d.footprint?.id, "fp-1");
  assert.equal(threatDetail(naiveRun, "threat-02").footprint, undefined);
  assert.equal(threatDetail(naiveRun, "nope").outcome, "unknown");
  assert.deepEqual(flattenSnapshot(d.footprint!.consequence), [
    { key: "people", value: "12" }, { key: "nested · ok", value: "yes" }, { key: "nested · none", value: "unavailable" },
  ]);
  assert.deepEqual(flattenSnapshot(null), [{ key: "value", value: "unavailable" }]);
  assert.deepEqual(flattenSnapshot([1, "a"]), [{ key: "value", value: "1, a" }]);
});

test("pair phase and failure text", () => {
  const pair: RunPair = { id: 1, scenarioRef: "sg2:validation:000000",
    baseline: { policy: "naive-launch-on-detection/1", status: "queued", runId: "a" },
    optimised: { policy: "optimal-fixed-rank-assignment/1", status: "running", runId: "b" } };
  assert.equal(pairPhase(pair), "pending"); assert.equal(pairFailure(pair), null);
  pair.baseline.status = "succeeded"; pair.optimised.status = "succeeded";
  assert.equal(pairPhase(pair), "ready");
  pair.optimised = { ...pair.optimised, status: "failed", error: { code: "SCENARIO_IDENTITY_MISMATCH", message: "drift" } };
  assert.equal(pairPhase(pair), "failed");
  assert.equal(pairFailure(pair), "Optimised run failed · SCENARIO_IDENTITY_MISMATCH: drift");
  assert.equal(pairFailure({ ...pair, optimised: { ...pair.optimised, status: "succeeded" }, problem: "Runs are on different scenarios" }), "Runs are on different scenarios");
});
