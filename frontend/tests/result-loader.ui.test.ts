import { afterEach, expect, it, vi } from "vitest";
import { mountResultLoader } from "../src/demo/result-loader.js";

const settle = async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); };
const snapshot = (id: string) => ({ source: "http", resultId: id, publishedAt: "2026-09-26T00:00:00Z", result: { id } });
afterEach(() => { document.body.replaceChildren(); });

it.each(["fetch", "parse", "render"])("Retry preserves the exact job result after a %s failure while Refresh selects latest", async mode => {
  let latest = "old", fail = true;
  const check = (stage: string, id: string) => {
    if (fail && stage === mode && id === "job-result") { fail = false; throw new Error("Temporary failure"); }
  };
  const load = vi.fn(async (identity = "latest") => {
    const id = identity === "latest" ? latest : identity;
    check("fetch", id);
    return snapshot(id);
  });
  const disposed: string[] = [];
  const loader = mountResultLoader(document.body, "Planning", load,
    value => { const result = value as { id: string }; check("parse", result.id); return result; },
    result => { check("render", result.id); return { dispose: () => { disposed.push(result.id); } }; });
  try {
    await settle();
    await loader.loadIdentity("job-result");
    expect(loader.snapshot()?.resultId).toBe("old");
    expect(disposed).toEqual([]);
    latest = "competing-result";
    document.querySelector<HTMLButtonElement>(".result-load-status button")!.click();
    await settle();
    expect(load.mock.calls.map(call => call[0] ?? "latest")).toEqual(["latest", "job-result", "job-result"]);
    expect(loader.snapshot()?.resultId).toBe("job-result");
    expect(disposed).toEqual(["old"]);
    document.querySelector<HTMLButtonElement>(".result-metadata > button")!.click();
    await settle();
    expect(loader.snapshot()?.resultId).toBe("competing-result");
    expect(load.mock.calls.at(-1)?.[0]).toBeUndefined();
    expect(disposed).toEqual(["old", "job-result"]);
  } finally { loader.dispose(); }
});

it("a stale failure cannot replace the identity used by Retry", async () => {
  let rejectOld!: (reason: Error) => void;
  let recovered = false;
  const load = vi.fn(async (identity = "latest") => {
    if (identity === "old-job") return new Promise((_resolve, reject) => { rejectOld = reject; });
    if (identity === "new-job" && !recovered) throw new Error("New job result unavailable");
    return snapshot(identity);
  });
  const loader = mountResultLoader(document.body, "Planning", load, value => value, () => ({ dispose() {} }));
  try {
    await settle();
    const old = loader.loadIdentity("old-job");
    await loader.loadIdentity("new-job");
    rejectOld(new Error("Late old failure")); await old;
    recovered = true;
    document.querySelector<HTMLButtonElement>(".result-load-status button")!.click(); await settle();
    expect(load.mock.calls.at(-1)?.[0]).toBe("new-job");
    expect(loader.snapshot()?.resultId).toBe("new-job");
  } finally { loader.dispose(); }
});
