import { afterEach, expect, it, vi } from "vitest";
import { awaitRun, parseRun, submitRun } from "../src/demo/runs.js";

const response = (value: unknown, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => value }) as Response;
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

it("parseRun rejects malformed records", () => {
  expect(() => parseRun({ runId: "", status: "queued" }, "simulation")).toThrow("Malformed run response");
  expect(() => parseRun({ runId: "a", status: "succeeded", resultKind: "planning", resultId: "r" }, "simulation")).toThrow("result identity");
  expect(() => parseRun({ runId: "a", status: "failed", error: { code: "", message: "m" } }, "simulation")).toThrow("run failure");
  expect(parseRun({ runId: "a", status: "running" }, "simulation", "a").status).toBe("running");
});

it("submitRun posts the body and surfaces the error envelope", async () => {
  const fetch = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
    expect(JSON.parse(String(init?.body))).toEqual({ kind: "simulation", scenarioRef: "sg2:validation:000000", policy: "naive-launch-on-detection/1" });
    return response({ error: { code: "BAD_REFERENCE", message: "unknown scenario" } }, 400);
  });
  vi.stubGlobal("fetch", fetch);
  await expect(submitRun({ kind: "simulation", scenarioRef: "sg2:validation:000000", policy: "naive-launch-on-detection/1" }, "simulation", new AbortController().signal))
    .rejects.toThrow("HTTP 400 · BAD_REFERENCE: unknown scenario");
});

it("awaitRun polls once a second until terminal and reports each update", async () => {
  vi.useFakeTimers();
  const states = [{ runId: "r1", status: "running" }, { runId: "r1", status: "succeeded", resultKind: "simulation", resultId: "res-1" }];
  const fetch = vi.fn(async () => response(states.shift()));
  vi.stubGlobal("fetch", fetch);
  const seen: string[] = [];
  const done = awaitRun({ runId: "r1", status: "queued" }, "simulation", new AbortController().signal, run => seen.push(run.status));
  await vi.advanceTimersByTimeAsync(999);
  expect(fetch).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(1);
  await vi.advanceTimersByTimeAsync(1000);
  expect((await done).resultId).toBe("res-1");
  expect(seen).toEqual(["running", "succeeded"]);
  expect(fetch).toHaveBeenCalledTimes(2);
});

it("awaitRun rejects when aborted while waiting", async () => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn());
  const abort = new AbortController();
  const done = awaitRun({ runId: "r1", status: "queued" }, "simulation", abort.signal);
  abort.abort();
  await expect(done).rejects.toThrow("Aborted");
});

it("awaitRun survives a transient poll failure and keeps polling", async () => {
  vi.useFakeTimers();
  const replies: (() => Promise<Response>)[] = [
    () => Promise.reject(new TypeError("Failed to fetch")),
    async () => response({ runId: "r1", status: "succeeded", resultKind: "simulation", resultId: "res-1" }),
  ];
  const fetch = vi.fn(() => replies.shift()!());
  vi.stubGlobal("fetch", fetch);
  const done = awaitRun({ runId: "r1", status: "running" }, "simulation", new AbortController().signal);
  await vi.advanceTimersByTimeAsync(1000);
  await vi.advanceTimersByTimeAsync(1000);
  expect((await done).resultId).toBe("res-1");
  expect(fetch).toHaveBeenCalledTimes(2);
});

it("awaitRun gives up on a malformed poll response at once", async () => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn(async () => response({ runId: "other", status: "running" })));
  const done = awaitRun({ runId: "r1", status: "running" }, "simulation", new AbortController().signal);
  const outcome = expect(done).rejects.toThrow("Malformed run response"); // attach the handler before the timer fires
  await vi.advanceTimersByTimeAsync(1000);
  await outcome;
});
