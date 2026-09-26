import { afterEach, describe, expect, it, vi } from "vitest";
import simulation from "../../data/results/demo-simulation-result.json";
import type { SingaporeCanvas } from "../src/lib/index.js";

vi.mock("../src/lib/index.js", () => ({ SINGAPORE_BOUNDS: { west: 103.6, east: 104.1, south: 1.2, north: 1.5 } }));

import { mountDecision } from "../src/demo/decision.js";
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

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});
describe("multi-threat comparison view", () => {
  it("renders the bundled fallback, advances stages, and disposes every layer", async () => {
    const { canvas, live } = canvasMock();
    const view = await mountDecision(canvas, { lighting: "midday" });

    expect(document.body.textContent).toContain("Outcome comparison");
    expect(document.body.textContent).toContain("Baseline - earliest feasible");
    expect(live.size).toBeGreaterThan(0);

    const next = [...document.querySelectorAll<HTMLButtonElement>("button")]
      .find(button => button.textContent === "Show optimised outcome");
    next?.click();
    expect(document.body.textContent).toContain("Optimised - consequence-aware v1");

    const compare = [...document.querySelectorAll<HTMLButtonElement>("button")]
      .find(button => button.textContent === "Compare outcomes");
    compare?.click();
    expect(document.body.textContent).toContain("Measured improvement");

    view.dispose();
    expect(live.size).toBe(0);
    expect(document.body.childElementCount).toBe(0);
  });

  it("navigates across missiles and opens the aggregate comparison", async () => {
    const { canvas } = canvasMock();
    const view = await mountDecision(canvas, { lighting: "midday" });

    const nextThreat = [...document.querySelectorAll<HTMLButtonElement>("button")]
      .find(button => button.textContent === "Next");
    nextThreat?.click();
    expect(document.body.textContent).toContain("M-02 - Missile 2 of 3");

    const all = document.querySelector<HTMLButtonElement>(".all-missiles-button");
    all?.click();
    expect(document.body.textContent).toContain("All missiles - 3 threats");
    expect(document.body.textContent).toContain("Scenario-wide comparison");

    view.dispose();
  });
});

describe("simulation result view", () => {
  it("shows pending state, validates, draws, and disposes all layers", async () => {
    const pending = deferred();
    const { canvas, live } = canvasMock();
    const view = mountSimulationResult(canvas, document.body, () => pending.promise);

    expect(document.body.textContent).toContain("Loading");
    expect(live.size).toBe(0);
    pending.resolve(simulation);
    await settle();

    expect(live.size).toBeGreaterThan(0);
    expect(document.querySelector<HTMLElement>(".result-load-status")?.hidden).toBe(true);
    view.dispose();
    expect(live.size).toBe(0);
    expect(document.body.childElementCount).toBe(0);
  });

  it("reports a failed load and retries without duplicating layers", async () => {
    const loader = vi.fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue(simulation);
    const { canvas, live } = canvasMock();
    const view = mountSimulationResult(canvas, document.body, loader);

    await settle();
    expect(document.body.textContent).toContain("Unavailable");
    expect(document.body.textContent).toContain("offline");

    document.querySelector<HTMLButtonElement>(".result-load-status button")?.click();
    await settle();
    const count = live.size;
    expect(count).toBeGreaterThan(0);

    view.retry();
    await settle();
    expect(live.size).toBe(count);
    view.dispose();
    expect(live.size).toBe(0);
  });

  it("ignores stale completion after a superseding retry", async () => {
    const old = deferred();
    const loader = vi.fn().mockReturnValueOnce(old.promise).mockResolvedValue(simulation);
    const { canvas, live } = canvasMock();
    const view = mountSimulationResult(canvas, document.body, loader);

    view.retry();
    await settle();
    const count = live.size;
    old.resolve({ schemaVersion: "bad" });
    await settle();

    expect(live.size).toBe(count);
    expect(document.querySelector<HTMLElement>(".result-load-status")?.hidden).toBe(true);
    view.dispose();
  });

  it.each([undefined, 0])("distinguishes an omitted consequence figure from %s", async value => {
    const artifact = structuredClone(simulation);
    const physical = artifact.consequenceSummary.physicalComponents as Record<string, number>;
    for (const key of ["people_potentially_exposed_total", "expected_casualties_central_total"]) {
      if (value === undefined) delete physical[key];
      else physical[key] = value;
    }
    const { canvas } = canvasMock();
    const view = mountSimulationResult(canvas, document.body, async () => artifact);
    await settle();

    expect(document.body.textContent).toContain(
      `${value === undefined ? "Unavailable" : "0"} people potentially exposed`,
    );
    expect(document.body.textContent).toContain(
      `${value === undefined ? "Unavailable" : "0"} assumption-grade expected casualties`,
    );
    view.dispose();
  });

  it("keeps the newest validated snapshot after a failed refresh", async () => {
    const snapshot = (id: string) => ({
      source: "http",
      resultId: id,
      publishedAt: "2026-09-26T00:00:00Z",
      result: structuredClone(simulation),
    });
    const loader = vi.fn().mockResolvedValueOnce(snapshot("A")).mockResolvedValueOnce(snapshot("B")).mockRejectedValue(new Error("offline"));
    const { canvas, live } = canvasMock();
    const view = mountSimulationResult(canvas, document.body, loader);

    await settle();
    const count = live.size;
    view.retry();
    await settle();
    expect(view.snapshot()?.resultId).toBe("B");
    expect(live.size).toBe(count);

    view.retry();
    await settle();
    expect(view.snapshot()?.resultId).toBe("B");
    expect(document.body.textContent).toContain("offline");
    expect(live.size).toBe(count);

    view.dispose();
    expect(live.size).toBe(0);
  });
});
