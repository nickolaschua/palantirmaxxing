import type { CircleLayer, PathLayer, SingaporeCanvas } from "../lib/index.js";
import { loadSimulationResult } from "./source.js";
import type { ResultLoader } from "./source.js";
import { mountResultLoader } from "./result-loader.js";
import { parseSimulationResult } from "./simulation-model.js";
import { ResultResources } from "./result-resources.js";
import type { Snapshot } from "./source.js";
import { mountRunControls } from "./run-controls.js";

export interface SimulationView { dispose(): void }

const COLOURS = ["#ff6b6b", "#ffd166", "#06d6a0", "#4cc9f0", "#7b61ff", "#f72585", "#90be6d", "#f8961e"];

function renderSimulationResult(canvas: SingaporeCanvas, panel: HTMLElement, result: ReturnType<typeof parseSimulationResult>, resources: ResultResources): SimulationView {
  const details = resources.node(document.createElement("details"));
  details.id = "simulation-result";
  const summary = document.createElement("summary");
  const v2 = result.schemaVersion === "simulation-result/2" ? result : undefined;
  summary.textContent = `${result.trajectories.length}-threat simulation${v2 ? ` · ${v2.provenance.split} · ${v2.provenance.profile}` : " baseline"}`;
  details.append(summary);
  let paths: PathLayer[] = [], circles: CircleLayer | undefined;
  const component = result.consequenceSummary.physicalComponents;
  const people = component.people_potentially_exposed_total;
  const casualties = component.expected_casualties_central_total;
  const copy = document.createElement("p");
  const intercepted = v2 ? v2.outcomes.filter(row => row.outcome === "intercepted").length : result.assignments.length;
  const unhandled = v2 ? v2.outcomes.length - intercepted : 0;
  copy.textContent = `${result.trajectories.length} trajectories · ${intercepted} intercepted${v2 ? ` · ${unhandled} unhandled` : ""} · ${people === undefined ? "Unavailable" : people.toLocaleString()} people potentially exposed · ${casualties === undefined ? "Unavailable" : casualties.toLocaleString()} assumption-grade expected casualties.`;
  const claim = document.createElement("p");
  if (v2) {
    const active = v2.policyComparison.active;
    const naive = v2.policyComparison.naive;
    const exact = v2.policyComparison.exactReference;
    const activeScope = active.informationScope === "online-detected-only"
      ? "online, detected threats only"
      : active.informationScope === "online-observation-only"
        ? "online, observation only; experimental/unpromoted"
        : "offline full episode, clairvoyant";
    claim.textContent = `Active ${active.policyIdentity} (${activeScope}) cost ${active.ordinalCost.toFixed(3)} · `
      + `naive ${naive.policyIdentity} (online, detected threats only) cost ${naive.ordinalCost.toFixed(3)} · `
      + `exact reference ${exact.policyIdentity} (offline full episode, clairvoyant) cost ${exact.ordinalCost.toFixed(3)} · `
      + `exact regret ${v2.policyComparison.exactRegret === null ? "Unavailable" : v2.policyComparison.exactRegret.toFixed(3)}.`;
  } else if (result.schemaVersion === "simulation-result/1") {
    claim.textContent = result.policyVersusBaseline.claim;
  }
  if (v2) {
    const badges = document.createElement("p");
    badges.className = "scenario-badges";
    const split = document.createElement("span"); split.textContent = v2.provenance.split;
    const profile = document.createElement("span"); profile.textContent = v2.provenance.profile;
    badges.append(split, profile);
    if (v2.policy.deploymentStatus) {
      const status = document.createElement("span");
      status.textContent = v2.policy.deploymentStatus;
      badges.append(status);
    }
    const identities = document.createElement("p");
    identities.className = "scenario-identities";
    identities.textContent = `Scenario ${v2.provenance.scenarioRef} · seed ${v2.seed} · episode ${v2.episodeId} · generator ${v2.provenance.generatorVersion} · distribution ${v2.provenance.distributionVersion} · provider ${v2.provenance.providerIdentity} · policy ${v2.policy.identity}${v2.policy.artifactIdentity ? ` · artifact ${v2.policy.artifactIdentity}` : ""} · hash ${v2.provenance.hashVerified ? "verified" : "unverified"} ${v2.provenance.canonicalEpisodeHash}`;
    const outcomes = document.createElement("p"); outcomes.className = "simulation-outcome-legend";
    const interceptedLabel = document.createElement("span"); interceptedLabel.className = "simulation-outcome-intercepted";
    interceptedLabel.textContent = `${intercepted} intercepted`;
    const unhandledLabel = document.createElement("span"); unhandledLabel.className = "simulation-outcome-unhandled";
    unhandledLabel.textContent = `${unhandled} unhandled`;
    outcomes.append(interceptedLabel, document.createTextNode(" · "), unhandledLabel);
    details.append(badges, identities, outcomes);
  }
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.textContent = "Show simulation";
  let visible = false;
  paths = result.trajectories.map((trajectory, index) => {
    const outcome = v2?.outcomes.find(row => row.threatId === trajectory.threatId)?.outcome;
    const colour = outcome === "unhandled" ? "#ff3b30" : COLOURS[index];
    return canvas.addPath(
    trajectory.samples.map(sample => ({
      lon: sample.position.lon, lat: sample.position.lat, height: sample.position.heightM,
      time: new Date(sample.time),
    })), { color: colour, trailColor: colour, width: outcome === "unhandled" ? 4 : 2, markerSize: 0 });
  });
  const unhandledFootprints = v2 ? v2.terminalCounterfactualFootprints.filter(row =>
    v2.outcomes.some(outcome => outcome.threatId === row.threatId && outcome.outcome === "unhandled")) : [];
  const displayedFootprints = [...result.selectedFootprints, ...unhandledFootprints];
  circles = canvas.addGroundCircles(displayedFootprints.map(row => ({
    id: row.id, center: { lon: row.center.lon, lat: row.center.lat }, radiusM: row.radiusM,
  })));
  if (v2) circles.setStyles(new Map(displayedFootprints.map(row => [row.id, row.kind === "selected"
    ? { fill: "rgba(6, 214, 160, 0.35)", outline: "#06d6a0", visible: true }
    : { fill: "rgba(255, 59, 48, 0.40)", outline: "#ff3b30", visible: true }])));
  for (const path of paths) path.setVisible(false);
  circles.setVisible(false);
  toggle.addEventListener("click", () => {
    visible = !visible;
    for (const path of paths) path.setVisible(visible);
    circles?.setVisible(visible);
    toggle.textContent = visible ? "Hide simulation" : "Show simulation";
  });
  const caveat = document.createElement("small");
  caveat.textContent = "Every circle is a supplied 100 m area, not a validated blast radius.";
  details.append(copy, claim, toggle, caveat);
  panel.append(details);
  return { dispose() { resources.dispose(); } };
}

export function mountSimulationResult(
  canvas: SingaporeCanvas, panel: HTMLElement, loader: ResultLoader = loadSimulationResult,
): SimulationView & { retry(): void; snapshot(): Snapshot | undefined } {
  const loading = mountResultLoader(panel, "Simulation", loader, parseSimulationResult,
    result => {
      const resources = new ResultResources(canvas);
      try { return renderSimulationResult(resources.canvas, panel, result, resources); }
      catch (error) { resources.dispose(); throw error; }
    });
  const runs = mountRunControls(loading.controls, "simulation", loading.loadIdentity);
  return { retry: loading.retry, snapshot: loading.snapshot, dispose() { runs.dispose(); loading.dispose(); } };
}
