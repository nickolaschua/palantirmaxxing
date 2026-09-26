import assert from "node:assert/strict";
import { chromium } from "@playwright/test";

const origin = process.argv[2] ?? "http://127.0.0.1:5173/?basemap=plain&acceptance=1";
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
  await page.locator("#panel-toggle").click();
  const controls = page.locator('.run-controls[data-kind="simulation"]');
  await controls.getByText("Rehearsed policy demo", { exact: true }).waitFor();
  const panel = page.locator("#comparison-panel");
  await panel.waitFor({ state: "attached" });
  assert.ok((await panel.textContent()).includes("No run pair yet"), "the comparison panel starts without synthetic data");

  for (const expected of steps) {
    const started = Date.now();
    await controls.getByRole("button", { name: expected.button, exact: true }).click();
    await page.locator('.run-controls[data-kind="simulation"][data-status="succeeded"]').waitFor({ timeout: 30_000 });
    const metadata = page.locator('.result-metadata[data-kind="simulation"]');
    await metadata.waitFor();
    const resultId = await metadata.getAttribute("data-result-id");
    assert.ok(resultId, `${expected.button}: a live result is loaded`);
    const payload = await page.evaluate(() => window.__mvpAcceptance?.inspect().simulation?.result);
    assert.ok(payload, `${expected.button}: the loaded payload is inspectable (open with ?acceptance=1)`);
    assert.equal(payload.provenance.scenarioRef, scenarioRef, `${expected.button}: pinned scenario is visible`);
    assert.equal(payload.policy.identity, expected.policy, `${expected.button}: active policy is visible`);
    assert.equal(payload.consequenceSummary.ordinalObjectiveCost.toFixed(3), expected.cost, `${expected.button}: expected rounded cost`);
    assert.equal(await page.locator("#standby").getAttribute("data-phase"), "standby", `${expected.button}: the screen returns to standby with the result loaded`);
    report.steps.push({ button: expected.button, policy: expected.policy, cost: Number(expected.cost),
      elapsedSeconds: Number(((Date.now() - started) / 1000).toFixed(3)), runId: await controls.getAttribute("data-run-id"), resultId });
  }

  report.elapsedSeconds = Number(((Date.now() - startedAt) / 1000).toFixed(3));
  report.status = "passed";
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
} finally {
  await browser.close();
}
