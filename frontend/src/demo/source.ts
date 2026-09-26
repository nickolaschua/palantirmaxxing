import { unwrapDelivery, parseDeliveryFailure } from "./delivery.ts";
import type { ResultKind } from "./delivery.ts";

/** A published result as the backend served it. There is no other source. */
export interface Snapshot {
  source: "http";
  result: unknown;
  resultId: string;
  publishedAt: string;
}
export type ResultLoader = (identity?: string, signal?: AbortSignal) => Promise<unknown>;

export async function loadResult(kind: ResultKind, identity = "latest", signal?: AbortSignal): Promise<Snapshot> {
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
  return { source: "http", result, resultId: envelope.resultId, publishedAt: envelope.publishedAt };
}

export const loadPlanningResult: ResultLoader = (identity, signal) => loadResult("planning", identity, signal);
export const loadSimulationResult: ResultLoader = (identity, signal) => loadResult("simulation", identity, signal);

export function isSnapshot(value: unknown): value is Snapshot {
  return typeof value === "object" && value !== null && (value as Snapshot).source === "http"
    && "result" in value && typeof (value as Snapshot).resultId === "string";
}
