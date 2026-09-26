import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { unwrapDelivery } from '../src/demo/delivery.ts';
import { parseResult } from '../src/demo/decision-model.ts';
import { parseSimulationResult } from '../src/demo/simulation-model.ts';
const corpus = JSON.parse(readFileSync(process.argv[2], 'utf8'));
for (const { kind, payload, name } of corpus.accepted) {
  const original = structuredClone(payload);
  const envelope = { resultId: `fresh-${name}`, publishedAt: '2026-09-26T00:00:00.000001Z', result: payload };
  const unwrapped = unwrapDelivery(kind, envelope);
  assert.strictEqual(unwrapped, payload);
  (kind === 'planning' ? parseResult : parseSimulationResult)(unwrapped);
  assert.deepEqual(payload, original, `${name}: parser/adapter changed evidence`);
  for (const number of [NaN, Infinity, -Infinity]) {
    const invalid = structuredClone(payload);
    invalid.unexpectedNumber = number;
    assert.throws(() => unwrapDelivery(kind, { ...envelope, result: invalid }), `${name}: nonfinite accepted`);
  }
}
for (const { kind, payload, name } of corpus.rejected) {
  assert.throws(() => unwrapDelivery(kind, {
    resultId: 'invalid', publishedAt: '2026-09-26T00:00:00Z', result: payload,
  }), `${kind}/${name}: invalid payload accepted`);
}
console.log(JSON.stringify({ accepted: corpus.accepted.length, rejected: corpus.rejected.length, adapterUnchanged: true }));
