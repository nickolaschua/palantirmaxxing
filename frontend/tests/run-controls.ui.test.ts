import { afterEach, expect, it, vi } from "vitest";
import { mountRunControls } from "../src/demo/run-controls.js";

const hash = (digit: string) => `sha256:${digit.repeat(64)}`;
const splits = ["validation", "held-out", "stress", "ood-geography", "ood-cadence", "assignment-reference"] as const;
const profiles = ["balanced", "full-standard", "burst-contention", "geographic-shift", "cadence-shift", "full-standard"] as const;
const manifest = {
  schemaVersion: "rl-scenario-suites/5", generatorVersion: "singapore-scenario/2",
  distributionVersion: "singapore-scenario-distribution/1", distributionChecksum: hash("0"),
  providerIdentity: "singapore-demo-v2",
  entries: splits.map((split, index) => ({ scenarioRef: `sg2:${split}:000000`, split, index: 0,
    seed: 10000 + index, profile: profiles[index], canonicalEpisodeHash: hash(String(index + 1)) })),
};
const response = (value: unknown, status = 200) => ({ ok: status >= 200 && status < 300, status,
  json: async () => value }) as Response;
const settle = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };

afterEach(() => { vi.unstubAllGlobals(); document.body.replaceChildren(); });

it("submits one exact frozen request per split and renders strings as text", async () => {
  const bodies: unknown[] = [];
  let count = 0;
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/api/v1/scenario-manifest")) return response(manifest);
    if (url.endsWith("/api/v1/runs") && init?.method === "POST") {
      bodies.push(JSON.parse(String(init.body)));
      return response({ runId: `run-${++count}`, status: "failed",
        error: { code: "INJECTED", message: "<img src=x onerror=alert(1)>" } }, 202);
    }
    throw new Error("unexpected request " + url);
  });
  vi.stubGlobal("fetch", fetch);
  const view = mountRunControls(document.body, "simulation", async () => {});
  try {
    await settle();
    const frozen = document.querySelector<HTMLInputElement>('input[value="frozen"]')!;
    frozen.click(); frozen.dispatchEvent(new Event("change"));
    const split = document.querySelector<HTMLSelectElement>('[aria-label="Scenario split"]')!;
    const button = [...document.querySelectorAll<HTMLButtonElement>("button")].find(row => row.textContent === "Run simulation")!;
    for (const value of splits) {
      split.value = value; split.dispatchEvent(new Event("change"));
      button.click(); await settle();
    }
    expect(bodies).toEqual(splits.map((value, index) => ({ kind: "simulation",
      scenarioRef: `sg2:${value}:000000`, policy: "naive-launch-on-detection/1" })));
    expect(document.body.textContent).toContain("<img src=x onerror=alert(1)>");
    expect(document.querySelector("img")).toBeNull();
  } finally { view.dispose(); }
});

it("duplicate frozen-run clicks create only one submission", async () => {
  let resolvePost!: (value: Response) => void;
  const post = new Promise<Response>(resolve => { resolvePost = resolve; });
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).endsWith("/api/v1/scenario-manifest")) return response(manifest);
    if (init?.method === "POST") return post;
    throw new Error("unexpected request");
  });
  vi.stubGlobal("fetch", fetch);
  const view = mountRunControls(document.body, "simulation", async () => {});
  try {
    await settle();
    const frozen = document.querySelector<HTMLInputElement>('input[value="frozen"]')!;
    frozen.click(); frozen.dispatchEvent(new Event("change"));
    const button = [...document.querySelectorAll<HTMLButtonElement>("button")].find(row => row.textContent === "Run simulation")!;
    button.click(); button.click();
    expect(fetch.mock.calls.filter(call => call[1]?.method === "POST")).toHaveLength(1);
    resolvePost(response({ runId: "run-1", status: "failed", error: { code: "STOP", message: "done" } }, 202));
    await settle();
  } finally { view.dispose(); }
});

it("offers and submits every demo policy, including the imitation warning", async () => {
  const bodies: unknown[] = [];
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).endsWith("/api/v1/scenario-manifest")) return response(manifest);
    if (init?.method === "POST") {
      bodies.push(JSON.parse(String(init.body)));
      return response({ runId: `run-${bodies.length}`, status: "failed",
        error: { code: "STOP", message: "done" } }, 202);
    }
    throw new Error("unexpected request");
  });
  vi.stubGlobal("fetch", fetch);
  const view = mountRunControls(document.body, "simulation", async () => {});
  try {
    await settle();
    const frozen = document.querySelector<HTMLInputElement>('input[value="frozen"]')!;
    frozen.click(); frozen.dispatchEvent(new Event("change"));
    const split = document.querySelector<HTMLSelectElement>('[aria-label="Scenario split"]')!;
    split.value = "validation"; split.dispatchEvent(new Event("change"));
    const policy = document.querySelector<HTMLSelectElement>('[aria-label="Simulation policy"]')!;
    const requested = ["naive-launch-on-detection/1", "optimal-fixed-rank-assignment/1",
      "structured-behavior-cloning/1"];
    expect([...policy.options].map(row => row.value)).toEqual(expect.arrayContaining(requested));
    const button = [...document.querySelectorAll<HTMLButtonElement>("button")].find(row => row.textContent === "Run simulation")!;
    for (const value of requested) {
      policy.value = value; policy.dispatchEvent(new Event("change"));
      if (value === "structured-behavior-cloning/1") {
        expect(document.body.textContent).toContain("experimental and not promoted");
      }
      button.click(); await settle();
    }
    expect(bodies).toEqual(requested.map(value => ({ kind: "simulation",
      scenarioRef: "sg2:validation:000000", policy: value })));
  } finally { view.dispose(); }
});

it("runs the numbered golden-scenario sequence with one click per policy", async () => {
  const bodies: unknown[] = [];
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).endsWith("/api/v1/scenario-manifest")) return response(manifest);
    if (init?.method === "POST") {
      bodies.push(JSON.parse(String(init.body)));
      return response({ runId: `demo-${bodies.length}`, status: "failed",
        error: { code: "TEST_COMPLETE", message: "stop after submission" } }, 202);
    }
    throw new Error("unexpected request");
  });
  vi.stubGlobal("fetch", fetch);
  const view = mountRunControls(document.body, "simulation", async () => {});
  try {
    await settle();
    expect(document.querySelector<HTMLElement>('.run-controls')?.dataset.mode).toBe("frozen");
    const buttons = [...document.querySelectorAll<HTMLButtonElement>(".demo-policy-actions button")];
    expect(buttons.map(button => button.textContent)).toEqual(["1 · Naive", "2 · Exact", "3 · Imitation"]);
    for (const button of buttons) { button.click(); await settle(); }
    expect(bodies).toEqual([
      { kind: "simulation", scenarioRef: "sg2:validation:000000", policy: "naive-launch-on-detection/1" },
      { kind: "simulation", scenarioRef: "sg2:validation:000000", policy: "optimal-fixed-rank-assignment/1" },
      { kind: "simulation", scenarioRef: "sg2:validation:000000", policy: "structured-behavior-cloning/1" },
    ]);
  } finally { view.dispose(); }
});
