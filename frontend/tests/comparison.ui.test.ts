import { afterEach, describe, expect, it, vi } from "vitest";
import type { SingaporeCanvas } from "../src/lib/index.js";
import { mountComparison } from "../src/demo/comparison.js";

function canvasMock(): SingaporeCanvas {
  const layer = () => ({
    ready: Promise.resolve(),
    destroy: vi.fn(),
    setVisible: vi.fn(),
    setStyles: vi.fn(),
  });
  return {
    time: { setRange: vi.fn(), seek: vi.fn(), play: vi.fn() },
    camera: { flyTo: vi.fn(() => Promise.resolve()) },
    addPath: vi.fn(layer),
    addLabels: vi.fn(layer),
    addMarkers: vi.fn(layer),
    addGroundCircles: vi.fn(layer),
  } as unknown as SingaporeCanvas;
}

const button = (label: string): HTMLButtonElement => {
  const match = [...document.querySelectorAll<HTMLButtonElement>("button")].find(item => item.textContent === label);
  if (!match) throw new Error(`Button not found: ${label}`);
  return match;
};

afterEach(() => document.body.replaceChildren());

describe("retrospective comparison presentation", () => {
  it("explains estimates plainly and generates the selected rationale from supplied values", async () => {
    const view = await mountComparison(canvasMock(), { lighting: "midday" });
    expect(document.body.textContent).toContain("The large number is the central estimate");
    expect(document.body.textContent).toContain("People affected multiplied by the number of hours their service is unavailable");
    expect(document.body.textContent).toContain("service-hours lost");
    expect(document.body.textContent).not.toContain("Time to 90% function");
    expect(document.body.textContent).not.toContain("Evidence quality");

    button("3 Compare").click();
    expect(document.body.textContent).toContain("Reduces people potentially affected by 6,400 (62%)");
    expect(document.body.textContent).toContain("44,500 of 50,000 paired samples");

    view.dispose();
  });

  it("rounds scenario robustness and lets the presenter close and restore the panel", async () => {
    const view = await mountComparison(canvasMock(), { lighting: "midday" });
    button("All missiles (3)").click();
    expect(document.body.textContent).not.toContain("Scenario robustness and provenance");

    button("Close panel").click();
    const panel = document.querySelector<HTMLElement>("#comparison-panel")!;
    const restore = document.querySelector<HTMLButtonElement>(".restore-comparison-panel")!;
    expect(panel.hidden).toBe(true);
    expect(restore.hidden).toBe(false);
    restore.click();
    expect(panel.hidden).toBe(false);

    view.dispose();
  });
});
