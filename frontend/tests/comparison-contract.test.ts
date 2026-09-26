import { test } from "node:test";
import assert from "node:assert/strict";
import { parseComparisonResult } from "../src/demo/comparison-contract.ts";
import { DEMO_COMPARISON_RESULT } from "../src/demo/comparison-data.ts";

const fixture = (): any => JSON.parse(JSON.stringify(DEMO_COMPARISON_RESULT));

test("structured comparison fixture satisfies the v2 contract", () => {
  const parsed = parseComparisonResult(fixture());
  assert.equal(parsed.schemaVersion, "multi-threat-comparison/2");
  assert.equal(parsed.threats[0]?.robustness.sampleCount, 50000);
});

test("comparison explanations must reference real metrics and provenance", () => {
  const unknownMetric = fixture();
  unknownMetric.threats[0].explanations[0].references[0].id = "missing";
  assert.throws(() => parseComparisonResult(unknownMetric), /unknown metric/);

  const unknownSource = fixture();
  unknownSource.threats[0].explanations[0].sourceIds = ["missing-source"];
  assert.throws(() => parseComparisonResult(unknownSource), /provenance\.sourceIds/);
});

test("robustness is derived from valid paired sample counts", () => {
  const invalid = fixture();
  invalid.threats[0].robustness.lowerConsequenceSamples = 50001;
  assert.throws(() => parseComparisonResult(invalid), /robustness is invalid/);
});

test("every outcome metric needs a plain-language description", () => {
  const invalid = fixture();
  invalid.threats[0].baseline.metrics[0].description = "";
  assert.throws(() => parseComparisonResult(invalid), /metrics\[0\] is invalid/);
});
