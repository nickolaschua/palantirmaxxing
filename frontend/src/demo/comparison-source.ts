import { parseComparisonResult } from "./comparison-contract.js";
import type { MultiThreatComparisonResult } from "./comparison-contract.js";
import { DEMO_COMPARISON_RESULT } from "./comparison-data.js";

export interface LoadedComparison {
  result: MultiThreatComparisonResult;
  sourceLabel: string;
  usingFallback: boolean;
}

/**
 * Load order:
 * 1. `?comparisonResult=/path/result.json` for a one-off run;
 * 2. `VITE_COMPARISON_RESULT_URL` for a deployed backend endpoint;
 * 3. the bundled fixture for an offline demo.
 */
export async function loadComparisonResult(): Promise<LoadedComparison> {
  const queryUrl = new URLSearchParams(window.location.search).get("comparisonResult")?.trim();
  const environmentUrl = import.meta.env.VITE_COMPARISON_RESULT_URL?.trim();
  const url = queryUrl || environmentUrl;
  if (!url) {
    return { result: parseComparisonResult(DEMO_COMPARISON_RESULT), sourceLabel: "Bundled demonstration fixture", usingFallback: true };
  }
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`Comparison result request failed with HTTP ${response.status}`);
  const result = parseComparisonResult(await response.json());
  return { result, sourceLabel: url, usingFallback: false };
}
