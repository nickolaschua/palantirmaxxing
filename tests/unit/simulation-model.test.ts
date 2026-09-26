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
