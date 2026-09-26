import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  advance, approachOrigin, comparisonLines, consequenceRows, descentSamples, DESCENT_S, detect, elapsedS, engagementOption, exposureGrade, framePose,
  isOpen, optionColour, parseResult, remainingS, STANDBY, successGrade, threatPositionAt, urgency,
} from "../../frontend/src/demo/decision-model.ts";

const raw = JSON.parse(readFileSync(new URL("../../data/results/demo-planning-result.json", import.meta.url), "utf8"));
const { result, options } = parseResult(raw);
const byMargin = [...options].sort((a, b) => (a.timeMarginS ?? 0) - (b.timeMarginS ?? 0));
const last = byMargin.at(-1)!;

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

test("flow: detection fixes the engagement, it launches itself on time, then impact and outcome", () => {
  const engaged = engagementOption(result, options)!;
  assert.equal(engaged.id, result.categoryAssignments.lowestExposure);
  const flow = detect(STANDBY, engaged.id);
  assert.deepEqual([flow.phase, flow.selected, flow.fired], ["live", engaged.id, null]);
  const launchS = engaged.timeMarginS! + 1; // later than the backend window, to show it still waits
  assert.equal(advance(flow, options, launchS - 0.01, launchS).phase, "live", "waits for its launch time");
  assert.equal(advance(flow, options, last.timeMarginS! + 0.5, last.timeMarginS! + 1).phase, "live", "a pending launch never expires");
  const fired = advance(flow, options, launchS, launchS);
  assert.deepEqual([fired.phase, fired.fired], ["fired", engaged.id]);
  assert.equal(advance(fired, options, engaged.timeFromStartS - 0.1).phase, "fired");
  assert.equal(advance(fired, options, engaged.timeFromStartS).phase, "impact", "the fall into the area comes first");
  assert.equal(advance(fired, options, engaged.timeFromStartS + DESCENT_S).phase, "outcome");
});

test("flow: with no engagement nothing launches and closed windows expire", () => {
  const idle = detect(STANDBY);
  assert.deepEqual([idle.phase, idle.selected], ["live", null]);
  assert.equal(advance(idle, options, 0).phase, "live");
  assert.equal(advance(idle, options, last.timeMarginS!).phase, "expired");
  assert.equal(advance(idle, options, 999, null).fired, null);
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

test("consequence: optional, validated, and rendered with unavailable kept apart from zero", () => {
  const withConsequence = (consequence: unknown) => {
    const r = structuredClone(raw);
    r.candidates.find((c: { id: string }) => c.id === last.id).consequence = consequence;
    return r;
  };
  const good = { total: null, scenario: "Weekday evening", dimensions: [
    { id: "H", weight: 0.35, value: { low: 30, central: 42, high: 55, confidence: "C", source: "SingStat" } },
    { id: "D", weight: 0.2, value: null },
    { id: "R", weight: 0.05, value: { low: 0, central: 0, high: 0 } },
  ] };
  assert.equal(parseResult(raw).options.every(o => o.consequence === undefined), true, "absent is fine");
  const parsedOption = parseResult(withConsequence(good)).options.find(o => o.id === last.id)!;
  const rows = consequenceRows(parsedOption.consequence!);
  assert.deepEqual(rows.map(r => r.value), ["Unavailable", "42 (30–55)", "Unavailable", "0"]);
  assert.deepEqual(rows.map(r => r.weight), ["", "35%", "20%", "5%"]);
  assert.deepEqual(rows[1]!.bar, { low: 0.3, central: 0.42, high: 0.55 });
  assert.equal(rows[2]!.bar, null, "unavailable draws no bar");
  assert.deepEqual(rows[3]!.bar, { low: 0, central: 0, high: 0 }, "zero is a value");
  assert.equal(rows[1]!.detail, "Confidence C · Source: SingStat");
  assert.equal(consequenceRows({ total: { low: null, central: 150, high: null }, dimensions: [] })[0]!.bar?.central, 1, "bar clamps to the scale");

  assert.throws(() => parseResult(withConsequence({ ...good, dimensions: [{ id: "Q", weight: 1, value: null }] })), /unknown dimension/);
  assert.throws(() => parseResult(withConsequence({ ...good, dimensions: [{ id: "H", weight: 1 }] })), /use null for unavailable/);
  assert.throws(() => parseResult(withConsequence({ ...good, total: { low: 50, central: 40, high: 60 } })), /low ≤ central ≤ high/);
  assert.throws(() => parseResult(withConsequence({ ...good, dimensions: undefined })), /no dimensions list/);
});

test("framing into the uncovered area: panels push the view away and back the camera off", () => {
  const points = [{ lon: 103.8, lat: 1.37 }, { lon: 103.9, lat: 1.38 }];
  const open = framePose(points, 70, 16 / 10);
  const covered = framePose(points, 70, 16 / 10, 1.2, { left: 0.15, right: 0.28, top: 0, bottom: 0.4 });
  assert.ok(covered.height! > open.height!, "less free screen, so the camera stands further back");
  assert.ok(covered.lon > open.lon, "a wider right panel moves the view east so the points sit left of it");
  assert.ok(covered.lat < open.lat, "the bottom tray moves the view south so the points sit above it");
});
