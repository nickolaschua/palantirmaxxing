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
