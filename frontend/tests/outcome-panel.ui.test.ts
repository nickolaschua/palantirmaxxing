import { afterEach, describe, expect, it, vi } from "vitest";
import type { SingaporeCanvas } from "../src/lib/index.js";
import { mountOutcomePanel } from "../src/demo/outcome-panel.js";
import { parseSimulationResult } from "../src/demo/simulation-model.js";
import type { SimulationResultV2 } from "../src/demo/simulation-model.js";
import type { RunPair } from "../src/demo/engagement-model.js";
import { v2Result } from "./helpers/simulation-v2.js";

function canvasMock() {
  const live = new Set<object>();
  const layer = () => { const row = { ready: Promise.resolve(), destroy: vi.fn(() => live.delete(row)), setVisible() {}, setStyles: vi.fn() }; live.add(row); return row; };
  return { live, canvas: { on: () => () => {}, addMarkers: vi.fn(layer), addGroundCircles: vi.fn(layer) } as unknown as SingaporeCanvas };
}
const parse = (raw: unknown) => parseSimulationResult(raw) as SimulationResultV2;
const pair = (baseline: SimulationResultV2, optimised: SimulationResultV2, problem?: string): RunPair => ({
  id: 1, scenarioRef: "sg2:validation:000000",
  baseline: { policy: "naive-launch-on-detection/1", status: "succeeded", runId: "run-n", resultId: "res-n" },
  optimised: { policy: "optimal-fixed-rank-assignment/1", status: "succeeded", runId: "run-e", resultId: "res-e" },
  ...(problem ? { problem } : { results: { baseline, optimised } }),
});
const button = (label: string): HTMLButtonElement => {
  const match = [...document.querySelectorAll<HTMLButtonElement>("button")].find(b => b.textContent === label);
  if (!match) throw new Error(`Button not found: ${label}`);
  return match;
};
afterEach(() => document.body.replaceChildren());

describe("outcome panel", () => {
  it("walks Baseline, Optimised, Compare and the scenario-wide view from two live runs", () => {
    const { canvas, live } = canvasMock();
    const onSelect = vi.fn(), onReplay = vi.fn();
    const panel = mountOutcomePanel(canvas, { onSelect, onReplay });
    expect(document.body.textContent).toContain("No run pair yet");
    const baseline = parse(v2Result({ policy: "naive-launch-on-detection/1", active: 2.5, naive: 2.5, physical: { people_potentially_exposed_total: 100, expected_casualties_central_total: 2 } }));
    const optimised = parse(v2Result({ active: 1.0, naive: 2.5, physical: { people_potentially_exposed_total: 40, expected_casualties_central_total: 1 }, unhandledLast: true }));
    panel.setPair(pair(baseline, optimised));
    expect(live.size).toBe(2);
    const text = () => document.getElementById("comparison-panel")!.textContent!;
    expect(text()).toContain("Live runs · sg2:validation:000000");
    expect(text()).toContain("People potentially exposed");
    expect(text()).toContain("Assumption-grade expected casualties");
    expect(text()).toContain("Threats intercepted");
    expect(text()).toContain("8 of 8 → 7 of 8");
    expect(text()).toContain("Unoptimised reference");
    expect(text()).toContain("Supplied 100 m area");
    expect(text()).not.toContain("Service disruption");
    expect(text()).not.toContain("Illustrative");
    button("Show optimised outcome").click();
    expect(text()).toContain("Optimised result");
    button("Compare outcomes").click();
    expect(text()).toContain("Live comparison");
    expect(text()).toContain("Training cost");
    button("Next missile").click();
    expect(onSelect).toHaveBeenCalledWith("threat-02");
    expect(text()).toContain("threat-02 - Missile 2 of 8");
    button("All missiles (8)").click();
    expect(text()).toContain("Scenario-wide comparison");
    expect(text()).toContain("Active minus naive cost");
    expect(text()).toContain("Limitations");
    button("Replay tracks").click();
    expect(onReplay).toHaveBeenCalled();
    panel.dispose();
    expect(live.size).toBe(0);
    expect(document.getElementById("comparison-panel")).toBeNull();
  });

  it("shows unavailable figures, a naive-cost mismatch, and a refused pair", () => {
    const { canvas } = canvasMock();
    const panel = mountOutcomePanel(canvas, { onSelect() {}, onReplay() {} });
    const baseline = parse(v2Result({ policy: "naive-launch-on-detection/1", active: 3.0, naive: 3.0, physical: { expected_casualties_central_total: 0 } }));
    const optimised = parse(v2Result({ active: 1.0, naive: 2.5, physical: { expected_casualties_central_total: 0 } }));
    panel.setPair(pair(baseline, optimised));
    const text = () => document.getElementById("comparison-panel")!.textContent!;
    expect(text()).toContain("unavailable → unavailable");
    expect(text()).toContain("0 → 0no change");
    expect(text()).toContain("Naive cost differs from the optimised run's record (2.5)");
    panel.setPair(pair(baseline, optimised, "Runs are on different scenarios"));
    expect(text()).toContain("Comparison unavailable · Runs are on different scenarios");
    expect(document.querySelectorAll(".story-steps")).toHaveLength(0);
    panel.setPair(null);
    expect(text()).toContain("No run pair yet");
    panel.dispose();
  });

  it("selectThreat follows the threats list without echoing the selection back", () => {
    const { canvas } = canvasMock();
    const onSelect = vi.fn();
    const panel = mountOutcomePanel(canvas, { onSelect, onReplay() {} });
    panel.setPair(pair(parse(v2Result({ policy: "naive-launch-on-detection/1", active: 2, naive: 2 })), parse(v2Result({}))));
    panel.selectThreat("threat-03");
    expect(document.getElementById("comparison-panel")!.textContent).toContain("threat-03 - Missile 3 of 8");
    expect(onSelect).not.toHaveBeenCalled();
    panel.dispose();
  });
});
