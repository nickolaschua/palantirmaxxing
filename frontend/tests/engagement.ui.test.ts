import { afterEach, describe, expect, it, vi } from "vitest";
import simulation from "../../data/results/demo-simulation-result.json";
import type { SingaporeCanvas } from "../src/lib/index.js";
import { manifest, v2Result } from "./helpers/simulation-v2.js";

vi.mock("../src/lib/index.js", () => ({ SINGAPORE_BOUNDS: { west: 103.6, east: 104.1, south: 1.2, north: 1.5 } }));

import { mountEngagement } from "../src/demo/engagement.js";

function canvasMock() {
  const live = new Set<object>();
  const handlers: Record<string, (payload: unknown) => void> = {};
  const layer = () => {
    const row = { ready: Promise.resolve(), destroy: vi.fn(() => live.delete(row)), setVisible() {}, setStyles() {}, setMarkerVisible() {}, play() {} };
    live.add(row);
    return row;
  };
  const time = { current: new Date(simulation.start), playing: false, setRange() {}, pause() { time.playing = false; }, seek(t: Date) { time.current = t; }, play() { time.playing = true; } };
  return {
    live, handlers, time,
    canvas: {
      scene: { basemap: "plain" }, time,
      camera: { flyTo: () => Promise.resolve(), pose: { lon: 103.8, lat: 1.3, height: 5000, heading: 0, pitch: -45 } },
      on: (event: string, handler: (payload: unknown) => void) => { handlers[event] = handler; return () => { delete handlers[event]; }; },
      addPath: vi.fn(layer), addMarkers: vi.fn(layer), addLabels: vi.fn(layer), addGroundCircles: vi.fn(layer), addBurst: vi.fn(layer),
    } as unknown as SingaporeCanvas,
  };
}
const response = (value: unknown, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => value }) as Response;
const settle = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };
const snapshot = (id: string, result: unknown) => ({ source: "http", resultId: id, publishedAt: "2026-09-26T00:00:00Z", result });
const naive = v2Result({ policy: "naive-launch-on-detection/1", active: 2.5, naive: 2.5, physical: { people_potentially_exposed_total: 100, expected_casualties_central_total: 2 } });
const exact = v2Result({ policy: "optimal-fixed-rank-assignment/1", active: 1.0, naive: 2.5, physical: { people_potentially_exposed_total: 40, expected_casualties_central_total: 1 } });
const loaderFor = (latest: unknown) => vi.fn(async (identity = "latest") =>
  identity === "latest" ? snapshot("latest", latest) : identity === "res-naive" ? snapshot(identity, naive) : snapshot(identity, exact));
function fetchStub(posts: unknown[], pending?: Promise<Response>) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/api/v1/scenario-manifest")) return response(manifest);
    if (url.endsWith("/api/v1/runs") && init?.method === "POST") {
      const body = JSON.parse(String(init.body)); posts.push(body);
      if (pending) return pending;
      const side = body.policy === "naive-launch-on-detection/1" ? "naive" : "exact";
      return response({ runId: `run-${side}`, status: "succeeded", resultKind: "simulation", resultId: `res-${side}` }, 202);
    }
    throw new Error("unexpected request " + url);
  });
}
const pickPolicy = (value: string) => {
  const policy = document.querySelector<HTMLSelectElement>('[aria-label="Simulation policy"]')!;
  policy.value = value; policy.dispatchEvent(new Event("change"));
};
const space = (target: EventTarget = window) => target.dispatchEvent(new KeyboardEvent("keydown", { code: "Space", bubbles: true }));
const panel = () => document.getElementById("panel")!;

// Every mounted view is disposed after its test, even when an assertion fails: a leaked keydown listener would
// answer later tests' Space presses.
const mounted: { dispose(): void }[] = [];
const mount = (canvas: SingaporeCanvas, loader: Parameters<typeof mountEngagement>[2]) => {
  const view = mountEngagement(canvas, panel(), loader);
  mounted.push(view);
  return view;
};
afterEach(() => { for (const view of mounted.splice(0)) view.dispose(); vi.unstubAllGlobals(); document.body.replaceChildren(); vi.restoreAllMocks(); });

