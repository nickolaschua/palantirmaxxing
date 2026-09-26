import { afterEach, describe, expect, it, vi } from "vitest";
import planning from "../../data/results/demo-planning-result.json";
import simulation from "../../data/results/demo-simulation-result.json";
import type { SingaporeCanvas } from "../src/lib/index.js";
vi.mock("../src/lib/index.js", () => ({ SINGAPORE_BOUNDS: { west: 103.6, east: 104.1, south: 1.2, north: 1.5 } }));
vi.mock("../src/demo/inspector.js", () => ({
  mountInspector: () => ({
    setBasemap() {}, setLighting() {}, dispose() {}, setRouteVisible() {},
    setCircleStyles() {}, close() {}, syncTime() {}, open() {},
  }),
}));
import { mountDecision } from "../src/demo/decision.js";
import { mountSimulationResult } from "../src/demo/simulation.js";

function canvasMock() {
  const live = new Set<object>();
  const layer = () => {
    const row = { ready: Promise.resolve(), destroy: vi.fn(() => live.delete(row)),
      setVisible() {}, setStyles() {}, setMarkerVisible() {}, play() {} };
    live.add(row);
    return row;
  };
  return { live, canvas: {
    scene: { basemap: "osm" }, time: { current: new Date(planning.start), setRange() {}, pause() {}, seek() {}, play() {} },
    camera: { flyTo: () => Promise.resolve() }, on: () => () => {},
    addPath: vi.fn(layer), addMarkers: vi.fn(layer), addLabels: vi.fn(layer),
    addGroundCircles: vi.fn(layer), addBurst: vi.fn(layer),
  } as unknown as SingaporeCanvas };
}
function deferred() {
  let resolve!: (value: unknown) => void, reject!: (reason: unknown) => void;
  const promise = new Promise<unknown>((a, b) => { resolve = a; reject = b; });
  return { promise, resolve, reject };
}
const settle = async () => { for (let i = 0; i < 5; i++) await Promise.resolve(); };
afterEach(() => { document.body.replaceChildren(); });
for (const kind of ["planning", "simulation"] as const) {
  describe(kind + " view with actual artifact", () => {
    const artifact = kind === "planning" ? planning : simulation;
    function mount(loader: () => Promise<unknown>) {
      const { canvas, live } = canvasMock();
      const view = kind === "planning"
        ? mountDecision(canvas, { lighting: "midday" }, loader)
        : mountSimulationResult(canvas, document.body, loader);
      return { view, live };
    }
    it("shows pending state, validates then draws, and disposes all layers", async () => {
      const pending = deferred();
      const { view, live } = mount(() => pending.promise);
      expect(document.body.textContent).toContain("Loading");
      expect(live.size).toBe(0);
      pending.resolve(artifact); await settle();
      expect(live.size).toBeGreaterThan(0);
      expect(document.querySelector<HTMLElement>(".result-load-status")?.hidden).toBe(true);
      view.dispose(); expect(live.size).toBe(0); expect(document.body.childElementCount).toBe(0);
    });
    for (const mode of ["rejection", "invalid schema"]) {
      it(mode + " displays a reason and Retry recovers without duplicate layers", async () => {
        const loader = vi.fn().mockImplementationOnce(() => mode === "rejection" ? Promise.reject(new Error("offline")) : Promise.resolve({ schemaVersion: "bad" }))
          .mockResolvedValue(artifact);
        const { view, live } = mount(loader);
        await settle();
        expect(document.body.textContent).toContain("Unavailable");
        expect(document.body.textContent).toContain(mode === "rejection" ? "offline" : "schema");
        expect(live.size).toBe(0);
        document.querySelector<HTMLButtonElement>(".result-load-status button")!.click();
        await settle(); const count = live.size; expect(count).toBeGreaterThan(0);
        view.retry(); await settle(); expect(live.size).toBe(count);
        view.dispose(); expect(live.size).toBe(0);
      });
    }
    for (const rejects of [false, true]) {
      it("ignores " + (rejects ? "rejection" : "resolution") + " after disposal", async () => {
        const pending = deferred(); const { view, live } = mount(() => pending.promise);
        view.dispose();
        if (rejects) pending.reject(new Error("late")); else pending.resolve(artifact);
        await settle(); expect(live.size).toBe(0); expect(document.body.childElementCount).toBe(0);
      });
      it("ignores superseded " + (rejects ? "rejection" : "resolution"), async () => {
        const old = deferred();
        const { view, live } = mount(vi.fn().mockReturnValueOnce(old.promise).mockResolvedValue(artifact));
        view.retry(); await settle(); const count = live.size;
        if (rejects) old.reject(new Error("stale")); else old.resolve({ schemaVersion: "bad" });
        await settle(); expect(live.size).toBe(count);
        expect(document.querySelector<HTMLElement>(".result-load-status")?.hidden).toBe(true);
        view.dispose(); expect(live.size).toBe(0);
      });
    }
    it("keeps validated snapshot when retry validation fails", async () => {
      const { view, live } = mount(vi.fn().mockResolvedValueOnce(artifact).mockResolvedValue({ schemaVersion: "bad" }));
      await settle(); const count = live.size;
      view.retry(); await settle(); expect(live.size).toBe(count); expect(document.body.textContent).toContain("Unavailable");
      view.dispose();
    });
  });
}
it.each([undefined, 0])("simulation figures distinguish omission from zero: %s", async value => {
  const artifact = structuredClone(simulation);
  const physical = artifact.consequenceSummary.physicalComponents as Record<string, number>;
  for (const key of ["people_potentially_exposed_total", "expected_casualties_central_total"]) {
    if (value === undefined) delete physical[key]; else physical[key] = value;
  }
  const { canvas } = canvasMock();
  const view = mountSimulationResult(canvas, document.body, async () => artifact); await settle();
  expect(document.body.textContent).toContain((value === undefined ? "Unavailable" : "0") + " people potentially exposed");
  expect(document.body.textContent).toContain((value === undefined ? "Unavailable" : "0") + " assumption-grade expected casualties");
  view.dispose();
});

