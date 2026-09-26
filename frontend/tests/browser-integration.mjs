import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { createWriteStream, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:net';
import { resolve } from 'node:path';
import { chromium } from '@playwright/test';

const [gate, evidence, inputs, python] = process.argv.slice(2);
mkdirSync(evidence, { recursive: true });
const children = [], assertions = [];
let browser, context, page, closing = false;
function check(condition, description) {
  assert.ok(condition, description);
  assertions.push(description);
}
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
function start(command, args, name, env = process.env, cwd = resolve('..')) {
  const child = spawn(command, args, { cwd, env, detached: true, stdio: ['pipe', 'pipe', 'pipe'] });
  children.push(child);
  const log = createWriteStream(resolve(evidence, `${name}.log`));
  child.stdout.pipe(log); child.stderr.pipe(log);
  child.on('error', error => { child.startError = error; });
  return child;
}
async function cleanup() {
  if (closing) return;
  closing = true;
  await browser?.close().catch(() => {});
  for (const child of children.reverse()) {
    if (child.exitCode === null) {
      try { process.kill(-child.pid, 'SIGTERM'); } catch {}
      await Promise.race([new Promise(r => child.once('exit', r)), delay(3000)]);
      try { process.kill(-child.pid, 'SIGKILL'); } catch {}
    }
  }
}
process.on('SIGTERM', async () => { await cleanup(); process.exit(143); });
process.on('SIGINT', async () => { await cleanup(); process.exit(130); });
const listeningPort = async () => {
  const server = createServer();
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const port = server.address().port;
  await new Promise(r => server.close(r));
  return port;
};
async function until(fn, description, timeout = 30000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    if (children.some(c => c.exitCode !== null || c.startError)) throw new Error('Required server exited unexpectedly');
    try { if (await fn()) return; } catch (e) { if (Date.now() - start > timeout - 200) throw e; }
    await delay(100);
  }
  throw new Error(`Timed out: ${description}`);
}
try {
  const api = start(python, ['scripts/browser_fixture_server.py', inputs], 'backend');
  const lines = createInterface({ input: api.stdout });
  const waiting = [], pending = [];
  lines.on('line', line => { const value = JSON.parse(line); const waiter = waiting.shift(); if (waiter) waiter(value); else pending.push(value); });
  const nextLine = () => pending.length ? Promise.resolve(pending.shift()) : new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Timed out waiting for test host')), 30000);
    waiting.push(value => { clearTimeout(timer); resolve(value); });
  });
  const ready = await nextLine();
  const publish = async (kind, payload) => {
    api.stdin.write(JSON.stringify({ action: 'publish', kind, payload }) + '\n');
    const response = await nextLine();
    if (response.error) throw new Error(response.error);
    return response.value;
  };
  const command = async action => { api.stdin.write(JSON.stringify({ action }) + '\n'); const response = await nextLine(); if (response.error) throw new Error(response.error); return response.value; };
  const port = await listeningPort();
  const origin = `http://127.0.0.1:${port}`;
  start(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], 'vite',
    { ...process.env, MVP_API_TARGET: `http://127.0.0.1:${ready.port}` }, process.cwd());
  await until(async () => (await fetch(origin)).ok, 'Vite ready');
  browser = await chromium.launch({ channel: 'chromium', headless: true });
  context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
  page = await context.newPage();
  page.setDefaultTimeout(15000);
  const errors = [], requests = [], external = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => requests.push(request.url()));
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.protocol === 'http:' || url.protocol === 'https:') {
      if (url.origin !== origin) { external.push(url.href); return route.abort('blockedbyclient'); }
    }
    return route.continue();
  });
  const url = origin + '/?basemap=plain&acceptance=1';
  const meta = kind => page.locator(`.result-metadata[data-kind="${kind}"]`);
  async function loaded(kind, identity) {
    await until(async () => (await meta(kind).getAttribute('data-result-id')) === identity, `${kind} snapshot ${identity}`);
  }
  await page.goto(url);
  for (const kind of ['simulation']) {
    await loaded(kind, ready.initial[kind].resultId);
    check(requests.includes(`${origin}/api/v1/${kind}-results/latest`), `${kind} requests latest through the Vite origin`);
    check((await meta(kind).textContent()).includes(ready.initial[kind].publishedAt), `${kind} displays publication time`);
  }
  check(new URL(page.url()).origin === origin, 'Browser remains on Vite origin');
  check(!requests.some(u => /fixture-source|demo-planning-result\.json|demo-simulation-result\.json/.test(u)), 'HTTP success imports no fixtures');
  const inspect = () => page.evaluate(() => window.__mvpAcceptance.inspect());
  check((await page.locator('#ops .list-area').textContent()).includes('No threats detected.'), 'Threats list starts empty in standby');
  check((await page.locator('#standby').textContent()).includes('Standby'), 'Standby bar shows standby');
  check((await page.locator('#comparison-panel').textContent()).includes('No run pair yet'), 'Comparison panel waits for a run pair');
  await page.screenshot({ path: resolve(evidence, 'http-success.png'), fullPage: true });
  if (gate === 'B05') {
    const failures = [
      ['404', { status: 404, json: { error: { code: 'RESULT_NOT_FOUND', message: 'No published snapshot' } } }, 'No published snapshot'],
      ['503', { status: 503, json: { error: { code: 'DELIVERY_UNAVAILABLE', message: 'Temporary storage failure' } } }, 'Temporary storage failure'],
      ['network', null, 'Network request failed'],
      ['invalid-json', { status: 200, contentType: 'application/json', body: '{' }, 'invalid JSON'],
      ['malformed', { status: 200, json: { result: {} } }, 'resultId'],
      ['wrong-kind', { status: 200, json: { resultId: 'x', publishedAt: '2026-09-26T00:00:00Z', result: { schemaVersion: 'planning-result/1' } } }, 'unsupported simulation result schema'],
    ];
    for (const kind of ['simulation']) {
      for (const [name, originalResponse, originalReason] of failures) {
        const handler = route => originalResponse ? route.fulfill(originalResponse) : route.abort('failed');
        await page.route(`**/api/v1/${kind}-results/latest`, handler);
        await page.goto(url);
        await until(async () => (await page.locator(`.result-load-status[aria-label="${'Simulation'} result loading"]`).textContent()).includes(originalReason), `visible ${kind} ${name} reason`);
        check(!requests.some(u => /fixture-source|demo-planning-result\.json|demo-simulation-result\.json/.test(u)), `${kind} ${name} does not load fixtures`);
        check((await page.locator('#standby').textContent()).includes('No simulation result loaded'), `${kind} ${name} draws no fabricated result`);
        await page.screenshot({ path: resolve(evidence, `failure-${kind}-${name}.png`), fullPage: true });
        await page.unroute(`**/api/v1/${kind}-results/latest`, handler);
      }
    }
    await page.goto(url);
    await loaded('simulation', ready.initial.simulation.resultId);
    await page.screenshot({ path: resolve(evidence, 'http-recovered.png'), fullPage: true });
    await page.goto(url + '&source=fixture');
    await loaded('simulation', ready.initial.simulation.resultId);
    check(!requests.some(u => /fixture-source|demo-simulation-result\.json/.test(u)), 'A source=fixture query is ignored: there is no fixture mode');
  }
  if (gate === 'B06') {
    await until(async () => (await inspect()).canvas.layers.filter(l => l.kind === 'circles').every(l => l.ready), 'Actual circle geometry ready');
    const baseline = (await inspect()).canvas;
    for (const kind of ['simulation']) {
      const previous = ready.initial[kind];
      const newer = await publish(kind);
      await delay(200);
      check((await meta(kind).getAttribute('data-result-id')) === previous.resultId, `${kind}: publication does not silently replace the snapshot`);
      await page.getByRole('button', { name: `Refresh ${kind}`, exact: true }).click();
      await loaded(kind, newer.resultId);
      for (const failure of ['fetch', 'validation']) {
        const handler = route => failure === 'fetch' ? route.abort('failed') : route.fulfill({ status: 200, json: { resultId: 'invalid' } });
        await page.route(`**/api/v1/${kind}-results/latest`, handler);
        await page.getByRole('button', { name: `Refresh ${kind}`, exact: true }).click();
        await until(async () => (await page.locator(`.result-load-status[aria-label="${'Simulation'} result loading"]`).textContent()).includes('Unavailable'), `${kind} ${failure} failure`);
        check((await meta(kind).getAttribute('data-result-id')) === newer.resultId, `${kind}: ${failure} failure preserves identity`);
        check((await inspect())[kind].resultId === newer.resultId, `${kind}: ${failure} failure preserves actual payload`);
        await page.unroute(`**/api/v1/${kind}-results/latest`, handler);
      }
      for (let i = 0; i < 10; i++) {
        const next = await publish(kind);
        await page.getByRole('button', { name: `Refresh ${kind}`, exact: true }).click();
        await loaded(kind, next.resultId);
      }
      await until(async () => (await inspect()).canvas.layers.filter(l => l.kind === 'circles').every(l => l.ready), 'Refreshed circle geometry ready');
      const after = (await inspect()).canvas;
      check(after.layerCount === baseline.layerCount && after.primitiveCount === baseline.primitiveCount, `${kind}: ten refreshes preserve actual live layer and primitive counts`);
      check(after.preRenderListeners === baseline.preRenderListeners && after.eventListeners === baseline.eventListeners, `${kind}: ten refreshes preserve listener counts`);
    }
    // A failed construction must preserve the actual shared Cesium clock, not merely leave the old result ID on screen.
    await page.locator('body').press('Space'); // Naive preset: replays the loaded result alone
    const oldClock = await page.evaluate(() => {
      const canvas = window.__canvas;
      const start = new Date(window.__mvpAcceptance.inspect().simulation.result.start);
      canvas.time.seek(new Date(start.getTime() + 5000));
      const original = canvas.addGroundCircles;
      window.__restoreCircleFactory = () => { canvas.addGroundCircles = original; delete window.__restoreCircleFactory; };
      canvas.addGroundCircles = () => { throw new Error('Injected refresh construction failure'); };
      return { time: canvas.time.current.getTime(), playing: canvas.time.playing, resultId: window.__mvpAcceptance.inspect().simulation.resultId };
    });
    try {
      await page.getByRole('button', { name: 'Refresh simulation', exact: true }).click();
      await until(async () => (await page.locator('.result-load-status').textContent()).includes('Injected refresh construction failure'), 'Failed live simulation construction');
      const retained = await page.evaluate(() => ({ time: window.__canvas.time.current.getTime(),
        playing: window.__canvas.time.playing, resultId: window.__mvpAcceptance.inspect().simulation.resultId }));
      check(oldClock.playing && retained.playing && retained.time >= oldClock.time, 'Failed simulation construction preserves real clock progress and playback');
      check(retained.resultId === oldClock.resultId, 'Failed live construction keeps the preceding snapshot');
    } finally { await page.evaluate(() => window.__restoreCircleFactory()); }
    const runRequests = [];
    page.on('request', request => { if (request.url().includes('/api/v1/runs')) runRequests.push(request); });
    await page.evaluate(() => {
      const snapshot = window.__mvpAcceptance.inspect().simulation;
      window.__canvas.time.pause();
      window.__canvas.time.seek(new Date(new Date(snapshot.result.start).getTime() + 30000));
    });
    await until(async () => (await page.locator('#ops .threats li').count()) > 0, 'Threats appear once the clock passes their detection');
    await delay(100);
    check(runRequests.length === 0, 'Space with the Naive preset submits no backend job');
    // Use real view modules and the real canvas for late-settlement/disposal races.
    const lifecycle = await page.evaluate(async () => {
      const { mountSimulationResult } = await import('/src/demo/simulation.ts');
      const canvas = window.__canvas;
      const initial = window.__mvpAcceptance.inspect();
      const results = [];
      for (const kind of ['simulation']) {
        const host = document.createElement('div'); document.body.append(host);
        const snapshot = initial[kind];
        let release;
        const load = () => new Promise(resolve => { release = resolve; });
        const mounted = mountSimulationResult(canvas, host, load);
        mounted.dispose();
        release(snapshot);
        await new Promise(r => setTimeout(r, 20));
        host.remove();
        results.push(canvas.inspect().layerCount === initial.canvas.layerCount);
      }
      return results;
    });
    check(lifecycle.every(Boolean), 'Disposed late responses create no real canvas layers');
    const diagnostics = await inspect();
    check(diagnostics.canvas.renderErrors.length === 0 && diagnostics.canvas.postRenderCount > 0 && diagnostics.canvas.webgl, 'Real Cesium rendered without render errors during refresh');
    await page.screenshot({ path: resolve(evidence, 'refresh-success.png'), fullPage: true });
  }
  if (gate === 'B08') {
    const submissions = [], polls = [], inFlight = new Set(), completedRuns = new Map();
    let maximumPolls = 0;
    page.on('request', request => {
      if (request.method() === 'POST' && request.url().endsWith('/api/v1/runs')) submissions.push(request.postDataJSON());
      if (request.method() === 'GET' && request.url().includes('/api/v1/runs/')) {
        polls.push({ url: request.url(), at: Date.now() }); inFlight.add(request); maximumPolls = Math.max(maximumPolls, inFlight.size);
      }
    });
    page.on('requestfinished', request => inFlight.delete(request));
    page.on('requestfailed', request => inFlight.delete(request));
    const raced = new Map();
    const race = async route => {
      const response = await route.fetch();
      const record = await response.json();
      if (record.status === 'succeeded') completedRuns.set(record.runId, record);
      if (record.status === 'succeeded' && !raced.has(record.resultKind)) {
        const another = await publish(record.resultKind);
        raced.set(record.resultKind, { record, another });
      }
      await route.fulfill({ response });
    };
    await page.route('**/api/v1/runs/*', race);
    const baselineCount = (await inspect()).canvas.layerCount;
    for (const kind of ['simulation']) {
      if (kind === 'simulation') {
        await page.getByLabel('Legacy seed', { exact: true }).check();
        await page.getByRole('spinbutton', { name: 'Simulation seed' }).fill('17');
      }
      const control = page.locator(`.run-controls[data-kind="${kind}"]`);
      const before = submissions.length;
      await page.getByRole('button', { name: `Run ${kind}`, exact: true }).evaluate(button => { button.click(); button.click(); });
      check(await page.getByRole('button', { name: `Run ${kind}`, exact: true }).isDisabled(), `${kind}: duplicate clicks disabled while pending`);
      check(/Submitting|queued|running/.test(await control.textContent()), `${kind}: pending status visible`);
      await until(async () => (await control.getAttribute('data-status')) === 'succeeded', `${kind} real run succeeds`, 60000);
      const { record, another } = raced.get(kind);
      await loaded(kind, record.resultId);
      check(record.resultId !== another.resultId, `${kind}: competing publication has a different identity`);
      check((await inspect())[kind].resultId === record.resultId, `${kind}: displays exact job publication despite newer latest`);
      check(submissions.length === before + 1, `${kind}: one submission per double click`);
      assert.deepEqual(submissions[before], { kind, seed: 17 });
      assertions.push(`${kind}: submitted intended request`);
      check(requests.includes(`${origin}/api/v1/${kind}-results/${record.resultId}`), `${kind}: fetches exact job result URL`);
      if (kind === 'simulation') check((await inspect()).simulation.result.seed === 17, 'Displayed simulation seed matches submitted seed');
      await page.screenshot({ path: resolve(evidence, `run-${kind}-success.png`), fullPage: true });
    }
    const manifest = await page.evaluate(async () => {
      const response = await fetch('/api/v1/scenario-manifest');
      if (!response.ok) throw new Error(`Manifest HTTP ${response.status}`);
      return response.json();
    });
    const frozenEntries = ['validation', 'held-out', 'stress', 'ood-geography', 'ood-cadence', 'assignment-reference']
      .map(split => manifest.entries.find(row => row.split === split));
    check(frozenEntries.every(Boolean), 'Manifest contains a representative from every frozen split');
    const simulationControl = page.locator('.run-controls[data-kind="simulation"]');
    const simulationButton = page.getByRole('button', { name: 'Run simulation', exact: true });
    await page.getByLabel('Frozen scenario', { exact: true }).check();
    const splitControl = page.getByRole('combobox', { name: 'Scenario split' });
    const scenarioControl = page.getByRole('combobox', { name: 'Scenario reference', exact: true });
    const policyControl = page.getByRole('combobox', { name: 'Simulation policy' });
    await splitControl.selectOption('');
    await until(async () => (await scenarioControl.locator('option').count()) === manifest.entries.length,
      'Frozen manifest options loaded into the controls');
    await policyControl.selectOption('naive-launch-on-detection/1');
    let simulationLayerBase, simulationListeners, eightThreatPayload;
    const assertSimulationGeometry = async payload => {
      const expectedIds = [
        ...payload.selectedFootprints.map(row => row.id),
        ...payload.terminalCounterfactualFootprints.filter(row =>
          payload.outcomes.some(outcome => outcome.threatId === row.threatId && outcome.outcome === 'unhandled')).map(row => row.id),
      ].sort();
      await until(async () => {
        const canvas = (await inspect()).canvas;
        return canvas.layers.some(layer => layer.kind === 'circles' && layer.ready
          && JSON.stringify(layer.circles.map(row => row.id).sort()) === JSON.stringify(expectedIds));
      }, 'Simulation footprint geometry ready');
      const canvas = (await inspect()).canvas;
      const paths = canvas.layers.filter(layer => layer.kind === 'path' && layer.positions.length === 20);
      check(paths.length === payload.trajectories.length,
        `${payload.trajectories.length}-threat result creates the exact Cesium path count`);
      const footprintLayer = canvas.layers.find(layer => layer.kind === 'circles'
        && JSON.stringify(layer.circles.map(row => row.id).sort()) === JSON.stringify(expectedIds));
      check(footprintLayer?.circles.length === expectedIds.length,
        `${payload.trajectories.length}-threat result creates the exact footprint count`);
      const base = canvas.layerCount - paths.length - 2;
      const replayPreRenderBase = canvas.preRenderListeners - paths.length * 2;
      if (simulationLayerBase === undefined) {
        simulationLayerBase = base;
        simulationListeners = { pre: replayPreRenderBase, events: canvas.eventListeners };
      } else {
        check(base === simulationLayerBase, 'Switching scenarios disposes preceding Cesium layers');
        check(replayPreRenderBase === simulationListeners.pre && canvas.eventListeners === simulationListeners.events,
          `Switching scenarios preserves normalized Cesium listener counts (${replayPreRenderBase}/${canvas.eventListeners} vs ${simulationListeners.pre}/${simulationListeners.events})`);
      }
    };
    const frozenSubmissionStart = submissions.length;
    for (const [index, entry] of frozenEntries.entries()) {
      await splitControl.selectOption(entry.split);
      await scenarioControl.selectOption(entry.scenarioRef);
      await until(async () => !(await simulationButton.isDisabled()), `Frozen ${entry.split} selection ready`);
      if (index === 0) raced.delete('simulation');
      if (index === 0) {
        await simulationButton.evaluate(button => { button.click(); button.click(); });
      } else await simulationButton.click();
      await until(async () => (await simulationControl.getAttribute('data-status')) === 'succeeded',
        `${entry.split} frozen run succeeds`, 120000);
      const runId = await simulationControl.getAttribute('data-run-id');
      const record = completedRuns.get(runId);
      check(Boolean(record?.resultId), `${entry.split}: terminal job exposes an exact result identity`);
      await loaded('simulation', record.resultId);
      const expectedBody = { kind: 'simulation', scenarioRef: entry.scenarioRef,
        policy: 'naive-launch-on-detection/1' };
      assert.deepEqual(submissions[frozenSubmissionStart + index], expectedBody);
      assertions.push(`${entry.split}: submitted the exact frozen request body`);
      if (index === 0) {
        const competitor = raced.get('simulation');
        check(record.resultId !== competitor.another.resultId
          && (await inspect()).simulation.resultId === record.resultId,
        'Frozen run displays its exact result despite a newer latest publication');
        check(submissions.length === frozenSubmissionStart + 1,
          'Duplicate frozen-run clicks submit only once');
      }
      const displayed = (await inspect()).simulation.result;
      check(displayed.seed === entry.seed && displayed.provenance.split === entry.split
        && displayed.provenance.profile === entry.profile
        && displayed.provenance.canonicalEpisodeHash === entry.canonicalEpisodeHash
        && displayed.policy.identity === 'naive-launch-on-detection/1',
      `${entry.split}: displayed seed, profile, split, hash, and policy match the manifest`);
      const identity = await page.locator('.result-metadata[data-kind="simulation"]').textContent();
      check(identity.includes(record.resultId), `${entry.split}: the loaded result identity is visible in the drawer`);
      const envelope = await page.evaluate(async resultId => {
        const response = await fetch(`/api/v1/simulation-results/${encodeURIComponent(resultId)}`);
        return response.json();
      }, record.resultId);
      await assertSimulationGeometry(envelope.result);
      if (envelope.result.trajectories.length === 8) eightThreatPayload = envelope.result;
    }
    check(Boolean(eightThreatPayload), 'Frozen representatives include a real eight-threat result');
    const warmupPayload = JSON.parse(readFileSync(resolve(inputs, 'warmup.json'), 'utf8'));
    check(warmupPayload.trajectories.length === 2, 'Warmup browser fixture is a real two-threat result');
    const warmupPublication = await publish('simulation', warmupPayload);
    await page.getByRole('button', { name: 'Refresh simulation', exact: true }).click();
    await loaded('simulation', warmupPublication.resultId);
    await assertSimulationGeometry(warmupPayload);
    const failedPayload = structuredClone(eightThreatPayload);
    const unhandled = failedPayload.outcomes.at(-1);
    failedPayload.assignments = failedPayload.assignments.filter(row => row.threat_id !== unhandled.threatId);
    failedPayload.selectedFootprints = failedPayload.selectedFootprints.filter(row => row.threatId !== unhandled.threatId);
    Object.assign(unhandled, { outcome: 'unhandled', interceptorId: null, opportunityId: null });
    const failureReason = 'constraint_violation:browser_acceptance_fixture';
    Object.assign(failedPayload.policyComparison.active, { completed: false, terminationReason: failureReason });
    Object.assign(failedPayload.policyComparison.naive, { completed: false, terminationReason: failureReason });
    failedPayload.policyComparison.exactRegret = null;
    Object.assign(failedPayload.termination, { reason: failureReason, completed: false,
      constraintStatus: 'violated', constraintViolation: 'browser_acceptance_fixture' });
    const failurePublication = await publish('simulation', failedPayload);
    await page.getByRole('button', { name: 'Refresh simulation', exact: true }).click();
    await loaded('simulation', failurePublication.resultId);
    await assertSimulationGeometry(failedPayload);
    await page.locator('body').press('Space');
    await page.evaluate(() => { window.__canvas.time.pause(); window.__canvas.time.seek(new Date(window.__mvpAcceptance.inspect().simulation.result.end)); });
    const unhandledRow = page.locator('#ops .threats li[data-state="unhandled"] .status');
    await until(async () => (await unhandledRow.count()) === 1, 'The unhandled threat is listed');
    check((await unhandledRow.evaluate(element => getComputedStyle(element).color)) === 'rgb(248, 81, 73)', 'An unhandled threat is visibly distinguished in red from intercepted threats');
    await page.screenshot({ path: resolve(evidence, 'frozen-scenarios-and-unhandled.png'), fullPage: true });
    const beforeBadReference = (await inspect()).simulation.resultId;
    const badReferenceStatus = await page.evaluate(async () => (await fetch('/api/v1/runs', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind: 'simulation', scenarioRef: '../../suites.json',
        policy: 'naive-launch-on-detection/1' }),
    })).status);
    check(badReferenceStatus === 400 && (await inspect()).simulation.resultId === beforeBadReference,
      'A bad scenario reference is rejected and preserves the preceding snapshot');
    check((await inspect()).canvas.layerCount === baselineCount, 'Run completion leaves no duplicate layers');
    check(maximumPolls === 1, 'Run polls never overlap');
    for (let i = 1; i < polls.length; i++) {
      if (polls[i].url === polls[i-1].url) check(polls[i].at - polls[i-1].at >= 950, 'Status polling waits one second between requests');
    }
    const finishedPolls = polls.length;
    await delay(1250);
    check(polls.length === finishedPolls, 'Polling stops after terminal results');
    for (const kind of ['simulation']) {
      const preceding = (await inspect())[kind].resultId;
      raced.delete(kind);
      const failedIds = [];
      const failExactOnce = route => {
        const identity = new URL(route.request().url()).pathname.split('/').at(-1);
        if (identity !== 'latest' && failedIds.length === 0) {
          failedIds.push(identity);
          return route.abort('failed');
        }
        return route.continue();
      };
      await page.route(`**/api/v1/${kind}-results/*`, failExactOnce);
      try {
        await page.getByRole('button', { name: `Run ${kind}`, exact: true }).click();
        await until(async () => (await page.locator(`.run-controls[data-kind="${kind}"]`).getAttribute('data-status')) === 'succeeded', `${kind} succeeds before display failure`, 60000);
        const status = page.locator(`.result-load-status[aria-label="${'Simulation'} result loading"]`);
        await until(async () => (await status.textContent()).includes('Unavailable'), `${kind} exact result fails to load`);
        const { record, another } = raced.get(kind);
        check((await inspect())[kind].resultId === preceding, `${kind}: failed exact result fetch retains preceding view`);
        check(failedIds[0] === record.resultId && record.resultId !== another.resultId, `${kind}: failed fetch belongs to job despite a competing latest`);
        const beforeRetry = submissions.length;
        await status.getByRole('button', { name: 'Retry', exact: true }).click();
        await loaded(kind, record.resultId);
        check(submissions.length === beforeRetry, `${kind}: display Retry does not submit another run`);
        check((await inspect())[kind].resultId !== another.resultId, `${kind}: Retry loads the job exact ID rather than competing latest`);
        await page.getByRole('button', { name: `Refresh ${kind}`, exact: true }).click();
        await loaded(kind, another.resultId);
        check((await inspect())[kind].resultId === another.resultId, `${kind}: explicit Refresh still selects latest`);
      } finally { await page.unroute(`**/api/v1/${kind}-results/*`, failExactOnce); }
    }
    await page.unroute('**/api/v1/runs/*', race);
    // Space submits a Naive and an optimised run on the drawer's scenario, then compares them.
    await page.getByLabel('Frozen scenario', { exact: true }).check();
    await splitControl.selectOption('validation');
    await scenarioControl.selectOption('sg2:validation:000000');
    await policyControl.selectOption('optimal-fixed-rank-assignment/1');
    const pairStart = submissions.length;
    await page.locator('body').press('Space');
    await until(async () => (await page.locator('#standby').getAttribute('data-phase')) === 'live', 'Run pair loads and the replay starts', 240000);
    assert.deepEqual(submissions.slice(pairStart), [
      { kind: 'simulation', scenarioRef: 'sg2:validation:000000', policy: 'naive-launch-on-detection/1' },
      { kind: 'simulation', scenarioRef: 'sg2:validation:000000', policy: 'optimal-fixed-rank-assignment/1' },
    ]);
    assertions.push('Space submitted exactly a Naive and an optimised run');
    const comparison = await page.locator('#comparison-panel').textContent();
    check(comparison.includes('Live runs · sg2:validation:000000') && comparison.includes('Ordinal objective cost'), 'Comparison panel shows the live pair');
    check(!/Illustrative|Bundled|Synthetic/.test(comparison), 'Comparison panel carries no synthetic or bundled figures');
    check((await page.locator('#ops .history-view .entry').count()) === 1, 'History lists the run pair');
    await page.screenshot({ path: resolve(evidence, 'run-pair-comparison.png'), fullPage: true });
    // Dispose while a real status HTTP response is held in transit.
    let held;
    const hold = async route => { const response = await route.fetch(); held = { route, response }; };
    await page.route('**/api/v1/runs/*', hold);
    await page.evaluate(async () => {
      const { mountRunControls } = await import('/src/demo/run-controls.ts');
      const host = document.createElement('div'); host.id = 'disposal-run'; document.body.append(host);
      window.__lateRunDisplays = 0;
      const view = mountRunControls(host, 'simulation', async () => { ++window.__lateRunDisplays; });
      window.__disposeTestRun = () => { view.dispose(); host.remove(); };
      host.querySelector('input[value="legacy"]').click();
      [...host.querySelectorAll('button')].find(button => button.textContent === 'Run simulation').click();
    });
    await until(() => held, 'A status response in flight');
    await page.evaluate(() => window.__disposeTestRun());
    const countAtDisposal = polls.length;
    await held.route.fulfill({ response: held.response }).catch(() => {});
    await page.unroute('**/api/v1/runs/*', hold);
    await delay(1250);
    check(polls.length === countAtDisposal && await page.evaluate(() => window.__lateRunDisplays === 0), 'Disposal stops polling and ignores an in-flight response');
    check((await page.locator('#disposal-run').count()) === 0, 'Disposed run controls remove their DOM');
  }
  if (gate === 'B09') {
    await until(async () => (await inspect()).canvas.layers.filter(l => l.kind === 'circles').every(l => l.ready), 'Real Cesium circles become ready');
    const start = await inspect();
    check(start.canvas.webgl && start.canvas.postRenderCount > 0, 'Actual WebGL context completes Cesium postRender events');
    const simPaths = d => d.canvas.layers.filter(l => l.kind === 'path' && l.positions.length === 20);
    const simCircles = d => d.canvas.layers.find(l => l.kind === 'circles' && l.circles.some(c => c.id === ready.initial.simulation.result.selectedFootprints[0].id));
    check(simPaths(start).length === 8 && simPaths(start).every(p => !p.visible), 'Eight actual simulation paths start hidden in standby');
    const shown = start;
    const allCircles = shown.canvas.layers.filter(l => l.kind === 'circles').flatMap(l => l.circles);
    const expected = [...ready.initial.simulation.result.selectedFootprints];
    for (const footprint of expected) {
      const actual = allCircles.find(c => c.id === footprint.id);
      check(actual && Math.abs(actual.lon - footprint.center.lon) <= 1e-7
        && Math.abs(actual.lat - footprint.center.lat) <= 1e-7
        && Math.abs(actual.radiusM - footprint.radiusM) <= 1e-6
        && Math.abs(actual.minorRadiusM - footprint.radiusM) <= 1e-6, `Actual circle ${footprint.id} matches served center/radius`);
    }
    await page.screenshot({ path: resolve(evidence, 'simulation-success.png'), fullPage: true });
    const evidencePayload = structuredClone(ready.initial.simulation.result);
    delete evidencePayload.consequenceSummary.physicalComponents.people_potentially_exposed_total;
    evidencePayload.consequenceSummary.physicalComponents.expected_casualties_central_total = 0;
    const evidenceResult = await publish('simulation', evidencePayload);
    await page.getByRole('button', { name: 'Refresh simulation', exact: true }).click();
    await loaded('simulation', evidenceResult.resultId);
    check((await inspect()).simulation.result.consequenceSummary.physicalComponents.people_potentially_exposed_total === undefined, 'Missing evidence stays missing in the served payload');
    const validIds = { simulation: evidenceResult.resultId };
    await command('stop-http');
    for (const kind of ['simulation']) {
      await page.getByRole('button', { name: `Refresh ${kind}`, exact: true }).click();
      await until(async () => (await page.locator(`.result-load-status[aria-label="${'Simulation'} result loading"]`).textContent()).includes('Unavailable'), `${kind} sees actual API loss`);
      check((await inspect())[kind].resultId === validIds[kind], `${kind} preserves snapshot during API loss`);
    }
    await page.screenshot({ path: resolve(evidence, 'api-loss.png'), fullPage: true });
    await command('start-http');
    for (const kind of ['simulation']) {
      const status = page.locator(`.result-load-status[aria-label="${'Simulation'} result loading"]`);
      await status.getByRole('button', { name: 'Retry', exact: true }).click();
      await until(() => status.isHidden(), `${kind} retries after API recovery`);
    }
    await page.screenshot({ path: resolve(evidence, 'api-recovered.png'), fullPage: true });
    await page.getByLabel('Legacy seed', { exact: true }).check();
    await page.getByRole('spinbutton', { name: 'Simulation seed' }).fill('7');
    await page.getByRole('button', { name: 'Run simulation', exact: true }).click();
    await until(async () => (await page.locator('.run-controls[data-kind="simulation"]').getAttribute('data-status')) === 'succeeded', 'Real run completion', 60000);
    await until(async () => (await inspect()).simulation.resultId !== evidenceResult.resultId, 'Run result loaded');
    await until(async () => (await inspect()).canvas.layers.filter(l => l.kind === 'circles').every(l => l.ready), 'Final result geometry ready');
    const final = await inspect();
    check(final.canvas.layerCount === start.canvas.layerCount && final.canvas.primitiveCount === start.canvas.primitiveCount, 'Refresh and run completion leave no duplicate Cesium layers/primitives');
    check(final.canvas.renderErrors.length === 0, 'No Cesium render-error events across core scenario');
    check(external.length === 0, 'Core scenario needs no external network requests (external traffic blocked)');
    writeFileSync(resolve(evidence, 'cesium-observations.json'), JSON.stringify({ start, shown, final, tolerances: { degrees: 1e-7, radiusM: 1e-6 } }, null, 2));
  }
  check(errors.length === 0, `No uncaught browser exceptions: ${errors.join('; ')}`);
  writeFileSync(resolve(evidence, 'browser-results.json'), JSON.stringify({ gate, status: 'passed', assertions, errors, external, browser: browser.version() }, null, 2));
  console.log(JSON.stringify({ gate, status: 'passed', assertions: assertions.length, browser: browser.version() }));
} catch (error) {
  await page?.screenshot({ path: resolve(evidence, 'failure.png'), fullPage: true }).catch(() => {});
  writeFileSync(resolve(evidence, 'browser-results.json'), JSON.stringify({ gate, status: 'failed', assertions, error: String(error.stack ?? error) }, null, 2));
  console.error(error);
  process.exitCode = 1;
} finally {
  await context?.tracing.stop({ path: resolve(evidence, 'trace.zip') }).catch(() => {});
  await cleanup();
}
