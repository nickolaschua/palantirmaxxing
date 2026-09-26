import { afterEach, describe, expect, it, vi } from "vitest";
import simulation from "../../data/results/demo-simulation-result.json";
import type { SingaporeCanvas } from "../src/lib/index.js";

vi.mock("../src/lib/index.js", () => ({
  SINGAPORE_BOUNDS: { west: 103.6, east: 104.1, south: 1.2, north: 1.5 },
}));

import { mountSimulationResult } from "../src/demo/simulation.js";

function canvasMock() {
  const live = new Set<object>();
  const layer = () => {
    const row = {
      ready: Promise.resolve(),
      destroy: vi.fn(() => live.delete(row)),
      setVisible() {},
      setStyles() {},
      setMarkerVisible() {},
      play() {},
    };
    live.add(row);
    return row;
  };
  return {
    live,
    canvas: {
      scene: { basemap: "osm" },
      time: { current: new Date(simulation.start), setRange() {}, pause() {}, seek() {}, play() {} },
      camera: { flyTo: () => Promise.resolve() },
      on: () => () => {},
      addPath: vi.fn(layer),
      addMarkers: vi.fn(layer),
      addLabels: vi.fn(layer),
      addGroundCircles: vi.fn(layer),
      addBurst: vi.fn(layer),
    } as unknown as SingaporeCanvas,
  };
}

function deferred() {
  let resolve!: (value: unknown) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<unknown>((accept, decline) => {
    resolve = accept;
    reject = decline;
  });
  return { promise, resolve, reject };
}

const settle = async () => {
  for (let index = 0; index < 5; index += 1) await Promise.resolve();
};

const snapshot = (id: string) => ({
  source: "http",
  resultId: id,
  publishedAt: "2026-09-26T00:00:00Z",
  result: structuredClone(simulation),
});

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("simulation loader lifecycle", () => {
  it("keeps the canvas empty while pending, then releases rendered layers on disposal", async () => {
    const pending = deferred();
    const { canvas, live } = canvasMock();
    const view = mountSimulationResult(canvas, document.body, () => pending.promise);
    expect(document.body.textContent).toContain("Loading");
    expect(live.size).toBe(0);
    pending.resolve(simulation);
    await settle();
    expect(live.size).toBeGreaterThan(0);
    view.dispose();
    expect(live.size).toBe(0);
    expect(document.body.childElementCount).toBe(0);
  });

  it.each(["rejection", "invalid schema"])("recovers from %s without duplicate layers", async mode => {
    const loader = vi.fn()
      .mockImplementationOnce(() => mode === "rejection"
        ? Promise.reject(new Error("offline"))
        : Promise.resolve({ schemaVersion: "bad" }))
      .mockResolvedValue(simulation);
    const { canvas, live } = canvasMock();
    const view = mountSimulationResult(canvas, document.body, loader);
    await settle();
    expect(document.body.textContent).toContain("Unavailable");
    expect(document.body.textContent).toContain(mode === "rejection" ? "offline" : "schema");
    expect(live.size).toBe(0);
    document.querySelector<HTMLButtonElement>(".result-load-status button")!.click();
    await settle();
    const count = live.size;
    expect(count).toBeGreaterThan(0);
    view.retry();
    await settle();
    expect(live.size).toBe(count);
    view.dispose();
  });

  it.each([false, true])("ignores a late %s after disposal", async rejects => {
    const pending = deferred();
    const { canvas, live } = canvasMock();
    const view = mountSimulationResult(canvas, document.body, () => pending.promise);
    view.dispose();
    if (rejects) pending.reject(new Error("late"));
    else pending.resolve(simulation);
    await settle();
    expect(live.size).toBe(0);
    expect(document.body.childElementCount).toBe(0);
  });

  it.each([false, true])("ignores a superseded %s", async rejects => {
    const old = deferred();
    const loader = vi.fn().mockReturnValueOnce(old.promise).mockResolvedValue(simulation);
    const { canvas, live } = canvasMock();
    const view = mountSimulationResult(canvas, document.body, loader);
    view.retry();
    await settle();
    const count = live.size;
    if (rejects) old.reject(new Error("stale"));
    else old.resolve({ schemaVersion: "bad" });
    await settle();
    expect(live.size).toBe(count);
    expect(document.querySelector<HTMLElement>(".result-load-status")?.hidden).toBe(true);
    view.dispose();
  });

  it("preserves the validated snapshot when retry validation fails", async () => {
    const loader = vi.fn().mockResolvedValueOnce(snapshot("A")).mockResolvedValue({ schemaVersion: "bad" });
    const { canvas, live } = canvasMock();
    const view = mountSimulationResult(canvas, document.body, loader);
    await settle();
    const count = live.size;
    view.retry();
    await settle();
    expect(live.size).toBe(count);
    expect(view.snapshot()?.resultId).toBe("A");
    expect(document.body.textContent).toContain("Unavailable");
    view.dispose();
  });
});

describe("simulation refresh ownership", () => {
  it("releases replaced layers across ten successful refreshes", async () => {
    const { canvas, live } = canvasMock();
    const loader = vi.fn().mockResolvedValue(snapshot("A"));
    const view = mountSimulationResult(canvas, document.body, loader);
    await settle();
    const count = live.size;
    for (let index = 0; index < 10; index += 1) {
      loader.mockResolvedValue(snapshot(`B${index}`));
      view.retry();
      await settle();
      expect(live.size).toBe(count);
    }
    expect(view.snapshot()?.resultId).toBe("B9");
    view.dispose();
    expect(live.size).toBe(0);
  });

  it("cleans up a partial render and preserves the preceding result", async () => {
    const { canvas, live } = canvasMock();
    const loader = vi.fn().mockResolvedValueOnce(snapshot("A")).mockResolvedValue(snapshot("B"));
    const view = mountSimulationResult(canvas, document.body, loader);
    await settle();
    const count = live.size;
    vi.mocked(canvas.addGroundCircles).mockImplementationOnce(() => {
      throw new Error("Injected geometry failure");
    });
    view.retry();
    await settle();
    expect(live.size).toBe(count);
    expect(view.snapshot()?.resultId).toBe("A");
    expect(document.body.textContent).toContain("Injected geometry failure");
    expect(document.querySelectorAll("#simulation-result")).toHaveLength(1);
    view.dispose();
  });

  it("aborts superseded requests and ignores their late resolution", async () => {
    const { canvas, live } = canvasMock();
    const old = deferred();
    const loader = vi.fn().mockReturnValueOnce(old.promise).mockResolvedValue(snapshot("B"));
    const view = mountSimulationResult(canvas, document.body, loader);
    const firstSignal = loader.mock.calls[0]![1] as AbortSignal;
    view.retry();
    await settle();
    expect(firstSignal.aborted).toBe(true);
    old.resolve(snapshot("A"));
    await settle();
    expect(view.snapshot()?.resultId).toBe("B");
    const secondSignal = loader.mock.calls[1]![1] as AbortSignal;
    view.dispose();
    expect(secondSignal.aborted).toBe(true);
    expect(live.size).toBe(0);
  });

  it("can be disposed repeatedly after a successful render", async () => {
    const { canvas, live } = canvasMock();
    const view = mountSimulationResult(canvas, document.body, async () => simulation);
    await settle();
    expect(live.size).toBeGreaterThan(0);
    view.dispose();
    expect(() => view.dispose()).not.toThrow();
    expect(live.size).toBe(0);
    expect(document.body.childElementCount).toBe(0);
  });
});
