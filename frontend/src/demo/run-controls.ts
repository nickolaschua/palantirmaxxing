import { resultSource } from "./source.js";
import type { ResultKind } from "./delivery.ts";

type Run = { runId: string; status: "queued" | "running" | "succeeded" | "failed";
  resultKind?: ResultKind; resultId?: string; error?: { code: string; message: string } };
function parseRun(value: unknown, kind: ResultKind, identity?: string): Run {
  const row = value as Run;
  if (!row || typeof row.runId !== "string" || !row.runId || (identity && identity !== row.runId)
      || !["queued", "running", "succeeded", "failed"].includes(row.status)) throw new Error("Malformed run response");
  if (row.status === "succeeded" && (row.resultKind !== kind || typeof row.resultId !== "string" || !row.resultId)) throw new Error("Malformed run result identity");
  if (row.status === "failed" && (!row.error || typeof row.error.code !== "string" || !row.error.code
      || typeof row.error.message !== "string" || !row.error.message)) throw new Error("Malformed run failure");
  return row;
}

export function mountRunControls(parent: HTMLElement, kind: ResultKind, display: (identity: string) => Promise<unknown>) {
  const root = document.createElement("section");
  root.className = "run-controls";
  root.dataset.kind = kind;
  const runButton = document.createElement("button");
  runButton.type = "button";
  runButton.textContent = `Run ${kind}`;
  const message = document.createElement("p");
  message.className = "run-status";
  message.setAttribute("role", "status");
  const retry = document.createElement("button");
  retry.type = "button"; retry.textContent = "Retry run status"; retry.hidden = true;
  let seed: HTMLInputElement | undefined;
  if (kind === "simulation") {
    const label = document.createElement("label"); label.textContent = "Simulation seed ";
    seed = document.createElement("input");
    seed.type = "number"; seed.min = "0"; seed.max = "2147483647"; seed.step = "1"; seed.value = "7";
    seed.setAttribute("aria-label", "Simulation seed");
    label.append(seed); root.append(label);
  }
  root.append(runButton, message, retry); parent.append(root);
  let disposed = false, active = false, polling = false;
  let runId: string | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let abort = new AbortController();
  const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);
  const setActive = (value: boolean) => { active = value; runButton.disabled = value; if (seed) seed.disabled = value; };

  async function request(path: string, options?: RequestInit): Promise<unknown> {
    const response = await fetch(path, { ...options, cache: "no-store", signal: abort.signal });
    let value: unknown;
    try { value = await response.json(); } catch { throw new Error(`HTTP ${response.status}: invalid run JSON`); }
    if (!response.ok) {
      const error = (value as { error?: { message?: string } })?.error;
      throw new Error(`HTTP ${response.status}: ${error?.message ?? "Run request failed"}`);
    }
    return value;
  }

  async function update(record: Run): Promise<void> {
    if (disposed) return;
    runId = record.runId;
    root.dataset.runId = runId;
    root.dataset.status = record.status;
    message.textContent = `${record.status} · ${runId}`;
    if (record.status === "succeeded") {
      message.textContent += ` · Result ${record.resultId}`;
      await display(record.resultId!);
      if (!disposed) setActive(false);
    } else if (record.status === "failed") {
      message.textContent += ` · ${record.error!.code}: ${record.error!.message}`;
      setActive(false);
    } else {
      timer = setTimeout(() => { void poll(); }, 1000);
    }
  }

  async function poll(): Promise<void> {
    if (disposed || !runId || polling || !active) return;
    polling = true; retry.hidden = true;
    try {
      const value = await request(`/api/v1/runs/${encodeURIComponent(runId)}`);
      if (!disposed) await update(parseRun(value, kind, runId));
    } catch (error) {
      if (!disposed) {
        message.textContent = `Run status unavailable · ${runId}: ${errorText(error)}`;
        retry.hidden = false; // Keep submission disabled until the existing run is resolved.
      }
    } finally { polling = false; }
  }

  runButton.onclick = async () => {
    if (disposed || active) return;
    const number = seed ? Number(seed.value) : undefined;
    if (seed && (!seed.value.trim() || !Number.isInteger(number) || number! < 0 || number! > 2147483647)) {
      message.textContent = "Seed must be an integer from 0 through 2147483647.";
      return;
    }
    setActive(true); retry.hidden = true; runId = undefined;
    message.textContent = "Submitting…"; root.dataset.status = "submitting";
    abort = new AbortController();
    try {
      const value = await request('/api/v1/runs', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(kind === 'planning' ? { kind } : { kind, seed: number }) });
      if (!disposed) await update(parseRun(value, kind));
    } catch (error) {
      if (!disposed) { message.textContent = `Run failed: ${errorText(error)}`; root.dataset.status = "failed"; setActive(false); }
    }
  };
  retry.onclick = () => { void poll(); };
  try {
    if (resultSource() === 'fixture') { runButton.disabled = true; if (seed) seed.disabled = true; message.textContent = 'Fixture mode · backend runs disabled'; }
  } catch (error) { runButton.disabled = true; message.textContent = errorText(error); }
  return {
    dispose() {
      if (disposed) return;
      disposed = true; clearTimeout(timer); abort.abort();
      runButton.onclick = retry.onclick = null;
      root.remove();
    },
  };
}
