import { ClockRange, ClockStep, JulianDate, Viewer } from "cesium";
import type { Emitter } from "./events.js";
import type { CanvasEvents } from "./types.js";

export interface TimeModule {
  /** Seeks to `start` and pauses. Playback stops at `stop`; it never loops. */
  setRange(start: Date, stop: Date): void;
  /** Actual speed, 1×. */
  play(): void;
  pause(): void;
  /** Clamped to the range. */
  seek(t: Date): void;
  readonly current: Date;
  readonly playing: boolean;
}

export interface TimeInternals {
  module: TimeModule;
  /** Current host time, for layers that sample by time. */
  now(): JulianDate;
  /** Where lighting pins the sun. */
  setSunInstant(instant: JulianDate): void;
  destroy(): void;
}

/**
 * The Viewer clock does two jobs: lighting pins it near a fixed instant for the
 * sun, and hosts animate with their own timestamps. An offset decouples them:
 * the Viewer clock reads `sun + (host − start)`, so a host's 20 s scenario plays
 * at 1× while the sun moves 20 s — invisible — and switching lighting mid-play
 * keeps the host time where it was.
 */
export function createTime(viewer: Viewer, emit: Emitter<CanvasEvents>): TimeInternals {
  const clock = viewer.clock;
  clock.clockStep = ClockStep.SYSTEM_CLOCK_MULTIPLIER;
  clock.multiplier = 1;
  clock.clockRange = ClockRange.CLAMPED;
  clock.shouldAnimate = false;

  let sun = JulianDate.clone(clock.currentTime);
  let start = JulianDate.clone(sun);
  let stop = JulianDate.clone(sun);
  let lastTick: number | undefined;

  // Always fresh objects: Clock keeps the reference it is given.
  const toHost = (viewerTime: JulianDate): JulianDate =>
    JulianDate.addSeconds(start, JulianDate.secondsDifference(viewerTime, sun), new JulianDate());
  const toViewer = (host: JulianDate): JulianDate =>
    JulianDate.addSeconds(sun, JulianDate.secondsDifference(host, start), new JulianDate());

  function place(host: JulianDate): void {
    const clamped = JulianDate.lessThan(host, start) ? start : JulianDate.greaterThan(host, stop) ? stop : host;
    clock.startTime = toViewer(start);
    clock.stopTime = toViewer(stop);
    clock.currentTime = toViewer(clamped);
  }

  const onTick = (): void => {
    const ms = JulianDate.toDate(toHost(clock.currentTime)).getTime();
    if (ms === lastTick) return; // paused and unchanged
    lastTick = ms;
    emit.emit("clockTick", new Date(ms));
  };
  // CLAMPED raises onStop on every tick that would pass `stop`.
  const onStop = (): void => { clock.shouldAnimate = false; };
  clock.onTick.addEventListener(onTick);
  clock.onStop.addEventListener(onStop);

  return {
    module: {
      setRange(rangeStart, rangeStop) {
        if (!(rangeStop.getTime() >= rangeStart.getTime())) throw new Error("Time range needs valid dates with stop >= start");
        clock.shouldAnimate = false;
        start = JulianDate.fromDate(rangeStart);
        stop = JulianDate.fromDate(rangeStop);
        place(start);
      },
      play() { clock.shouldAnimate = true; },
      pause() { clock.shouldAnimate = false; },
      seek(t) {
        if (!Number.isFinite(t.getTime())) throw new Error("Cannot seek to an invalid date");
        place(JulianDate.fromDate(t));
      },
      get current() { return JulianDate.toDate(toHost(clock.currentTime)); },
      get playing() { return clock.shouldAnimate; },
    },
    now: () => toHost(clock.currentTime),
    setSunInstant(instant) {
      const host = toHost(clock.currentTime);
      sun = JulianDate.clone(instant);
      place(host);
    },
    destroy() {
      clock.onTick.removeEventListener(onTick);
      clock.onStop.removeEventListener(onStop);
    },
  };
}
