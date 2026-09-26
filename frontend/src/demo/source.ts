import { unwrapDelivery, parseDeliveryFailure } from "./delivery.ts";
import type { ResultKind } from "./delivery.ts";

export interface Snapshot {
  source: "http" | "fixture";
  result: unknown;
  resultId: string | null;
  publishedAt: string | null;
}
export type ResultLoader = (identity?: string, signal?: AbortSignal) => Promise<unknown>;

export function resultSource(): "http" | "fixture" {
  const source = new URLSearchParams(location.search).get("source") ?? import.meta.env?.VITE_RESULT_SOURCE ?? "http";
  if (source !== "http" && source !== "fixture") throw new Error(`Unsupported result source: ${source}`);
  return source;
}

export async function loadResult(kind: ResultKind, identity = "latest", signal?: AbortSignal): Promise<Snapshot> {
  const source = resultSource();
  if (source === "fixture") {
    const fixtures = await import("./fixture-source.js");
    const result = await (kind === "planning" ? fixtures.loadPlanningResult() : fixtures.loadSimulationResult());
    return { source, result, resultId: null, publishedAt: null };
  }
  let response: Response;
  try {
    response = await fetch(`/api/v1/${kind}-results/${encodeURIComponent(identity)}`, { cache: "no-store", signal });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new Error(`Network request failed: ${error instanceof Error ? error.message : String(error)}`);
  }
  let body: unknown;
  try { body = await response.json(); }
  catch { throw new Error(`HTTP ${response.status}: invalid JSON response`); }
  if (!response.ok) {
    const reason = parseDeliveryFailure(response.status, body);
    throw new Error(`HTTP ${response.status} · ${reason.code}: ${reason.message}`);
  }
  const result = unwrapDelivery(kind, body);
  const envelope = body as { resultId: string; publishedAt: string };
  if (identity !== "latest" && envelope.resultId !== identity) throw new Error("Response identity does not match requested snapshot");
  return { source, result, resultId: envelope.resultId, publishedAt: envelope.publishedAt };
}

export const loadPlanningResult: ResultLoader = (identity, signal) => loadResult("planning", identity, signal);
export const loadSimulationResult: ResultLoader = (identity, signal) => loadResult("simulation", identity, signal);

export function isSnapshot(value: unknown): value is Snapshot {
  return typeof value === "object" && value !== null && "source" in value
    && ((value as Snapshot).source === "http" || (value as Snapshot).source === "fixture") && "result" in value;
}