for (const kind of ["planning", "simulation"] as const) {
  describe(kind + " refresh ownership", () => {
    const artifact = kind === "planning" ? planning : simulation;
    const snapshot = (id: string) => ({ source: "http", resultId: id, publishedAt: "2026-09-26T00:00:00Z", result: structuredClone(artifact) });
    function mount(canvas: SingaporeCanvas, loader: () => Promise<unknown>) {
      return kind === "planning" ? mountDecision(canvas, { lighting: "midday" }, loader)
        : mountSimulationResult(canvas, document.body, loader);
    }
    it("keeps identity on failed refresh and releases layers across ten replacements", async () => {
      const { canvas, live } = canvasMock();
      const load = vi.fn().mockResolvedValue(snapshot("A"));
      const view = mount(canvas, load);
      await settle(); const count = live.size;
      for (let i = 0; i < 10; i++) { load.mockResolvedValue(snapshot("B" + i)); view.retry(); await settle(); expect(live.size).toBe(count); }
      expect(document.querySelector(`.result-metadata[data-kind=${kind}]`)?.getAttribute("data-result-id")).toBe("B9");
      load.mockRejectedValue(new Error("offline")); view.retry(); await settle();
      expect(live.size).toBe(count);
      expect(view.snapshot()?.resultId).toBe("B9");
      view.dispose(); expect(live.size).toBe(0); expect(document.body.childElementCount).toBe(0);
    });
    it("cleans up partial rendering and keeps the preceding result", async () => {
      const { canvas, live } = canvasMock();
      const view = mount(canvas, vi.fn().mockResolvedValueOnce(snapshot("A")).mockResolvedValue(snapshot("B")));
      await settle(); const count = live.size;
      vi.mocked(canvas.addGroundCircles).mockImplementationOnce(() => { throw new Error("Injected geometry failure"); });
      view.retry(); await settle();
      expect(live.size).toBe(count);
      expect(view.snapshot()?.resultId).toBe("A");
      expect(document.body.textContent).toContain("Injected geometry failure");
      expect(document.querySelectorAll(kind === "planning" ? "#decision-tray" : "#simulation-result").length).toBe(1);
      view.dispose(); expect(live.size).toBe(0);
    });
    it("aborts superseded requests and keeps newer metadata when an ignored abort resolves late", async () => {
      const { canvas, live } = canvasMock();
      const old = deferred();
      const load = vi.fn().mockReturnValueOnce(old.promise).mockResolvedValue(snapshot("B"));
      const view = mount(canvas, load);
      const firstSignal = load.mock.calls[0]![1] as AbortSignal;
      view.retry(); await settle();
      expect(firstSignal.aborted).toBe(true);
      old.resolve(snapshot("A")); await settle();
      expect(view.snapshot()?.resultId).toBe("B");
      const secondSignal = load.mock.calls[1]![1] as AbortSignal;
      view.dispose(); expect(secondSignal.aborted).toBe(true); expect(live.size).toBe(0);
    });
  });
}

it("planning disposal removes its keyboard/clock listeners and pending outcome timer", async () => {
  vi.useFakeTimers();
  const add = vi.spyOn(window, "addEventListener");
  const remove = vi.spyOn(window, "removeEventListener");
  try {
    const { canvas, live } = canvasMock();
    let now = new Date(planning.start);
    Object.defineProperty(canvas.time, "current", { get: () => now });
    canvas.time.seek = date => { now = date; };
    let tick: ((date: Date) => void) | undefined;
    const off = vi.fn();
    canvas.on = ((_event: string, listener: (date: Date) => void) => { tick = listener; return off; }) as SingaporeCanvas["on"];
    const view = mountDecision(canvas, { lighting: "midday" }, async () => planning);
    await settle();
    document.querySelector<HTMLButtonElement>("#presenter button")!.click();
    document.querySelector<HTMLButtonElement>(".card .pick")!.click();
    document.querySelector<HTMLButtonElement>(".card .fire")!.dispatchEvent(new MouseEvent("click", { detail: 1 }));
    now = new Date(new Date(planning.end).getTime() + 10000);
    tick!(now);
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    const key = add.mock.calls.find(call => call[0] === "keydown")![1];
    view.dispose();
    expect(off).toHaveBeenCalledTimes(1);
    expect(remove).toHaveBeenCalledWith("keydown", key);
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(5000);
    expect(live.size).toBe(0);
    expect(document.body.childElementCount).toBe(0);
  } finally { add.mockRestore(); remove.mockRestore(); vi.useRealTimers(); }
});