describe("engagement screen", () => {
  it("builds the fixed screen and loads the latest result into standby", async () => {
    vi.stubGlobal("fetch", fetchStub([]));
    document.body.append(Object.assign(document.createElement("div"), { id: "panel" }));
    const { canvas, live } = canvasMock();
    const view = mount(canvas, loaderFor(simulation));
    expect(document.getElementById("standby")!.textContent).toContain("No simulation result loaded");
    await settle();
    expect(live.size).toBeGreaterThan(0);
    expect(document.querySelector("#ops .list-area")!.textContent).toContain("No threats detected.");
    expect(document.getElementById("standby")!.textContent).toContain("Standby");
    expect(document.getElementById("comparison-panel")!.textContent).toContain("No run pair yet");
    expect(document.getElementById("standby")!.dataset.resultId).toBe("latest");
    view.dispose();
    expect(live.size).toBe(0);
    expect(document.querySelectorAll("#ops, #presenter, #birds-eye, #standby, #comparison-panel")).toHaveLength(0);
  });

  it("Space submits a Naive and an optimised run, loads both, and starts the replay", async () => {
    const posts: { policy: string; scenarioRef: string }[] = [];
    vi.stubGlobal("fetch", fetchStub(posts));
    document.body.append(Object.assign(document.createElement("div"), { id: "panel" }));
    const { canvas, time } = canvasMock();
    const loader = loaderFor(simulation);
    const view = mount(canvas, loader);
    await settle();
    pickPolicy("optimal-fixed-rank-assignment/1");
    space();
    await settle(); await settle();
    expect(posts.map(p => p.policy)).toEqual(["naive-launch-on-detection/1", "optimal-fixed-rank-assignment/1"]);
    expect(posts.every(p => p.scenarioRef === "sg2:validation:000000")).toBe(true);
    expect(loader.mock.calls.map(c => c[0])).toEqual(expect.arrayContaining(["res-naive", "res-exact"]));
    expect(document.getElementById("standby")!.dataset.phase).toBe("live");
    expect(time.playing).toBe(true);
    const text = document.getElementById("comparison-panel")!.textContent!;
    expect(text).toContain("Live runs · sg2:validation:000000");
    expect(text).toContain("All missiles · Baseline → Optimised");
    expect(text).toContain("100 → 40");
    expect(text).toContain("▼ 60%");
    expect(document.querySelector("#ops .history-view")!.textContent).toContain("#1 · sg2:validation:000000 · Naive vs Exact · ready");
    view.dispose();
  });

  it("replays alone when the drawer's policy is Naive, sending no run", async () => {
    const posts: unknown[] = [];
    vi.stubGlobal("fetch", fetchStub(posts));
    document.body.append(Object.assign(document.createElement("div"), { id: "panel" }));
    const { canvas, handlers, time } = canvasMock();
    const view = mount(canvas, loaderFor(simulation));
    await settle();
    expect(document.getElementById("standby")!.textContent).toContain("other than Naive");
    space();
    await settle();
    expect(posts).toHaveLength(0);
    expect(document.getElementById("standby")!.dataset.phase).toBe("live");
    time.current = new Date(new Date(simulation.start).getTime() + 30_000);
    handlers.clockTick!(time.current);
    expect(document.querySelectorAll("#ops .threats li").length).toBeGreaterThan(0);
    expect(document.getElementById("comparison-panel")!.textContent).toContain("No run pair yet");
    view.dispose();
  });

  it("submits one pair per Space and ignores Space typed inside a field", async () => {
    const posts: unknown[] = [];
    let release!: (value: Response) => void;
    vi.stubGlobal("fetch", fetchStub(posts, new Promise<Response>(resolve => { release = resolve; })));
    document.body.append(Object.assign(document.createElement("div"), { id: "panel" }));
    const { canvas } = canvasMock();
    const view = mount(canvas, loaderFor(simulation));
    await settle();
    pickPolicy("optimal-fixed-rank-assignment/1");
    const seed = document.querySelector<HTMLInputElement>('[aria-label="Simulation seed"]')!;
    space(seed);
    space(); space();
    await settle();
    expect(posts).toHaveLength(2);
    expect(document.getElementById("standby")!.dataset.phase).toBe("submitting");
    expect(document.getElementById("standby")!.textContent).toContain("submitting");
    release(response({ runId: "run-x", status: "failed", error: { code: "STOP", message: "test" } }, 202));
    await settle(); await settle();
    expect(document.getElementById("standby")!.textContent).toContain("Failed · Baseline run failed · STOP: test");
    expect(document.getElementById("standby")!.dataset.phase).toBe("standby");
    view.dispose();
  });

  it("refuses a pair whose results are on different scenarios", async () => {
    const posts: unknown[] = [];
    vi.stubGlobal("fetch", fetchStub(posts));
    document.body.append(Object.assign(document.createElement("div"), { id: "panel" }));
    const { canvas } = canvasMock();
    const other = v2Result({ policy: "optimal-fixed-rank-assignment/1", scenarioRef: "sg2:stress:000001" });
    const loader = vi.fn(async (identity = "latest") => identity === "latest" ? snapshot("latest", simulation) : identity === "res-naive" ? snapshot(identity, naive) : snapshot(identity, other));
    const view = mount(canvas, loader);
    await settle();
    pickPolicy("optimal-fixed-rank-assignment/1");
    space();
    await settle(); await settle();
    expect(document.getElementById("comparison-panel")!.textContent).toContain("Comparison unavailable · Runs are on different scenarios");
    expect(document.getElementById("standby")!.textContent).toContain("Failed · Runs are on different scenarios");
    expect(document.getElementById("standby")!.dataset.phase).toBe("standby");
    view.dispose();
  });
});

