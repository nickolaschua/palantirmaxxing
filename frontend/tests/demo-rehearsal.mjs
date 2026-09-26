import assert from "node:assert/strict";
import { chromium } from "@playwright/test";

const origin = process.argv[2] ?? "http://127.0.0.1:5173/?basemap=plain";
const scenarioRef = "sg2:validation:000000";
const steps = [
  { button: "1 · Naive", policy: "naive-launch-on-detection/1", cost: "2.464" },
  { button: "2 · Exact", policy: "optimal-fixed-rank-assignment/1", cost: "0.447" },
  { button: "3 · Imitation", policy: "structured-behavior-cloning/1", cost: "0.447" },
];

const browser = await chromium.launch({ channel: "chromium", headless: true });
const startedAt = Date.now();
const report = { origin, scenarioRef, steps: [] };

try {
  const page = await browser.newPage({ viewport: { width: 1640, height: 1280 } });
  page.setDefaultTimeout(30_000);
  await page.goto(origin, { waitUntil: "domcontentloaded" });

  const controls = page.locator('.run-controls[data-kind="simulation"]');
  await controls.getByText("Rehearsed policy demo", { exact: true }).waitFor();
  const retrospective = page.locator('#comparison-panel[data-source="bundled-retrospective"]');
  await retrospective.waitFor({ state: "attached" });
  assert.equal(await retrospective.locator(".synthetic-badge").textContent(),
    "Bundled retrospective · not the live run");

  for (const expected of steps) {
    const started = Date.now();
    await controls.getByRole("button", { name: expected.button, exact: true }).click();
    await page.locator('.run-controls[data-kind="simulation"][data-status="succeeded"]').waitFor({ timeout: 30_000 });

    const result = page.locator(`#simulation-result[data-policy="${expected.policy}"]`);
    await result.waitFor({ timeout: 30_000 });
    const text = await result.textContent();
    assert.ok(text?.includes(scenarioRef), `${expected.button}: pinned scenario is visible`);
    assert.ok(text?.includes("6 intercepted · 0 unhandled"), `${expected.button}: constraint-safe outcome is visible`);
    assert.ok(text?.includes(`Active ${expected.policy}`), `${expected.button}: active policy is visible`);
    assert.ok(text?.includes(`cost ${expected.cost}`), `${expected.button}: expected rounded cost is visible`);
    assert.ok((await result.locator("summary").textContent())?.includes(`cost ${expected.cost}`),
      `${expected.button}: the collapsed result heading keeps the cost visible`);
    assert.ok(["playing", "complete"].includes(await result.getAttribute("data-replay")),
      `${expected.button}: the visible map replay starts automatically`);
    assert.ok(await result.locator(".live-impact-grid").isVisible(),
      `${expected.button}: the policy impact scorecard is visible`);

    report.steps.push({
      button: expected.button,
      policy: expected.policy,
      cost: Number(expected.cost),
      elapsedSeconds: Number(((Date.now() - started) / 1000).toFixed(3)),
      runId: await controls.getAttribute("data-run-id"),
      visibleReplay: true,
    });
  }

  report.elapsedSeconds = Number(((Date.now() - startedAt) / 1000).toFixed(3));
  report.status = "passed";
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
} finally {
  await browser.close();
}
