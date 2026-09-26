import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { engagementOption, parseResult } from "../../frontend/src/demo/decision-model.ts";
import {
  BASES, chooseBase, groundDistanceM, INTERCEPTOR_SPEED_MPS, interceptorSamples, planLaunch,
} from "../../frontend/src/demo/interceptor-model.ts";
import type { InterceptorBase } from "../../frontend/src/demo/interceptor-model.ts";

const raw = JSON.parse(readFileSync(new URL("../../data/results/demo-planning-result.json", import.meta.url), "utf8"));
const { result, options } = parseResult(raw);
const khatib = BASES.find(b => b.id === "khatib")!;
const lowest = engagementOption(result, options)!;
const earliest = options.find(o => o.id === result.categoryAssignments.earliestViable)!;
const start = new Date(result.start);

test("the demo's lowest-exposure intercept is reachable from Khatib: launch ≈ T+0.4 s, flight ≈ 16.4 s", () => {
  const plan = planLaunch(khatib, lowest, 0);
  assert.ok(plan.feasible);
  assert.ok(Math.abs(plan.flightS - 16.4) < 0.1, `flight ${plan.flightS}`);
  assert.ok(Math.abs(plan.launchS - 0.4) < 0.1, `launch ${plan.launchS}`);
  assert.equal(plan.flightS, plan.distanceM / INTERCEPTOR_SPEED_MPS);
  assert.ok(Math.abs(plan.launchS + plan.flightS - lowest.timeFromStartS) < 1e-9);
});

test("an intercept that would need a launch before detection is out of range", () => {
  const plan = planLaunch(khatib, earliest, 0);
  assert.equal(plan.feasible, false);
  assert.ok(!plan.feasible && plan.requiredLaunchS < 0);
});

test("the arc leaves the pad at launch and meets the intercept point on time, never below ground", () => {
  const plan = planLaunch(khatib, lowest, 0);
  assert.ok(plan.feasible);
  const arc = interceptorSamples(khatib, lowest, plan, start);
  const [first, last] = [arc[0]!, arc.at(-1)!];
  assert.deepEqual([first.lon, first.lat, first.height], [khatib.position.lon, khatib.position.lat, 0]);
  assert.ok(Math.abs(first.time.getTime() - (start.getTime() + plan.launchS * 1000)) < 1);
  assert.deepEqual([last.lon, last.lat, last.height], [lowest.position.lon, lowest.position.lat, lowest.position.height]);
  assert.ok(Math.abs(last.time.getTime() - (start.getTime() + lowest.timeFromStartS * 1000)) < 1);
  assert.ok(arc.every((s, i) => i === 0 || s.time > arc[i - 1]!.time), "time strictly increases");
  assert.ok(arc.every(s => s.height >= 0));
  assert.ok(arc[1]!.height > 0, "it climbs straight away");
});

test("the three real bases: Paya Lebar is nearest the demo intercept, Khatib covers when it is empty, Tengah is out of range", () => {
  const full = new Map(BASES.map(b => [b.id, b.stock]));
  const first = chooseBase(BASES, full, lowest, 0)!;
  assert.equal(first.base.id, "paya-lebar");
  assert.ok(Math.abs(first.plan.launchS - 2.3) < 0.1, `launch ${first.plan.launchS}`);
  assert.equal(chooseBase(BASES, new Map([...full, ["paya-lebar", 0]]), lowest, 0)?.base.id, "khatib");
  assert.equal(planLaunch(BASES.find(b => b.id === "tengah")!, lowest, 0).feasible, false);
  assert.equal(chooseBase(BASES, new Map([...full, ["paya-lebar", 0], ["khatib", 0]]), lowest, 0), null);
});

test("chooseBase: the nearest base with stock that can make it; null when none can", () => {
  const target = { position: { lon: 103.86, lat: 1.37, height: 1000 }, timeFromStartS: 60 };
  const near: InterceptorBase = { id: "near", label: "Near", position: { lon: 103.87, lat: 1.37 }, stock: 8 };
  const mid: InterceptorBase = { id: "mid", label: "Mid", position: { lon: 103.83, lat: 1.42 }, stock: 8 };
  const far: InterceptorBase = { id: "far", label: "Far", position: { lon: 103.5, lat: 1.37 }, stock: 8 };
  const bases = [far, mid, near];
  const full = new Map(bases.map(b => [b.id, 8]));
  assert.equal(chooseBase(bases, full, target, 0)?.base.id, "near");
  assert.equal(chooseBase(bases, new Map([...full, ["near", 0]]), target, 0)?.base.id, "mid", "an empty base is skipped");
  // `far` is ~40 km out: 100 s of flight cannot make a 60 s intercept.
  assert.ok(groundDistanceM(far.position, target.position) / INTERCEPTOR_SPEED_MPS > target.timeFromStartS);
  assert.equal(chooseBase([far], full, target, 0), null, "out of range everywhere");
  assert.equal(chooseBase(bases, new Map(), target, 0), null, "no stock anywhere");
});
