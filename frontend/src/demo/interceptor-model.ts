/**
 * Friendly interceptor bases: which base takes a shot, when it has to launch,
 * and the arc it flies. The intercept point and time come from the backend;
 * everything here is worked backwards from them. No DOM, no Cesium.
 *
 * Demonstration only: fixed horizontal speed, flat ground, no drag.
 */

export interface InterceptorBase { id: string; label: string; position: { lon: number; lat: number }; stock: number }
/** Where and when the backend wants the threat met. `height` is metres. */
export interface InterceptTarget { position: { lon: number; lat: number; height: number }; timeFromStartS: number }
export type LaunchPlan =
  | { feasible: true; launchS: number; flightS: number; distanceM: number }
  | { feasible: false; requiredLaunchS: number; distanceM: number };

/** Centroids of the OSM outlines in military.json. */
export const BASES: readonly InterceptorBase[] = [
  { id: "khatib", label: "Khatib Camp", position: { lon: 103.8281, lat: 1.4226 }, stock: 8 },
  { id: "tengah", label: "Tengah Air Base", position: { lon: 103.7138, lat: 1.3913 }, stock: 8 },
  { id: "paya-lebar", label: "Paya Lebar Air Base", position: { lon: 103.9105, lat: 1.3572 }, stock: 8 },
];

/** Horizontal; slow enough for an audience to follow. */
export const INTERCEPTOR_SPEED_MPS = 400;
/** Same value as the backend threat generator. */
export const GRAVITY_MPS2 = 9.80665;

/** Flat-ground metres, with the same factors as the rest of the demo. */
export function groundDistanceM(a: { lon: number; lat: number }, b: { lon: number; lat: number }): number {
  const mPerDegLon = 111_320 * Math.cos((((a.lat + b.lat) / 2) * Math.PI) / 180);
  return Math.hypot((b.lon - a.lon) * mPerDegLon, (b.lat - a.lat) * 110_574);
}

/**
 * Launch = intercept time − flight time. A launch still ahead just waits for
 * its moment; one that would have to happen before detection is out of range.
 */
export function planLaunch(base: InterceptorBase, target: InterceptTarget, detectionS: number): LaunchPlan {
  const distanceM = groundDistanceM(base.position, target.position);
  const flightS = distanceM / INTERCEPTOR_SPEED_MPS;
  const launchS = target.timeFromStartS - flightS;
  return launchS >= detectionS ? { feasible: true, launchS, flightS, distanceM } : { feasible: false, requiredLaunchS: launchS, distanceM };
}

/** The nearest base to the intercept point that still has stock and can make it in time. */
export function chooseBase(
  bases: readonly InterceptorBase[], stock: ReadonlyMap<string, number>, target: InterceptTarget, detectionS: number,
): { base: InterceptorBase; plan: LaunchPlan & { feasible: true } } | null {
  let best: { base: InterceptorBase; plan: LaunchPlan & { feasible: true } } | null = null;
  for (const base of bases) {
    if ((stock.get(base.id) ?? 0) <= 0) continue;
    const plan = planLaunch(base, target, detectionS);
    if (plan.feasible && (!best || plan.distanceM < best.plan.distanceM)) best = { base, plan };
  }
  return best;
}

/**
 * The flight from the pad to the intercept point: straight over the ground,
 * a ballistic parabola in height that leaves the ground at launch and reaches
 * the intercept height exactly on time.
 */
export function interceptorSamples(
  base: InterceptorBase, target: InterceptTarget, plan: { launchS: number; flightS: number }, start: Date, steps = 24,
): { lon: number; lat: number; height: number; time: Date }[] {
  const T = plan.flightS;
  const vz = (target.position.height + 0.5 * GRAVITY_MPS2 * T * T) / T;
  return Array.from({ length: steps + 1 }, (_, i) => {
    const f = i / steps;
    const t = f * T;
    const time = new Date(start.getTime() + (plan.launchS + t) * 1000);
    // The last sample is pinned so roundoff cannot miss the intercept point.
    if (i === steps) return { ...target.position, time };
    return {
      lon: base.position.lon + f * (target.position.lon - base.position.lon),
      lat: base.position.lat + f * (target.position.lat - base.position.lat),
      height: Math.max(0, vz * t - 0.5 * GRAVITY_MPS2 * t * t),
      time,
    };
  });
}
