import type { CircleLayer, PathLayer, SingaporeCanvas } from "../lib/index.js";
import resultJson from "../../../data/results/demo-simulation-result.json";
import { parseSimulationResult } from "./simulation-model.js";

export interface SimulationView { dispose(): void }

const COLOURS = ["#ff6b6b", "#ffd166", "#06d6a0", "#4cc9f0", "#7b61ff", "#f72585", "#90be6d", "#f8961e"];

export function mountSimulationResult(canvas: SingaporeCanvas, panel: HTMLElement): SimulationView {
  const details = document.createElement("details");
  details.id = "simulation-result";
  const summary = document.createElement("summary");
  summary.textContent = "8-threat simulation baseline";
  details.append(summary);
  let paths: PathLayer[] = [], circles: CircleLayer | undefined;
  try {
    const result = parseSimulationResult(resultJson);
    const component = result.consequenceSummary.physicalComponents;
    const people = component.people_potentially_exposed_total ?? 0;
    const casualties = component.expected_casualties_central_total ?? 0;
    const copy = document.createElement("p");
    copy.textContent = `${result.trajectories.length} trajectories · ${result.assignments.length} interceptions · ${people.toLocaleString()} people potentially exposed · ${casualties.toLocaleString()} assumption-grade expected casualties.`;
    const claim = document.createElement("p");
    claim.textContent = result.policyVersusBaseline.claim;
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.textContent = "Show simulation";
    let visible = false;
    paths = result.trajectories.map((trajectory, index) => canvas.addPath(
      trajectory.samples.map(sample => ({
        lon: sample.position.lon, lat: sample.position.lat, height: sample.position.heightM,
        time: new Date(sample.time),
      })), { color: COLOURS[index], trailColor: COLOURS[index], width: 2, markerSize: 0 },
    ));
    circles = canvas.addGroundCircles(result.selectedFootprints.map(row => ({
      id: row.id, center: { lon: row.center.lon, lat: row.center.lat }, radiusM: row.radiusM,
    })));
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
  } catch (error) {
    const message = document.createElement("p");
    message.textContent = `Simulation result unavailable: ${error instanceof Error ? error.message : String(error)}`;
    details.append(message);
  }
  panel.append(details);
  return { dispose() { for (const path of paths) path.destroy(); circles?.destroy(); details.remove(); } };
}
