import { existsSync, readFileSync } from 'node:fs';
import { chromium } from '@playwright/test';
import { parseDataset } from '../src/demo/population-model.ts';

for (const path of ['../data/processed/population-display.geojson', 'public/population.geojson']) {
  const data = parseDataset(JSON.parse(readFileSync(path, 'utf8')));
  if (!data.features.length) throw new Error(`Empty prepared display dataset: ${path}`);
}
const executable = chromium.executablePath();
if (!existsSync(executable)) {
  throw new Error(`Missing Chromium: ${executable}. Recovery: cd frontend && npx playwright install chromium`);
}
let browser;
try {
  browser = await chromium.launch({ channel: 'chromium', timeout: 30000 });
  console.log(JSON.stringify({ node: process.version, chromium: browser.version(), executable }));
} catch (error) {
  throw new Error(`Chromium prerequisite failed. Recovery: cd frontend && npx playwright install --with-deps chromium. ${error}`);
} finally {
  await browser?.close();
}