describe("engagement screen · review fixes", () => {
  it("a changed drawer policy submits a new pair instead of replaying the old one", async () => {
    const posts: { policy: string }[] = [];
    vi.stubGlobal("fetch", fetchStub(posts));
    document.body.append(Object.assign(document.createElement("div"), { id: "panel" }));
    const { canvas, handlers, time } = canvasMock();
    const view = mount(canvas, loaderFor(simulation));
    await settle();
    pickPolicy("optimal-fixed-rank-assignment/1");
    space();
    await settle(); await settle();
    expect(posts).toHaveLength(2);
    // Let the replay finish: Space then starts over instead of replaying.
    time.current = new Date(new Date(simulation.start).getTime() + 3_600_000);
    handlers.clockTick!(time.current);
    expect(document.getElementById("standby")!.dataset.phase).toBe("done");
    pickPolicy("structured-behavior-cloning/1");
    expect(document.getElementById("standby")!.textContent).toContain("press Space to submit Naive + Imitation");
    space();
    await settle(); await settle();
    expect(posts.map(p => p.policy)).toEqual(["naive-launch-on-detection/1", "optimal-fixed-rank-assignment/1", "naive-launch-on-detection/1", "structured-behavior-cloning/1"]);
    expect(document.querySelectorAll("#ops .history-view .entry")).toHaveLength(2);
    view.dispose();
  });

  it("a failed construction does not touch the shared clock", async () => {
    vi.stubGlobal("fetch", fetchStub([]));
    document.body.append(Object.assign(document.createElement("div"), { id: "panel" }));
    const { canvas, time } = canvasMock();
    const setRange = vi.spyOn(time, "setRange");
    const view = mount(canvas, loaderFor(simulation));
    await settle();
    expect(setRange).toHaveBeenCalledTimes(1);
    vi.mocked(canvas.addGroundCircles).mockImplementationOnce(() => { throw new Error("Injected geometry failure"); });
    view.retry();
    await settle();
    expect(document.body.textContent).toContain("Injected geometry failure");
    expect(setRange).toHaveBeenCalledTimes(1);
    view.dispose();
  });

  it("a drawer result arriving while a pair is pending keeps the pair state", async () => {
    const posts: unknown[] = [];
    let release!: (value: Response) => void;
    vi.stubGlobal("fetch", fetchStub(posts, new Promise<Response>(resolve => { release = resolve; })));
    document.body.append(Object.assign(document.createElement("div"), { id: "panel" }));
    const { canvas } = canvasMock();
    const view = mount(canvas, loaderFor(simulation));
    await settle();
    pickPolicy("optimal-fixed-rank-assignment/1");
    space();
    await settle();
    expect(document.getElementById("standby")!.dataset.phase).toBe("submitting");
    view.retry();
    await settle();
    expect(document.getElementById("standby")!.dataset.phase).toBe("submitting");
    expect([...document.querySelectorAll("#presenter button")].map(b => b.textContent)).toEqual(["History"]);
    space();
    await settle();
    expect(posts).toHaveLength(2);
    release(response({ runId: "run-x", status: "failed", error: { code: "STOP", message: "test" } }, 202));
    await settle(); await settle();
    expect(document.getElementById("standby")!.dataset.phase).toBe("standby");
    view.dispose();
  });

  it("loading a different result drops the active pair from the panel", async () => {
    vi.stubGlobal("fetch", fetchStub([]));
    document.body.append(Object.assign(document.createElement("div"), { id: "panel" }));
    const { canvas } = canvasMock();
    const view = mount(canvas, loaderFor(simulation));
    await settle();
    pickPolicy("optimal-fixed-rank-assignment/1");
    space();
    await settle(); await settle();
    expect(document.getElementById("comparison-panel")!.textContent).toContain("All missiles · Baseline → Optimised");
    document.querySelector<HTMLButtonElement>(".result-metadata > button")!.click(); // Refresh: latest, not the pair's result
    await settle();
    expect(document.getElementById("comparison-panel")!.textContent).toContain("No run pair yet");
    expect(document.querySelector('#ops .history-view .entry[aria-pressed="true"]')).toBeNull();
    view.dispose();
  });
});
