import { parseResult } from "./decision-model.ts";
import { parseSimulationResult } from "./simulation-model.ts";

export type ResultKind = "planning" | "simulation";
const record = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const nonempty = (v: unknown): v is string => typeof v === "string" && v.trim().length > 0;

function utc(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(value)) return false;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 19) === value.slice(0, 19);
}

/** Pure adapter only: no fetch, URL, fixture enrichment, or payload mutation. */
export function unwrapDelivery(kind: ResultKind, value: unknown): unknown {
  if (!record(value) || !nonempty(value.resultId)) throw new Error("Missing delivery resultId");
  if (!utc(value.publishedAt)) throw new Error("Invalid UTC publishedAt");
  if (!record(value.result)) throw new Error("Missing result object");
  if (kind === "planning") parseResult(value.result);
  else parseSimulationResult(value.result);
  return value.result;
}

export function parseDeliveryFailure(status: number, value: unknown): { code: string; message: string } {
  if (![404, 503, 500].includes(status)) throw new Error("Unsupported failure status");
  if (!record(value) || !record(value.error) || !nonempty(value.error.code) || !nonempty(value.error.message)) {
    throw new Error("Invalid delivery error");
  }
  return { code: value.error.code, message: value.error.message };
}
