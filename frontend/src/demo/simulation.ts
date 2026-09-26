import type { CircleLayer, MarkerLayer, PathLayer, SingaporeCanvas } from "../lib/index.js";
import { loadSimulationResult } from "./source.js";
import type { ResultLoader } from "./source.js";
import { mountResultLoader } from "./result-loader.js";
import { parseSimulationResult } from "./simulation-model.js";
import { ResultResources } from "./result-resources.js";
import type { Snapshot } from "./source.js";
import { mountRunControls } from "./run-controls.js";
import { framePose } from "./decision-model.js";
import { POLICY_NAMES } from "./engagement-model.js";

export interface SimulationView { dispose(): void }

const COLOURS = ["#ff6b6b", "#ffd166", "#06d6a0", "#4cc9f0", "#7b61ff", "#f72585", "#90be6d", "#f8961e"];
const REPLAY_SPEED = 12;

const metric = (label: string, value: string, note: string): HTMLElement => {
  const card = document.createElement("div");
  const heading = document.createElement("span"); heading.textContent = label;
  const strong = document.createElement("strong"); strong.textContent = value;
  const small = document.createElement("small"); small.textContent = note;
  card.append(heading, strong, small);
  return card;
};

const clockText = (seconds: number): string => {
  const rounded = Math.max(0, Math.round(seconds));
  return `${String(Math.floor(rounded / 60)).padStart(2, "0")}:${String(rounded % 60).padStart(2, "0")}`;
};

