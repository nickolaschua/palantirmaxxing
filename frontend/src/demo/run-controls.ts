import { resultSource } from "./source.js";
import type { ResultKind } from "./delivery.ts";
import { filterScenarioEntries, parseScenarioManifest, POLICIES, POLICY_LABELS, POLICY_NOTES, PROFILES, SPLITS } from "./scenario-manifest-model.js";
import type { FrozenPolicy, FrozenProfile, FrozenSplit, ScenarioManifest } from "./scenario-manifest-model.js";

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

const option = (value: string, label = value): HTMLOptionElement => {
  const row = document.createElement("option"); row.value = value; row.textContent = label; return row;
};
const labelled = (caption: string, control: HTMLElement): HTMLLabelElement => {
  const row = document.createElement("label"); row.append(document.createTextNode(caption + " "), control); return row;
};

export function mountRunControls(parent: HTMLElement, kind: ResultKind, display: (identity: string) => Promise<unknown>) {
  const root = document.createElement("section");
  root.className = "run-controls"; root.dataset.kind = kind;
  const runButton = document.createElement("button");
  runButton.type = "button"; runButton.textContent = `Run ${kind}`;
  const message = document.createElement("p");
  message.className = "run-status"; message.setAttribute("role", "status");
  const retry = document.createElement("button");
  retry.type = "button"; retry.textContent = "Retry run status"; retry.hidden = true;
  let seed: HTMLInputElement | undefined;
  let legacyMode: HTMLInputElement | undefined, frozenMode: HTMLInputElement | undefined;
  let frozen: HTMLElement | undefined, split: HTMLSelectElement | undefined, profile: HTMLSelectElement | undefined;
  let search: HTMLInputElement | undefined, scenario: HTMLSelectElement | undefined, policy: HTMLSelectElement | undefined;
  let selection: HTMLParagraphElement | undefined;
  let manifest: ScenarioManifest | undefined;
  if (kind === "simulation") {
    const mode = document.createElement("div"); mode.className = "run-mode";
    legacyMode = document.createElement("input"); legacyMode.type = "radio"; legacyMode.name = "simulation-run-mode";
    legacyMode.value = "legacy"; legacyMode.checked = true;
    frozenMode = document.createElement("input"); frozenMode.type = "radio"; frozenMode.name = "simulation-run-mode";
    frozenMode.value = "frozen";
    mode.append(labelled("Legacy seed", legacyMode), labelled("Frozen scenario", frozenMode));
    seed = document.createElement("input");
    seed.type = "number"; seed.min = "0"; seed.max = "2147483647"; seed.step = "1"; seed.value = "7";
    seed.setAttribute("aria-label", "Simulation seed");
    const seedRow = labelled("Simulation seed", seed); seedRow.className = "legacy-seed-controls";
    frozen = document.createElement("section"); frozen.className = "frozen-scenario-controls"; frozen.hidden = true;
    split = document.createElement("select"); split.setAttribute("aria-label", "Scenario split");
    split.append(option("", "All splits"), ...[...SPLITS].map(value => option(value)));
    profile = document.createElement("select"); profile.setAttribute("aria-label", "Scenario profile");
    profile.append(option("", "All profiles"), ...[...PROFILES].map(value => option(value)));
    search = document.createElement("input"); search.type = "search"; search.placeholder = "sg2:…";
    search.setAttribute("aria-label", "Scenario reference search");
    scenario = document.createElement("select"); scenario.setAttribute("aria-label", "Scenario reference");
    scenario.append(option("", "Loading checked manifest…"));
    policy = document.createElement("select"); policy.setAttribute("aria-label", "Simulation policy");
    policy.append(...POLICIES.map(value => option(value, POLICY_LABELS[value])));
    selection = document.createElement("p"); selection.className = "scenario-selection";
    frozen.append(labelled("Split", split), labelled("Profile", profile), labelled("Reference search", search),
      labelled("Scenario", scenario), labelled("Policy", policy), selection);
    root.append(mode, seedRow, frozen);
  }
  root.append(runButton, message, retry); parent.append(root);
  let disposed = false, active = false, polling = false, permanentlyDisabled = false;
  let runId: string | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let abort = new AbortController();
  const manifestAbort = new AbortController();
  const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);
  const frozenSelected = () => frozenMode?.checked === true;
  const selectedEntry = () => manifest?.entries.find(row => row.scenarioRef === scenario?.value);
  const refreshDisabled = () => {
    runButton.disabled = permanentlyDisabled || active || (frozenSelected() && !selectedEntry());
    if (seed) seed.disabled = permanentlyDisabled || active || frozenSelected();
    for (const control of [legacyMode, frozenMode, split, profile, search, scenario, policy]) {
      if (control) control.disabled = permanentlyDisabled || active || ((control === split || control === profile || control === search || control === scenario || control === policy) && !frozenSelected());
    }
  };
  const setActive = (value: boolean) => { active = value; refreshDisabled(); };
  const refreshSelection = () => {
    if (!scenario || !selection) return;
    const rows = filterScenarioEntries(manifest?.entries ?? [], {
      split: split?.value as FrozenSplit | "", profile: profile?.value as FrozenProfile | "", query: search?.value,
    });
    const preceding = scenario.value;
    scenario.replaceChildren(...rows.map(row => option(row.scenarioRef, `${row.scenarioRef} · ${row.profile} · seed ${row.seed}`)));
    if (rows.some(row => row.scenarioRef === preceding)) scenario.value = preceding;
    const entry = selectedEntry();
    const policyNote = policy && POLICIES.includes(policy.value as FrozenPolicy)
      ? POLICY_NOTES[policy.value as FrozenPolicy] : "";
    selection.textContent = entry ? `${entry.split} · ${entry.profile} · seed ${entry.seed} · ${entry.canonicalEpisodeHash} · ${policyNote}`
      : rows.length ? "Select a frozen scenario." : "No references match these filters.";
    refreshDisabled();
  };
  const refreshMode = () => {
    const isFrozen = frozenSelected(); root.dataset.mode = isFrozen ? "frozen" : "legacy";
    const legacy = root.querySelector<HTMLElement>(".legacy-seed-controls"); if (legacy) legacy.hidden = isFrozen;
    if (frozen) frozen.hidden = !isFrozen;
    refreshSelection(); refreshDisabled();
  };

  async function request(path: string, options?: RequestInit): Promise<unknown> {
    const response = await fetch(path, { ...options, cache: "no-store", signal: abort.signal });
    let value: unknown;
    try { value = await response.json(); } catch { throw new Error(`HTTP ${response.status}: invalid run JSON`); }
    if (!response.ok) {
      const error = (value as { error?: { code?: string; message?: string } })?.error;
      throw new Error(`HTTP ${response.status}${error?.code ? ` · ${error.code}` : ""}: ${error?.message ?? "Run request failed"}`);
    }
    return value;
  }

  async function update(record: Run): Promise<void> {
    if (disposed) return;
    runId = record.runId; root.dataset.runId = runId; root.dataset.status = record.status;
    message.textContent = `${record.status} · ${runId}`;
    if (record.status === "succeeded") {
      message.textContent += ` · Result ${record.resultId}`;
      await display(record.resultId!);
      if (!disposed) setActive(false);
    } else if (record.status === "failed") {
      message.textContent += ` · ${record.error!.code}: ${record.error!.message}`; setActive(false);
    } else timer = setTimeout(() => { void poll(); }, 1000);
  }

  async function poll(): Promise<void> {
    if (disposed || !runId || polling || !active) return;
    polling = true; retry.hidden = true;
    try {
      const value = await request(`/api/v1/runs/${encodeURIComponent(runId)}`);
      if (!disposed) await update(parseRun(value, kind, runId));
    } catch (error) {
      if (!disposed) { message.textContent = `Run status unavailable · ${runId}: ${errorText(error)}`; retry.hidden = false; }
    } finally { polling = false; }
  }

  runButton.onclick = async () => {
    if (disposed || active) return;
    const number = seed ? Number(seed.value) : undefined;
    if (seed && !frozenSelected() && (!seed.value.trim() || !Number.isInteger(number) || number! < 0 || number! > 2147483647)) {
      message.textContent = "Seed must be an integer from 0 through 2147483647."; return;
    }
    const entry = selectedEntry();
    if (frozenSelected() && (!entry || !policy || !POLICIES.includes(policy.value as FrozenPolicy))) {
      message.textContent = "Select a checked scenario reference and supported policy."; return;
    }
    setActive(true); retry.hidden = true; runId = undefined;
    message.textContent = "Submitting…"; root.dataset.status = "submitting"; abort = new AbortController();
    const body = kind === "planning" ? { kind } : frozenSelected()
      ? { kind, scenarioRef: entry!.scenarioRef, policy: policy!.value as FrozenPolicy }
      : { kind, seed: number };
    try {
      const value = await request("/api/v1/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!disposed) await update(parseRun(value, kind));
    } catch (error) {
      if (!disposed) { message.textContent = `Run failed: ${errorText(error)}`; root.dataset.status = "failed"; setActive(false); }
    }
  };
  retry.onclick = () => { void poll(); };
  if (legacyMode && frozenMode) { legacyMode.onchange = refreshMode; frozenMode.onchange = refreshMode; }
  for (const control of [split, profile, search, scenario, policy]) if (control) control.onchange = refreshSelection;
  try {
    if (resultSource() === "fixture") {
      permanentlyDisabled = true; message.textContent = "Fixture mode · backend runs disabled"; refreshDisabled();
    } else if (kind === "simulation") {
      void (async () => {
        try {
          const response = await fetch("/api/v1/scenario-manifest", { cache: "no-store", signal: manifestAbort.signal });
          const value: unknown = await response.json();
          if (!response.ok) throw new Error(`HTTP ${response.status}: scenario manifest request failed`);
          const checked = parseScenarioManifest(value);
          if (disposed) return;
          manifest = checked; refreshSelection();
        } catch (error) {
          if (!disposed && !manifestAbort.signal.aborted) {
            if (scenario) scenario.replaceChildren(option("", "Checked manifest unavailable"));
            if (selection) selection.textContent = `Frozen scenarios unavailable: ${errorText(error)}`;
            refreshDisabled();
          }
        }
      })();
    }
  } catch (error) { permanentlyDisabled = true; message.textContent = errorText(error); refreshDisabled(); }
  refreshMode();
  return {
    dispose() {
      if (disposed) return;
      disposed = true; clearTimeout(timer); abort.abort(); manifestAbort.abort();
      runButton.onclick = retry.onclick = null;
      if (legacyMode) legacyMode.onchange = null; if (frozenMode) frozenMode.onchange = null;
      for (const control of [split, profile, search, scenario, policy]) if (control) control.onchange = null;
      root.remove();
    },
  };
}
