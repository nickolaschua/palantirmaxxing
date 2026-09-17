import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  advance, approachOrigin, comparisonLines, descentSamples, DESCENT_S, detect, elapsedS, exposureGrade, fire, framePose,
  isOpen, optionColour, parseResult, remainingS, select, STANDBY, successGrade, threatPositionAt, urgency,
} from "../../frontend/src/demo/decision-model.ts";

const raw = JSON.parse(readFileSync(new URL("../../data/results/demo-planning-result.json", import.meta.url), "utf8"));
const { result, options } = parseResult(raw);
const byMargin = [...options].sort((a, b) => (a.timeMarginS ?? 0) - (b.timeMarginS ?? 0));
const first = byMargin[0]!, last = byMargin.at(-1)!;

test("validation rejects a wrong schema, an unresolved representative and non-finite numbers", () => {
  assert.throws(() => parseResult({ ...raw, schemaVersion: "planning-result/2" }), /Unsupported schema/);
  assert.throws(() => parseResult({ ...raw, representativeCandidateIds: ["nope"] }), /not a candidate/);
  const broken = structuredClone(raw);
  broken.candidates.find((c: { id: string }) => c.id === last.id).timeFromStartS = null;
  assert.throws(() => parseResult(broken), /non-finite/);
  assert.equal(parseResult({ ...raw, representativeCandidateIds: [], comparisons: [] }).options.length, 0);
});

test("countdown and expiry follow timeMarginS − elapsed", () => {
  const start = Date.parse(result.start);
  assert.equal(elapsedS(result, new Date(start + 2500)), 2.5);
  assert.equal(remainingS(last, 1), last.timeMarginS! - 1);
  assert.equal(isOpen(last, last.timeMarginS! - 0.01), true);
  assert.equal(isOpen(last, last.timeMarginS!), false);
  assert.equal(remainingS({ timeMarginS: null }, 1), null);
});

test("flow: detect, select, fire, outcome; closed windows clear selection; all closed expires", () => {
  let flow = detect(STANDBY);
  assert.equal(flow.phase, "live");
  flow = select(flow, options, first.id, 0);
  assert.equal(flow.selected, first.id);
  flow = advance(flow, options, first.timeMarginS! + 0.01);
  assert.equal(flow.selected, null, "selection clears when its window closes");
  assert.equal(fire(flow, options, 1).phase, "live", "nothing selected, nothing fires");
  assert.equal(select(flow, options, first.id, first.timeMarginS! + 1).selected, null, "a closed option cannot be selected");
  assert.equal(advance(flow, options, last.timeMarginS!).phase, "expired");
  const fired = fire(select(flow, options, last.id, 1), options, 1);
  assert.deepEqual([fired.phase, fired.fired], ["fired", last.id]);
  assert.equal(advance(fired, options, last.timeFromStartS - 0.1).phase, "fired");
  assert.equal(advance(fired, options, last.timeFromStartS).phase, "impact", "the fall into the area comes first");
  assert.equal(advance(fired, options, last.timeFromStartS + DESCENT_S).phase, "outcome");
  assert.equal(advance(fired, options, last.timeMarginS! + 1).phase, "fired", "firing is not undone by windows closing");
});

test("deadline positions: before the first sample pins to the start; otherwise interpolated", () => {
  const s = result.threat.samples;
  const pinned = threatPositionAt(result, 0.1);
  assert.equal(pinned.beforePath, true);
  assert.equal(pinned.position.lon, s[0]!.lon);
  const at = (Date.parse(s[1]!.time) + Date.parse(s[2]!.time)) / 2 - Date.parse(result.start);
  const mid = threatPositionAt(result, at / 1000);
  assert.ok(Math.abs(mid.position.lon - (s[1]!.lon + s[2]!.lon) / 2) < 1e-9);
  assert.equal(threatPositionAt(result, 999).position.lon, s.at(-1)!.lon);
});

test("the fall stays over the area's centre and lands at the end of the descent", () => {
  const fall = descentSamples(last, new Date(result.start));
  assert.equal(fall.length, 7);
  assert.ok(fall.every(s => s.lon === last.position.lon && s.lat === last.position.lat), "it falls straight onto the centre");
  assert.equal(fall[0]!.height, last.position.height);
  assert.equal(fall.at(-1)!.height, 0);
  assert.ok(fall[1]!.height > fall[3]!.height, "an accelerating fall loses height faster later");
  const seconds = (fall.at(-1)!.time.getTime() - fall[0]!.time.getTime()) / 1000;
  assert.equal(seconds, DESCENT_S);
});

test("illustrative approach origin sits outside the bounds, back along the supplied heading", () => {
  const bounds = { west: 103.56, south: 1.13, east: 104.14, north: 1.52 };
  const origin = approachOrigin(result, bounds)!;
  const first = result.threat.samples[0]!;
  assert.ok(origin.lon < bounds.west, `origin lon ${origin.lon} should be west of the box`);
  assert.ok(Math.abs(origin.lat - first.lat) < 0.01, "an eastbound threat keeps its latitude");
  assert.ok(origin.timeFromStartS < 0, "the origin is before detection");
  assert.equal(origin.height, first.height);
  // 6 km of margin beyond the edge, at the supplied 225 m/s.
  const km = (first.lon - origin.lon) * 111_320 * Math.cos((first.lat * Math.PI) / 180) / 1000;
  assert.ok(km > 30 && km < 40, `expected roughly 30-40 km back, got ${km.toFixed(1)}`);
  assert.equal(approachOrigin({ ...result, threat: { ...result.threat, samples: [first, first] } }, bounds), null);
});

test("colours by category priority, comparison wording, framing", () => {
  assert.equal(optionColour({ categories: ["earliest_viable", "highest_success"] }), "#3d8bff");
  assert.equal(optionColour({ categories: ["lowest_exposure"] }), "#ff4d4d");
  assert.equal(optionColour({ categories: ["something_new"] }), "#b58cff");
  const lines = comparisonLines({
    ...result,
    representativeCandidateIds: ["a", "b"],
    comparisons: [{ referenceCandidateId: "a", comparisonCandidateId: "b", deltaTimeS: 14, deltaSuccessProbability: -0.056,
      deltaSuccessPercentagePoints: -5.6, deltaPeoplePotentiallyExposed: -13608.7, relativeExposureChange: -0.8923 }],
  }, "b");
  assert.equal(lines[0]!.text, "−13,609 people potentially exposed (−89.2%) · −5.6 pp supplied success (synthetic) · +14.0 s intercept time");
  const pose = framePose([{ lon: 103.8, lat: 1.37 }, { lon: 103.9, lat: 1.38 }], 70, 16 / 9);
  assert.ok(pose.lat < 1.375 && pose.height! > 0 && pose.pitch === -70);
});

test("grades: success against fixed marks, exposure only relative to the result, urgency 0 to 1 across the window", () => {
  assert.equal(successGrade(0.896), "good");
  assert.equal(successGrade(0.8), "good");
  assert.equal(successGrade(0.6), "fair");
  assert.equal(successGrade(0.49), "poor");
  assert.equal(exposureGrade(1643, [1643, 15252]), "good");
  assert.equal(exposureGrade(15252, [1643, 15252]), "poor");
  assert.equal(exposureGrade(8000, [1643, 15252]), "fair");
  assert.equal(exposureGrade(1643, [1643]), null);
  const o = { timeMarginS: 10 };
  assert.equal(urgency(o, 0), 0);
  assert.equal(urgency(o, 5), 0.5);
  assert.equal(urgency(o, 12), 1);
  assert.equal(urgency({ timeMarginS: null }, 3), 0);
});