function renderSimulationResult(canvas: SingaporeCanvas, panel: HTMLElement, result: ReturnType<typeof parseSimulationResult>, resources: ResultResources): SimulationView {
  const details = resources.node(document.createElement("details"));
  details.id = "simulation-result";
  const summary = document.createElement("summary");
  const v2 = result.schemaVersion === "simulation-result/2" ? result : undefined;
  details.open = Boolean(v2);
  if (v2) details.dataset.policy = v2.policy.identity;
  summary.textContent = v2
    ? `Live ${POLICY_NAMES[v2.policy.identity] ?? v2.policy.identity} · cost ${v2.policyComparison.active.ordinalCost.toFixed(3)} · ${result.trajectories.length} threats · ${v2.provenance.split} · ${v2.provenance.profile}`
    : `Simulation result · ${result.trajectories.length} threats · baseline`;
  details.append(summary);
  let paths: PathLayer[] = [], circles: CircleLayer | undefined, markers: MarkerLayer | undefined;
  const component = result.consequenceSummary.physicalComponents;
  const people = component.people_potentially_exposed_total;
  const casualties = component.expected_casualties_central_total;
  const copy = document.createElement("p");
  const intercepted = v2 ? v2.outcomes.filter(row => row.outcome === "intercepted").length : result.assignments.length;
  const unhandled = v2 ? v2.outcomes.length - intercepted : 0;
  copy.textContent = `${result.trajectories.length} trajectories · ${intercepted} intercepted${v2 ? ` · ${unhandled} unhandled` : ""} · ${people === undefined ? "Unavailable" : people.toLocaleString()} people potentially exposed · ${casualties === undefined ? "Unavailable" : casualties.toLocaleString()} assumption-grade expected casualties.`;
  const claim = document.createElement("p");
  let live: HTMLParagraphElement | undefined;
  let impact: HTMLElement | undefined;
  if (v2) {
    live = document.createElement("p"); live.className = "live-result-banner";
    const active = v2.policyComparison.active;
    const naive = v2.policyComparison.naive;
    const exact = v2.policyComparison.exactReference;
    const activeScope = active.informationScope === "online-detected-only"
      ? "online, detected threats only"
      : active.informationScope === "online-observation-only"
        ? "online, observation only; experimental/unpromoted"
        : "offline full episode, clairvoyant";
    live.textContent = `VISIBLE POLICY REPLAY · ${POLICY_NAMES[active.policyIdentity] ?? active.policyIdentity} · ${activeScope}`;
    claim.textContent = `Active ${active.policyIdentity} (${activeScope}) cost ${active.ordinalCost.toFixed(3)} · `
      + `naive ${naive.policyIdentity} (online, detected threats only) cost ${naive.ordinalCost.toFixed(3)} · `
      + `exact reference ${exact.policyIdentity} (offline full episode, clairvoyant) cost ${exact.ordinalCost.toFixed(3)} · `
      + `exact regret ${v2.policyComparison.exactRegret === null ? "Unavailable" : v2.policyComparison.exactRegret.toFixed(3)}.`;
    const improvement = naive.ordinalCost === 0 ? 0 : ((naive.ordinalCost - active.ordinalCost) / naive.ordinalCost) * 100;
    impact = document.createElement("section"); impact.className = "live-impact-grid";
    impact.setAttribute("aria-label", "Live policy impact");
    impact.append(
      metric("Active cost", active.ordinalCost.toFixed(3), "lower is better"),
      metric("vs Naive", Math.abs(improvement) < 0.05 ? "Reference" : `${Math.abs(improvement).toFixed(1)}% ${improvement > 0 ? "lower" : "higher"}`,
        `Naive ${naive.ordinalCost.toFixed(3)}`),
      metric("Exact regret", v2.policyComparison.exactRegret === null ? "N/A" : v2.policyComparison.exactRegret.toFixed(3),
        `Exact ${exact.ordinalCost.toFixed(3)}`),
      metric("Outcome", `${intercepted}/${v2.outcomes.length}`, unhandled ? `${unhandled} unhandled` : "all intercepted"),
    );
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
    details.append(live!, impact!, badges, identities, outcomes);
  }
  const replayState = document.createElement("p"); replayState.className = "simulation-replay-state";
  const progress = document.createElement("progress"); progress.className = "simulation-replay-progress";
  const replayActions = document.createElement("div"); replayActions.className = "simulation-replay-actions";
  const replayButton = document.createElement("button"); replayButton.type = "button"; replayButton.textContent = `Replay visible run · ${REPLAY_SPEED}×`;
  const pauseButton = document.createElement("button"); pauseButton.type = "button"; pauseButton.textContent = "Pause replay";
  const toggle = document.createElement("button"); toggle.type = "button";
  let visible = Boolean(v2);
  paths = result.trajectories.map((trajectory, index) => {
    const outcome = v2?.outcomes.find(row => row.threatId === trajectory.threatId)?.outcome;
    const colour = outcome === "unhandled" ? "#ff3b30" : COLOURS[index];
    return canvas.addPath(
    trajectory.samples.map(sample => ({
      lon: sample.position.lon, lat: sample.position.lat, height: sample.position.heightM,
      time: new Date(sample.time),
    })), { color: colour, trailColor: "rgba(207, 217, 230, 0.3)", width: outcome === "unhandled" ? 5 : 3,
      markerSize: outcome === "unhandled" ? 18 : 14, markerShape: "craft", markerPulse: true });
  });
  const unhandledFootprints = v2 ? v2.terminalCounterfactualFootprints.filter(row =>
    v2.outcomes.some(outcome => outcome.threatId === row.threatId && outcome.outcome === "unhandled")) : [];
  const displayedFootprints = [...result.selectedFootprints, ...unhandledFootprints];
  circles = canvas.addGroundCircles(displayedFootprints.map(row => ({
    id: row.id, center: { lon: row.center.lon, lat: row.center.lat }, radiusM: row.radiusM,
  })));
  markers = canvas.addMarkers(displayedFootprints.map(row => ({ id: row.id, position: row.center })));
  if (v2) circles.setStyles(new Map(displayedFootprints.map(row => [row.id, row.kind === "selected"
    ? { fill: "rgba(6, 214, 160, 0.35)", outline: "#06d6a0", visible: true }
    : { fill: "rgba(255, 59, 48, 0.40)", outline: "#ff3b30", visible: true }])));
  markers.setStyles(new Map(displayedFootprints.map(row => [row.id, {
    color: row.kind === "selected" ? "#06d6a0" : "#ff3b30",
    size: row.kind === "selected" ? 12 : 16,
    visible: true,
    label: `${row.kind === "selected" ? "Intercept" : "Unhandled"} · ${row.threatId}`,
  }])));
  const setVisible = (next: boolean): void => {
    visible = next;
    for (const path of paths) path.setVisible(visible);
    circles?.setVisible(visible);
    markers?.setVisible(visible);
    toggle.textContent = visible ? "Hide simulation" : "Show simulation";
  };
  setVisible(visible);
  toggle.addEventListener("click", () => {
    setVisible(!visible);
  });
  const replayStart = new Date(result.start);
  const replayStop = new Date(result.end);
  const durationS = Math.max(0.001, (replayStop.getTime() - replayStart.getTime()) / 1000);
  progress.max = durationS;
  const updateReplayState = (now: Date): void => {
    const elapsedS = Math.max(0, Math.min(durationS, (now.getTime() - replayStart.getTime()) / 1000));
    progress.value = elapsedS;
    const complete = elapsedS >= durationS - 0.05;
    details.dataset.replay = complete ? "complete" : canvas.time.playing ? "playing" : "paused";
    replayState.textContent = `${complete ? "REPLAY COMPLETE" : canvas.time.playing ? `PLAYING ${REPLAY_SPEED}×` : "REPLAY PAUSED"} · T+${clockText(elapsedS)} / ${clockText(durationS)}`;
  };
  const replay = (): void => {
    setVisible(true);
    canvas.time.setRange(replayStart, replayStop);
    canvas.time.seek(replayStart);
    canvas.time.play(REPLAY_SPEED);
    updateReplayState(replayStart);
    const points = result.trajectories.flatMap(trajectory => trajectory.samples.map(sample => ({
      lon: sample.position.lon, lat: sample.position.lat, height: sample.position.heightM,
    })));
    canvas.camera.flyTo(framePose(points, -72, innerWidth / innerHeight, 1.12), { duration: 0.8 }).catch(() => undefined);
  };
  replayButton.onclick = replay;
  pauseButton.onclick = () => { canvas.time.pause(); updateReplayState(canvas.time.current); };
  resources.use(canvas.on("clockTick", updateReplayState));
  replayActions.append(replayButton, pauseButton, toggle);
  const caveat = document.createElement("small");
  caveat.textContent = "Every circle is a supplied 100 m area, not a validated blast radius.";
  if (v2) impact!.after(replayState, progress, replayActions);
  else details.append(replayState, progress, replayActions);
  details.append(copy, claim, caveat);
  (v2 ? document.body : panel).append(details);
  if (v2) replay();
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
