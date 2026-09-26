import assert from "node:assert/strict";
import test from "node:test";
import { filterScenarioEntries, parseScenarioManifest } from "../../frontend/src/demo/scenario-manifest-model.ts";

const hash = (digit: string) => `sha256:${digit.repeat(64)}`;
const document = {
  schemaVersion: "rl-scenario-suites/5",
  generatorVersion: "singapore-scenario/2",
  distributionVersion: "singapore-scenario-distribution/1",
  distributionChecksum: hash("0"),
  providerIdentity: "singapore-demo-v2",
  entries: [
    { scenarioRef: "sg2:validation:000000", split: "validation", index: 0, seed: 10000,
      profile: "balanced", canonicalEpisodeHash: hash("1") },
    { scenarioRef: "sg2:validation:000001", split: "validation", index: 1, seed: 10001,
      profile: "full-standard", canonicalEpisodeHash: hash("2") },
    { scenarioRef: "sg2:stress:000000", split: "stress", index: 0, seed: 30000,
      profile: "low-slack", canonicalEpisodeHash: hash("3") },
  ],
};

test("scenario filters return exact checked references", () => {
  const parsed = parseScenarioManifest(document);
  assert.deepEqual(filterScenarioEntries(parsed.entries, { split: "validation" }).map(row => row.scenarioRef),
    ["sg2:validation:000000", "sg2:validation:000001"]);
  assert.deepEqual(filterScenarioEntries(parsed.entries, { profile: "low-slack" }).map(row => row.scenarioRef),
    ["sg2:stress:000000"]);
  assert.deepEqual(filterScenarioEntries(parsed.entries, { query: "000001" }).map(row => row.scenarioRef),
    ["sg2:validation:000001"]);
});

test("manifest parser rejects malformed identities and duplicate hashes", () => {
  const malformed = structuredClone(document) as any;
  malformed.entries[0].scenarioRef = "../suites.json";
  assert.throws(() => parseScenarioManifest(malformed), /invalid scenario metadata/);
  const duplicate = structuredClone(document) as any;
  duplicate.entries[1].canonicalEpisodeHash = duplicate.entries[0].canonicalEpisodeHash;
  assert.throws(() => parseScenarioManifest(duplicate), /duplicate/);
});
