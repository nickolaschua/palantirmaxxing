import { test } from "node:test";
import assert from "node:assert/strict";
import {
  BASES, chooseBase, groundDistanceM, INTERCEPTOR_SPEED_MPS, interceptorSamples, planLaunch,
} from "../../frontend/src/demo/interceptor-model.ts";
import type { InterceptorBase } from "../../frontend/src/demo/interceptor-model.ts";

const khatib = BASES.find(b => b.id === "khatib")!;
const start = new Date("2026-09-26T04:00:00Z");
// About 5 km east of Khatib, 13.7 km up, met 30 s in: reachable at 400 m/s with a launch around T+17.5 s.
const near = { position: { lon: 103.873, lat: 1.4226, height: 13_687 }, timeFromStartS: 30 };
// 20 km away, met 10 s in: would need a launch before detection.
const far = { position: { lon: 103.6485, lat: 1.4226, height: 10_000 }, timeFromStartS: 10 };

test("planLaunch works backwards from the intercept time at 400 m/s", () => {
  const plan = planLaunch(khatib, near, 0);
  assert.ok(plan.feasible);
  assert.equal(plan.flightS, plan.distanceM / INTERCEPTOR_SPEED_MPS);
  assert.ok(Math.abs(plan.launchS + plan.flightS - near.timeFromStartS) < 1e-9);
  assert.ok(plan.launchS > 17 && plan.launchS < 18, `launch ${plan.launchS}`);
});

test("an intercept that would need a launch before detection is out of range", () => {
  const plan = planLaunch(khatib, far, 0);
  assert.equal(plan.feasible, false);
  assert.ok(!plan.feasible && plan.requiredLaunchS < 0);
});

test("the arc leaves the pad at launch and meets the intercept point on time, never below ground", () => {
  const plan = planLaunch(khatib, near, 0);
  assert.ok(plan.feasible);
  const arc = interceptorSamples(khatib, near, plan, start);
  const [first, last] = [arc[0]!, arc.at(-1)!];
  assert.deepEqual([first.lon, first.lat, first.height], [khatib.position.lon, khatib.position.lat, 0]);
  assert.ok(Math.abs(first.time.getTime() - (start.getTime() + plan.launchS * 1000)) < 1);
  assert.deepEqual([last.lon, last.lat, last.height], [near.position.lon, near.position.lat, near.position.height]);
  assert.ok(Math.abs(last.time.getTime() - (start.getTime() + near.timeFromStartS * 1000)) < 1);
  assert.ok(arc.every((s, i) => i === 0 || s.time > arc[i - 1]!.time), "time strictly increases");
  assert.ok(arc.every(s => s.height >= 0));
  assert.ok(arc[1]!.height > 0, "it climbs straight away");
});

test("chooseBase: the nearest base with stock that can make it; null when none can", () => {
  const target = { position: { lon: 103.86, lat: 1.37, height: 1000 }, timeFromStartS: 60 };
  const nearBase: InterceptorBase = { id: "near", label: "Near", position: { lon: 103.87, lat: 1.37 }, stock: 8 };
  const mid: InterceptorBase = { id: "mid", label: "Mid", position: { lon: 103.83, lat: 1.42 }, stock: 8 };
  const farBase: InterceptorBase = { id: "far", label: "Far", position: { lon: 103.5, lat: 1.37 }, stock: 8 };
  const bases = [farBase, mid, nearBase];
  const full = new Map(bases.map(b => [b.id, 8]));
  assert.equal(chooseBase(bases, full, target, 0)?.base.id, "near");
  assert.equal(chooseBase(bases, new Map([...full, ["near", 0]]), target, 0)?.base.id, "mid", "an empty base is skipped");
  assert.ok(groundDistanceM(farBase.position, target.position) / INTERCEPTOR_SPEED_MPS > target.timeFromStartS);
  assert.equal(chooseBase([farBase], full, target, 0), null, "out of range everywhere");
  assert.equal(chooseBase(bases, new Map(), target, 0), null, "no stock anywhere");
});
