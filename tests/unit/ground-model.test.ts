import { test } from "node:test";
import assert from "node:assert/strict";
import { packLines, query } from "../../frontend/src/lib/ground-model.ts";

const hits = (lines: ReturnType<typeof packLines>, w: number, s: number, e: number, n: number): number[] => {
  const out: number[] = [];
  query(lines, w, s, e, n, (i) => out.push(i));
  return out.sort((a, b) => a - b);
};

test("delta and degree inputs decode to the same integers; short lines are dropped", () => {
  const delta = packLines([[10380000, 130000, 10, -20, 5, 5], [1, 2]], true);
  const deg = packLines([[103.8, 1.3, 103.8001, 1.2998, 103.80015, 1.29985]], false);
  assert.deepEqual([...delta.xy], [10380000, 130000, 10380010, 129980, 10380015, 129985]);
  assert.deepEqual([...deg.xy], [...delta.xy]);
  assert.deepEqual([...delta.start], [0, 3]);
  assert.deepEqual([...delta.box], [10380000, 129980, 10380015, 130000]);
});

test("a query visits each line whose box meets it, once, even across many cells", () => {
  const lines = packLines([
    [0, 0, 5000, 0],          // long: spans six cells
    [2500, 2500, 10, 10],     // small, in one cell
    [9000, 9000, 1, 1],       // far corner
  ], true);
  assert.deepEqual(hits(lines, -10, -10, 6000, 10), [0]);
  assert.deepEqual(hits(lines, 2000, -10, 3000, 3000), [0, 1]);
  assert.deepEqual(hits(lines, 2511, 2511, 2600, 2600), []); // same cell as line 1, outside its box
  assert.deepEqual(hits(lines, -1e6, -1e6, 1e6, 1e6), [0, 1, 2]);
  assert.deepEqual(hits(lines, 20000, 20000, 30000, 30000), []); // off the grid
  assert.deepEqual(hits(lines, 8990, 8990, 9000, 9000), [2]);
});
