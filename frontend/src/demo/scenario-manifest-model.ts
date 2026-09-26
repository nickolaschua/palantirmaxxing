export type FrozenSplit = "validation" | "held-out" | "stress" | "ood-geography" | "ood-cadence" | "assignment-reference";
export type FrozenProfile = "warmup" | "balanced" | "full-standard" | "burst-contention" | "low-slack" | "consequence-contrast" | "geographic-shift" | "cadence-shift";
export type FrozenPolicy = "naive-launch-on-detection/1" | "feasible-immediate-matching/1"
  | "optimal-fixed-rank-assignment/1" | "structured-behavior-cloning/1";
export interface ScenarioManifestEntry {
  scenarioRef: string; split: FrozenSplit; index: number; seed: number;
  profile: FrozenProfile; canonicalEpisodeHash: string;
}
export interface ScenarioManifest {
  schemaVersion: "rl-scenario-suites/5";
  generatorVersion: "singapore-scenario/2";
  distributionVersion: "singapore-scenario-distribution/1";
  distributionChecksum: string;
  providerIdentity: "singapore-demo-v2";
  entries: readonly ScenarioManifestEntry[];
}

export const SPLITS = new Set<FrozenSplit>(["validation", "held-out", "stress", "ood-geography", "ood-cadence", "assignment-reference"]);
export const PROFILES = new Set<FrozenProfile>(["warmup", "balanced", "full-standard", "burst-contention", "low-slack", "consequence-contrast", "geographic-shift", "cadence-shift"]);
export const POLICIES: readonly FrozenPolicy[] = ["naive-launch-on-detection/1", "structured-behavior-cloning/1", "optimal-fixed-rank-assignment/1", "feasible-immediate-matching/1"];
export const DEMO_SCENARIO_REF = "sg2:validation:000000";
export const DEMO_POLICIES: readonly FrozenPolicy[] = [
  "naive-launch-on-detection/1",
  "optimal-fixed-rank-assignment/1",
  "structured-behavior-cloning/1",
];
export const POLICY_LABELS: Readonly<Record<FrozenPolicy, string>> = {
  "naive-launch-on-detection/1": "Naive online · safe fallback",
  "structured-behavior-cloning/1": "Structured imitation · experimental",
  "optimal-fixed-rank-assignment/1": "Exact fixed-rank · offline reference",
  "feasible-immediate-matching/1": "Feasible matching · offline comparator",
};
export const POLICY_NOTES: Readonly<Record<FrozenPolicy, string>> = {
  "naive-launch-on-detection/1": "Online rule using only detected threats.",
  "structured-behavior-cloning/1": "Online observation-only checkpoint; experimental and not promoted because validation still contained constraint violations.",
  "optimal-fixed-rank-assignment/1": "Clairvoyant offline optimum within the immutable additive fixed-rank proof scope.",
  "feasible-immediate-matching/1": "Offline full-episode matching comparator.",
};
const HASH = /^sha256:[0-9a-f]{64}$/;
const REFERENCE = /^sg2:(validation|held-out|stress|ood-geography|ood-cadence|assignment-reference):[0-9]{6}$/;
const record = (value: unknown, name: string): Record<string, unknown> => {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error(`${name} must be an object`);
  return value as Record<string, unknown>;
};
const nonempty = (value: unknown, name: string): string => {
  if (typeof value !== "string" || !value.trim()) throw new Error(`${name} must be a nonempty string`);
  return value;
};

export function parseScenarioManifest(value: unknown): ScenarioManifest {
  const root = record(value, "scenario manifest");
  if (root.schemaVersion !== "rl-scenario-suites/5" || root.generatorVersion !== "singapore-scenario/2"
      || root.distributionVersion !== "singapore-scenario-distribution/1" || root.providerIdentity !== "singapore-demo-v2"
      || typeof root.distributionChecksum !== "string" || !HASH.test(root.distributionChecksum)) {
    throw new Error("unsupported scenario manifest identity");
  }
  if (!Array.isArray(root.entries)) throw new Error("scenario manifest entries must be an array");
  const entries = root.entries.map((value, index): ScenarioManifestEntry => {
    const row = record(value, `entries[${index}]`);
    const scenarioRef = nonempty(row.scenarioRef, "scenarioRef");
    const split = nonempty(row.split, "split") as FrozenSplit;
    const profile = nonempty(row.profile, "profile") as FrozenProfile;
    const hash = nonempty(row.canonicalEpisodeHash, "canonicalEpisodeHash");
    if (!REFERENCE.test(scenarioRef) || !SPLITS.has(split) || !PROFILES.has(profile)
        || !scenarioRef.startsWith(`sg2:${split}:`) || !HASH.test(hash)
        || !Number.isInteger(row.index) || (row.index as number) < 0
        || !Number.isInteger(row.seed) || (row.seed as number) < 0 || (row.seed as number) > 2147483647) {
      throw new Error(`entries[${index}] has invalid scenario metadata`);
    }
    return { scenarioRef, split, index: row.index as number, seed: row.seed as number,
      profile, canonicalEpisodeHash: hash };
  });
  if (new Set(entries.map(row => row.scenarioRef)).size !== entries.length
      || new Set(entries.map(row => row.canonicalEpisodeHash)).size !== entries.length) {
    throw new Error("scenario manifest contains duplicate identities");
  }
  return { schemaVersion: "rl-scenario-suites/5", generatorVersion: "singapore-scenario/2",
    distributionVersion: "singapore-scenario-distribution/1", distributionChecksum: root.distributionChecksum,
    providerIdentity: "singapore-demo-v2", entries };
}

export function filterScenarioEntries(entries: readonly ScenarioManifestEntry[], options: {
  split?: FrozenSplit | ""; profile?: FrozenProfile | ""; query?: string;
} = {}): readonly ScenarioManifestEntry[] {
  const query = (options.query ?? "").trim().toLocaleLowerCase();
  return entries.filter(row => (!options.split || row.split === options.split)
    && (!options.profile || row.profile === options.profile)
    && (!query || row.scenarioRef.toLocaleLowerCase().includes(query)))
    .sort((a, b) => a.scenarioRef.localeCompare(b.scenarioRef));
}
