import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { unwrapDelivery, parseDeliveryFailure } from "../src/demo/delivery.ts";
import { parseResult } from "../src/demo/decision-model.ts";
import { parseSimulationResult } from "../src/demo/simulation-model.ts";

const artifact = (kind: string) => JSON.parse(readFileSync(new URL('../../data/results/demo-' + kind + '-result.json', import.meta.url), "utf8"));
const envelope = (result: unknown) => ({ resultId: "published-snapshot-1", publishedAt: "2026-09-26T00:00:00.123456Z", result });
for (const kind of ["planning", "simulation"] as const) {
  test(kind + ": actual artifact unwraps unchanged to existing parser input", () => {
    const input = envelope(artifact(kind));
    const before = JSON.stringify(input);
    const result = unwrapDelivery(kind, input);
    assert.equal(result, input.result);
    (kind === "planning" ? parseResult : parseSimulationResult)(result);
    assert.equal(JSON.stringify(input), before);
  });
  test(kind + ": rejects wrong kind, identity, publication time and schema", () => {
    assert.throws(() => unwrapDelivery(kind, envelope(artifact(kind === "planning" ? "simulation" : "planning"))));
    for (const resultId of [undefined, null, "", " ", 42]) assert.throws(() => unwrapDelivery(kind, { ...envelope(artifact(kind)), resultId }));
    for (const publishedAt of [undefined, "", "yesterday", "2026-02-30T00:00:00Z", "2026-09-26T24:00:00Z", "2026-09-26", "2026-09-26T00:00:00+08:00"]) {
      assert.throws(() => unwrapDelivery(kind, { ...envelope(artifact(kind)), publishedAt }));
    }
    assert.throws(() => unwrapDelivery(kind, envelope({ ...artifact(kind), schemaVersion: kind + "-result/2" })));
    for (const result of [null, [], {}]) assert.throws(() => unwrapDelivery(kind, envelope(result)));
  });
}
for (const [status, code, message] of [[404, "RESULT_NOT_FOUND", "No matching published result."], [503, "DELIVERY_UNAVAILABLE", "Result delivery is temporarily unavailable."], [500, "INTERNAL_ERROR", "Unexpected server failure."]] as const) {
  test(status + " error envelope", () => {
    assert.deepEqual(parseDeliveryFailure(status, { error: { code, message } }), { code, message });
    for (const value of [null, {}, { error: { code } }, { error: { code: "", message } }]) assert.throws(() => parseDeliveryFailure(status, value));
  });
}
test("unknown failure status is rejected", () => assert.throws(() => parseDeliveryFailure(401, { error: { code: "X", message: "X" } })));
