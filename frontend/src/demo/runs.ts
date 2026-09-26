import type { ResultKind } from "./delivery.ts";

export type Run = { runId: string; status: "queued" | "running" | "succeeded" | "failed";
  resultKind?: ResultKind; resultId?: string; error?: { code: string; message: string } };

export function parseRun(value: unknown, kind: ResultKind, identity?: string): Run {
  const row = value as Run;
  if (!row || typeof row.runId !== "string" || !row.runId || (identity && identity !== row.runId)
      || !["queued", "running", "succeeded", "failed"].includes(row.status)) throw new Error("Malformed run response");
  if (row.status === "succeeded" && (row.resultKind !== kind || typeof row.resultId !== "string" || !row.resultId)) throw new Error("Malformed run result identity");
  if (row.status === "failed" && (!row.error || typeof row.error.code !== "string" || !row.error.code
      || typeof row.error.message !== "string" || !row.error.message)) throw new Error("Malformed run failure");
  return row;
}

async function request(path: string, signal: AbortSignal, options?: RequestInit): Promise<unknown> {
  const response = await fetch(path, { ...options, cache: "no-store", signal });
  let value: unknown;
  try { value = await response.json(); } catch { throw new Error(`HTTP ${response.status}: invalid run JSON`); }
  if (!response.ok) {
    const error = (value as { error?: { code?: string; message?: string } })?.error;
    throw new Error(`HTTP ${response.status}${error?.code ? ` · ${error.code}` : ""}: ${error?.message ?? "Run request failed"}`);
  }
  return value;
}

export const submitRun = async (body: object, kind: ResultKind, signal: AbortSignal): Promise<Run> =>
  parseRun(await request("/api/v1/runs", signal, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }), kind);

export const pollRun = async (runId: string, kind: ResultKind, signal: AbortSignal): Promise<Run> =>
  parseRun(await request(`/api/v1/runs/${encodeURIComponent(runId)}`, signal, undefined), kind, runId);

const POLL_MS = 1000;
const POLL_RETRIES = 5; // consecutive transient failures tolerated before the run is reported failed
const wait = (ms: number, signal: AbortSignal): Promise<void> => new Promise((resolve, reject) => {
  if (signal.aborted) { reject(new DOMException("Aborted", "AbortError")); return; }
  const timer = setTimeout(() => { signal.removeEventListener("abort", stop); resolve(); }, ms);
  const stop = () => { clearTimeout(timer); reject(new DOMException("Aborted", "AbortError")); };
  signal.addEventListener("abort", stop, { once: true });
});

/**
 * One poll in flight at a time, one second apart, until the run is terminal. A transient failure (network,
 * 503, bad JSON) is retried a bounded number of times, as the job keeps running on the backend; a malformed
 * record is a contract breach and fails at once.
 */
export async function awaitRun(run: Run, kind: ResultKind, signal: AbortSignal, onUpdate?: (run: Run) => void): Promise<Run> {
  let current = run, failures = 0;
  while (current.status === "queued" || current.status === "running") {
    await wait(POLL_MS, signal);
    try { current = await pollRun(current.runId, kind, signal); failures = 0; }
    catch (error) {
      if (signal.aborted || (error instanceof Error && error.message.startsWith("Malformed")) || ++failures >= POLL_RETRIES) throw error;
      continue;
    }
    onUpdate?.(current);
  }
  return current;
}
