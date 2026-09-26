import { SINGAPORE_BOUNDS } from "../lib/index.js";
import type { BasemapKind, CircleLayer, CircleStyle, LabelLayer, LightingPreset, MarkerLayer, MarkerStyle, PathLayer, SingaporeCanvas } from "../lib/index.js";
import {
  advance, approachOrigin, categoryColour, categoryLabel, circleBounds, comparisonLines, consequenceRows, descentSamples, DESCENT_S, detect,
  elapsedS, exposureGrade, fire, formatNumber, formatPercent, formatT, framePose, isOpen, optionColour, parseResult,
  remainingS, select, shortId, STANDBY, successGrade, threatPositionAt, urgency, wording,
} from "./decision-model.js";
import type { Flow, Grade, Option } from "./decision-model.js";
import { mountInspector } from "./inspector.js";
import { loadPlanningResult } from "./source.js";

export interface Decision {
  setBasemap(kind: BasemapKind): void;
  setLighting(preset: LightingPreset): void;
  dispose(): void;
}

const STANDBY_PITCH = -70;
const BURST_S = 2.2;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (className) e.className = className;
  if (text !== undefined) e.textContent = text;
  return e;
}

const alpha = (hex: string, a: number): string => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
};

const ignoreCancel = (err: unknown): void => {
  if (!(err instanceof Error && err.name === "FlightCancelled")) throw err;
};

/** A struck area once the threat is down: light, so it reads apart from anything still live. */
const markStyle = (o: Option): CircleStyle => ({ fill: alpha(optionColour(o), 0.12), outline: "rgba(255, 255, 255, 0.55)", visible: true });

const exposureText = (o: Option): string =>
  !o.exposure ? "Not evaluated"
  : o.exposure.peoplePotentiallyExposed === null ? "Incomplete (partial coverage)"
  : formatNumber(o.exposure.peoplePotentiallyExposed);
const successText = (o: Option): string =>
  o.suppliedSuccessProbability === undefined ? "Unavailable" : formatPercent(o.suppliedSuccessProbability);
const coverageText = (o: Option): string =>
  !o.exposure ? "Not evaluated"
  : o.exposure.status === "complete" ? "Complete population coverage"
  : o.exposure.coveredAreaFraction === null ? "Partial coverage" : `Partial coverage (${formatPercent(o.exposure.coveredAreaFraction)} of area)`;

/**
 * The engagement decision flow on planning-result/1:
 * Standby → [Space/Play] Live → [FIRE click] Fired → intercept → Outcome;
 * Live → every window closed → Expired; [R/Restart] → Standby from anywhere.
 */
export async function mountDecision(
  canvas: SingaporeCanvas,
  setup: { ionToken?: string; googleApiKey?: string; lighting: LightingPreset },
): Promise<Decision> {
  const tray = el("section");
  tray.id = "decision-tray";
  tray.setAttribute("aria-label", "Engagement decision");
  const phaseEl = el("span", "phase");
  const clockEl = el("span", "clock");
  const head = el("header");
  head.append(phaseEl, clockEl);
  const message = el("p", "message");
  message.setAttribute("role", "status");
  const cardsEl = el("div", "cards");
  const summary = el("ul", "summary");
  tray.className = "decision-tray";
  tray.append(head, message, cardsEl, summary);

  // Presenter controls, bottom right: Play and Restart (temporary) above History.
  const presenter = el("div");
  presenter.id = "presenter";
  const playBtn = el("button", undefined, "Play");
  const restartBtn = el("button", undefined, "Restart");
  const historyBtn = el("button", undefined, "History");
  playBtn.type = restartBtn.type = historyBtn.type = "button";
  const presenterRow = el("div", "row");
  presenterRow.append(playBtn, restartBtn);
  presenter.append(presenterRow, historyBtn);
  // Past threats, each with its mark on the map that can be switched off.
  const historyPanel = el("aside");
  historyPanel.id = "history";
  historyPanel.setAttribute("aria-label", "Past threats");
  const historyEmpty = el("p", "empty", "No past threats yet.");
  const historyList = el("ul");
  historyPanel.append(el("h2", undefined, "History"), historyEmpty, historyList);
  historyBtn.setAttribute("aria-expanded", "false");
  historyBtn.onclick = () => {
    const open = !historyPanel.classList.contains("open");
    // Grow from, and shrink back into, the History button.
    const b = historyBtn.getBoundingClientRect();
    // offsetLeft/Top ignore the panel's own scale, which the origin is measured against.
    historyPanel.style.transformOrigin = `${b.left + b.width / 2 - historyPanel.offsetLeft}px ${b.top + b.height / 2 - historyPanel.offsetTop}px`;
    historyPanel.classList.toggle("open", open);
    historyBtn.setAttribute("aria-expanded", String(open));
  };
  document.body.append(tray, presenter, historyPanel);

  // The result loads and validates here, in Standby, so nothing can fail mid-countdown.
  let parsed: ReturnType<typeof parseResult>;
  try {
    parsed = parseResult(await loadPlanningResult());
  } catch (error) {
    phaseEl.textContent = "UNAVAILABLE";
    message.textContent = `Can't use the planning result: ${error instanceof Error ? error.message : String(error)}`;
    playBtn.disabled = restartBtn.disabled = true;
    return { setBasemap() {}, setLighting() {}, dispose() { tray.remove(); presenter.remove(); historyPanel.remove(); } };
  }
  const { result, options } = parsed;
  const words = wording(result.assumptions);
  const start = new Date(result.start);
  const samples = result.threat.samples.map(({ time, ...position }) => ({ ...position, time: new Date(time) }));
  const optionName = (id: string | null): string => `Option ${options.findIndex(o => o.id === id) + 1}`;
  const exposures = options.flatMap(o => (typeof o.exposure?.peoplePotentiallyExposed === "number" ? [o.exposure.peoplePotentiallyExposed] : []));
  const exposureGradeOf = (o: Option): Grade | null =>
    typeof o.exposure?.peoplePotentiallyExposed === "number" ? exposureGrade(o.exposure.peoplePotentiallyExposed, exposures) : null;
  const successGradeOf = (o: Option): Grade | null => (o.suppliedSuccessProbability === undefined ? null : successGrade(o.suppliedSuccessProbability));

  // --- map layers, hidden until Live ---
  // The clock runs past the supplied end so a fall after the latest intercept has room.
  const endS = (new Date(result.end).getTime() - start.getTime()) / 1000;
  const latestIntercept = Math.max(endS, ...options.map(o => o.timeFromStartS + DESCENT_S + 0.5));
  canvas.time.setRange(start, new Date(start.getTime() + latestIntercept * 1000));
  const path = canvas.addPath(samples, { color: "#f5f7fa", width: 4, trailColor: "rgba(245, 247, 250, 0.5)", markerSize: 35, markerShape: "craft", markerPulse: true });
  // Illustration: the payload has no launch origin, so this is extrapolated from
  // the first two samples and drawn dashed, dim and labelled.
  const origin = approachOrigin(result, SINGAPORE_BOUNDS);
  const first = samples[0];
  let approach: PathLayer | undefined;
  let approachLabel: LabelLayer | undefined;
  if (origin && first) {
    approach = canvas.addPath(
      [{ ...origin, time: new Date(start.getTime() + origin.timeFromStartS * 1000) }, first],
      { color: "rgba(245, 247, 250, 0.65)", width: 3, dashed: true, markerSize: 0 },
    );
    approachLabel = canvas.addLabels(
      [{ position: origin, text: `Illustrative inbound track · not supplied · ${Math.round(-origin.timeFromStartS)} s earlier` }],
    );
  }
  const markers = canvas.addMarkers(options.flatMap(o => [
    { id: o.id, position: o.position },
    ...(o.timeMarginS === null ? [] : [{ id: `${o.id}#closes`, position: threatPositionAt(result, o.timeMarginS).position }]),
  ]));
  let hovered: string | null = null;
  let pinned: string | null = null;
  const circles = canvas.addGroundCircles(
    options.map(o => ({ id: o.id, center: o.position, radiusM: o.footprint.radiusM })),
    // Hover opens the side window, click pins it. Neither selects nor fires.
    { hover(id) { hovered = id; showInspector(); }, click(id) { pinned = id; showInspector(); } },
  );
  // The fall into the chosen area, drawn only once that option is fired.
  let descent: PathLayer | undefined;
  const inspector = mountInspector({
    keys: { ionToken: setup.ionToken, googleApiKey: setup.googleApiKey },
    basemap: canvas.scene.basemap,
    lighting: setup.lighting,
    samples,
    range: [start, new Date(result.end)],
    options,
    onUnpin() { pinned = null; showInspector(); },
  });
  // Everything that belongs to this threat's flight. Once it is down, this goes
  // and only the struck area stays, as a mark of where an intercept has been.
  const setRouteVisible = (visible: boolean): void => {
    path.setVisible(visible);
    approach?.setVisible(visible);
    approachLabel?.setVisible(visible);
    descent?.setVisible(visible);
    inspector.setRouteVisible(visible);
  };
  const setLayersVisible = (visible: boolean): void => {
    setRouteVisible(visible);
    markers.setVisible(visible);
    circles.setVisible(visible);
  };
  setLayersVisible(false);

  // --- history: one entry per run; a struck area's mark stays on the map across restarts ---
  // snapshot: a copy of the tray as it closed, reopened from the history entry.
  interface HistoryEntry { text: string; mark?: { circle: CircleLayer; marker: MarkerLayer }; shown: boolean; snapshot?: HTMLElement }
  const history: HistoryEntry[] = [];
  let recorded = false; // this run already has its entry
  let runMarkReady = false; // this run's history mark is built, so the run's own area can go
  let openSnapshot: HTMLElement | null = null;
  function closeSnapshot(): void {
    if (!openSnapshot) return;
    openSnapshot.remove();
    openSnapshot = null;
    tray.hidden = flow.phase === "outcome"; // the live tray only comes back if it had not closed
    renderHistory();
  }
  function toggleSnapshot(entry: HistoryEntry): void {
    const same = openSnapshot === entry.snapshot;
    closeSnapshot();
    if (same || !entry.snapshot) return;
    openSnapshot = entry.snapshot;
    tray.hidden = true;
    document.body.append(openSnapshot);
    renderHistory();
  }
  function renderHistory(): void {
    historyEmpty.hidden = history.length > 0;
    historyList.replaceChildren(...[...history].reverse().map(entry => {
      const li = el("li");
      const label = el("label");
      const box = el("input");
      box.type = "checkbox";
      box.checked = !!entry.mark && entry.shown;
      box.disabled = !entry.mark;
      box.title = entry.mark ? "Show the struck area on the map" : "Nothing was fired, so there is no mark";
      box.onchange = () => {
        entry.shown = box.checked;
        entry.mark?.circle.setVisible(entry.shown);
        entry.mark?.marker.setVisible(entry.shown);
      };
      box.setAttribute("aria-label", "Show the struck area on the map");
      label.append(box);
      let text: HTMLElement;
      if (entry.snapshot) {
        text = el("button", "entry", entry.text);
        (text as HTMLButtonElement).type = "button";
        text.title = "Show this engagement's details";
        text.setAttribute("aria-pressed", String(openSnapshot === entry.snapshot));
        text.onclick = () => toggleSnapshot(entry);
      } else {
        text = el("span", entry.mark ? undefined : "muted", entry.text);
      }
      li.append(label, text);
      return li;
    }));
  }
  function record(text: string, chosen?: Option): void {
    if (recorded) return;
    recorded = true;
    let mark: HistoryEntry["mark"];
    if (chosen) {
      const id = `mark-${history.length}`;
      const circle = canvas.addGroundCircles([{ id, center: chosen.position, radiusM: chosen.footprint.radiusM }]);
      circle.setStyles(new Map([[id, markStyle(chosen)]]));
      const marker = canvas.addMarkers([{ id, position: chosen.position }]);
      marker.setStyles(new Map([[id, { color: "#e8eaed", size: 7, visible: true, label: `Intercepted · ${formatT(chosen.timeFromStartS)}` }]]));
      mark = { circle, marker };
      void circle.ready.then(() => { runMarkReady = true; if (!disposed) render(); });
    }
    history.push({ text, mark, shown: true });
    renderHistory();
  }

  /**
   * What the panels cover, so framing uses only the open map. The side window is
   * reserved even while closed (it opens on hover); the tray is reserved at its
   * Live height, since framing happens in Standby while it is still short.
   */
  const coveredInsets = () => {
    const w = innerWidth, h = innerHeight;
    const panel = document.getElementById("panel")?.getBoundingClientRect();
    const trayTop = Math.min(tray.getBoundingClientRect().top, h - 270);
    return {
      left: panel ? panel.right / w : 0,
      right: w > 1100 ? 432 / w : 0, // matches the side window's 16 + 400 + 16 in style.css
      top: 0,
      bottom: Math.max(0, (h - trayTop) / h),
    };
  };
  const framePoints = [...samples, ...options.flatMap(o => circleBounds(o.position, o.footprint.radiusM))];
  const frameCorridor = (): void => {
    // Generous margin: the route flies 1,000 m nearer the camera than the ground, so it looks wider.
    canvas.camera.flyTo(framePose(framePoints, STANDBY_PITCH, innerWidth / innerHeight, 1.3, coveredInsets()), { duration: 1.2 }).catch(ignoreCancel);
  };

  // --- state ---
  let flow: Flow = STANDBY;
  // Detection waits until the areas can draw: they build on shared workers and can
  // take seconds, longer than an option's whole window.
  let layersReady = false;
  let disposed = false;
  void circles.ready.then(() => {
    layersReady = true;
    if (!disposed) render();
  });
  const now = (): number => elapsedS(result, canvas.time.current);

  const cards = options.map((o, i) => {
    const card = el("div", "card");
    card.style.setProperty("--option", optionColour(o));
    const pick = el("button", "pick");
    pick.type = "button";
    const titleEl = el("span", "card-title");
    titleEl.append(el("kbd", undefined, String(i + 1)), ` Option ${i + 1} `, el("code", undefined, shortId(o.id)));
    const badges = el("span", "badges");
    for (const c of o.categories.length ? o.categories : [""]) {
      const badge = el("span", "badge");
      const swatch = el("i");
      swatch.style.background = categoryColour(c);
      badge.append(swatch, categoryLabel(c));
      badges.append(badge);
    }
    const dl = el("dl");
    for (const [k, v, grade] of [[words.exposure, exposureText(o), exposureGradeOf(o)], [words.success, successText(o), successGradeOf(o)], ["Intercept", formatT(o.timeFromStartS), null]] as const) {
      const dd = el("dd", undefined, v);
      if (grade) dd.dataset.grade = grade;
      dl.append(el("dt", undefined, k), dd);
    }
    const bar = el("span", "bar");
    const fill = el("i");
    bar.append(fill);
    const left = el("span", "left countdown");
    pick.append(titleEl, badges, dl, bar, left);
    const fireBtn = el("button", "fire", `FIRE · Option ${i + 1}`);
    fireBtn.type = "button";
    fireBtn.title = "Click to fire. Keyboard firing is disabled.";
    card.append(pick, fireBtn);
    cardsEl.append(card);

    pick.onclick = () => { flow = select(flow, options, o.id, now()); render(); };
    fireBtn.onclick = event => {
      // Keyboard-generated clicks have detail 0: firing takes a real pointer click, never Enter or Space.
      if (event.detail === 0) return;
      flow = fire(flow, options, now());
      render();
    };
    return { option: o, card, pick, fill, left, fireBtn };
  });

  function showInspector(): void {
    const o = options.find(x => x.id === (pinned ?? hovered));
    if (!o || flow.phase === "standby") { inspector.close(); return; }
    const rem = remainingS(o, now());
    inspector.open(o, {
      eyebrow: words.area.toUpperCase(),
      title: `${optionName(o.id)} · ${shortId(o.id)}`,
      colour: optionColour(o),
      pinned: pinned === o.id,
      rows: [
        { label: "Intercept", value: formatT(o.timeFromStartS) },
        { label: words.exposure, value: exposureText(o), grade: exposureGradeOf(o) },
        { label: words.success, value: successText(o), grade: successGradeOf(o) },
        {
          label: "Window",
          value: flow.fired === o.id ? "Fired" : rem === null ? "No window supplied" : rem > 0 ? `${rem.toFixed(1)} s left` : "Expired",
          urgency: flow.phase === "live" && rem !== null && rem > 0 ? urgency(o, now()) : 0,
        },
        { label: "Coverage", value: coverageText(o) },
      ],
      consequence: o.consequence && {
        scenario: o.consequence.scenario ?? null,
        illustrative: o.consequence.illustrative === true,
        rows: consequenceRows(o.consequence),
      },
    });
  }

  // One burst per option, built now so its ground geometry is ready when it plays.
  const bursts = new Map(options.map(o => [
    o.id,
    canvas.addBurst({ lon: o.position.lon, lat: o.position.lat }, { color: "#ff7043", radiusM: o.footprint.radiusM, durationS: BURST_S }),
  ]));

  function beginImpact(chosen: Option): void {
    if (descent) return;
    path.setMarkerVisible(false); // the threat leaves its supplied route here
    descent = canvas.addPath(descentSamples(chosen, start), {
      color: "#ff7043", trailColor: "#ff7043", width: 2, markerSize: 35, markerShape: "craft", markerPulse: true,
    });
  }

  let closeTray: ReturnType<typeof setTimeout> | undefined;
  let lastCircles = "";
  let lastMarkers = "";
  function render(): void {
    let elapsed = now();
    const next = advance(flow, options, elapsed);
    const firedOption = options.find(o => o.id === next.fired);
    if (next.phase === "impact" && firedOption) beginImpact(firedOption);
    if (next.phase === "outcome" && flow.phase !== "outcome" && firedOption) {
      // Hold everything at the moment it comes down.
      canvas.time.pause();
      canvas.time.seek(new Date(start.getTime() + (firedOption.timeFromStartS + DESCENT_S) * 1000));
      elapsed = firedOption.timeFromStartS + DESCENT_S;
      descent?.setMarkerVisible(false); // it is inside the burst now
      const burst = bursts.get(firedOption.id);
      burst?.setVisible(true);
      burst?.play();
      // Close the tray once the burst has played out; Restart brings it back.
      const runIndex = history.length; // record() below adds this run's entry here
      closeTray = setTimeout(() => {
        const snapshot = tray.cloneNode(true) as HTMLElement;
        snapshot.removeAttribute("id");
        snapshot.classList.add("snapshot");
        snapshot.querySelectorAll("button").forEach(b => { b.disabled = true; });
        const close = el("button", "close", "Close");
        close.type = "button";
        close.onclick = closeSnapshot;
        snapshot.querySelector("header")?.append(close);
        const past = history[runIndex];
        if (past) past.snapshot = snapshot;
        tray.hidden = true;
        renderHistory();
      }, BURST_S * 1000);
      setRouteVisible(false); // the flight is over; the struck area stays as the mark
      record(`Threat ${history.length + 1} · ${optionName(firedOption.id)} (${shortId(firedOption.id)}) · intercepted at ${formatT(firedOption.timeFromStartS)}`, firedOption);
    }
    if (next.phase === "expired" && flow.phase !== "expired") record(`Threat ${history.length + 1} · expired · nothing fired`);
    // Nothing was fired, so the supplied route simply runs out.
    if (next.phase === "expired" && elapsed >= endS && canvas.time.playing) {
      canvas.time.pause();
      canvas.time.seek(new Date(start.getTime() + endS * 1000));
      elapsed = endS;
    }
    flow = next;
    const { phase } = flow;
    const locked = phase === "fired" || phase === "impact" || phase === "outcome";
    const chosen = options.find(o => o.id === flow.fired);

    tray.dataset.phase = phase;
    phaseEl.textContent = phase.toUpperCase();
    clockEl.textContent = formatT(Math.max(0, elapsed));
    message.textContent =
      phase === "standby" ? (!options.length ? "No eligible options in this result — nothing to decide" : layersReady ? "Standby — press Space on detection" : "Preparing map layers…")
      : phase === "live" ? (flow.selected ? `${optionName(flow.selected)} selected — click FIRE to commit` : `Threat live — select an option (1–${options.length})`)
      : phase === "fired" ? `Fired ${optionName(flow.fired)} — intercept at ${formatT(chosen!.timeFromStartS)}`
      : phase === "impact" ? `Intercepted at ${formatT(chosen!.timeFromStartS)} — coming down inside its ${words.area.toLowerCase()}`
      : phase === "outcome" ? `Outcome — ${optionName(flow.fired)}, intercept at ${formatT(chosen!.timeFromStartS)}, down inside its ${words.area.toLowerCase()}`
      : "All engagement windows expired — nothing fired";
    cardsEl.hidden = phase === "standby";
    playBtn.disabled = phase !== "standby" || !layersReady;
    restartBtn.disabled = phase === "standby";

    if (phase === "outcome" && chosen && !summary.childElementCount) {
      summary.append(el("li", undefined, `${words.exposure}: ${exposureText(chosen)} · ${words.success}: ${successText(chosen)}`));
      for (const line of comparisonLines(result, chosen.id, words)) {
        summary.append(el("li", undefined, `vs ${optionName(line.otherId)} (${shortId(line.otherId)}): ${line.text}`));
      }
    } else if (phase !== "outcome" && summary.childElementCount) {
      summary.replaceChildren();
    }

    for (const c of cards) {
      const o = c.option;
      const rem = remainingS(o, elapsed);
      const open = isOpen(o, elapsed);
      const selected = flow.selected === o.id;
      c.card.dataset.state = flow.fired === o.id ? "fired" : locked || phase === "expired" || !open ? "closed" : selected ? "selected" : "open";
      c.pick.disabled = phase !== "live" || !open;
      c.pick.setAttribute("aria-pressed", String(selected));
      c.fill.style.width = `${o.timeMarginS && rem !== null ? Math.max(0, Math.min(1, rem / o.timeMarginS)) * 100 : 0}%`;
      c.left.textContent = flow.fired === o.id ? "Fired" : locked ? "—" : rem === null ? "No window supplied" : open ? `${rem.toFixed(1)} s left` : "Window closed";
      // Reddens the countdown and its bar as the window closes.
      c.card.style.setProperty("--urgency", String(phase === "live" && open ? urgency(o, elapsed) : 0));
      c.fireBtn.hidden = !(phase === "live" && selected && open);
    }

    const circleStyles = new Map<string, CircleStyle>(options.map(o => {
      const colour = optionColour(o);
      const strong = { fill: alpha(colour, 0.5), outline: "#ffffff", visible: true };
      const normal = { fill: alpha(colour, 0.3), outline: colour, visible: true };
      const faded = { fill: alpha(colour, 0.08), outline: alpha(colour, 0.4), visible: true };
      // Once it comes down, the area steps back so the burst over it is the thing you see.
      const struck = { fill: alpha(colour, 0.18), outline: "#ffffff", visible: true };
      const gone = { ...faded, visible: false };
      // At the outcome the run's own area shows the mark only until the history copy has built.
      const chosenStyle = phase === "outcome" ? (runMarkReady ? gone : markStyle(o)) : phase === "impact" ? struck : strong;
      const style = locked ? (flow.fired === o.id ? chosenStyle : phase === "outcome" ? gone : faded) : phase === "expired" || !isOpen(o, elapsed) ? faded : flow.selected === o.id ? strong : normal;
      return [o.id, style];
    }));
    const circleKey = JSON.stringify([...circleStyles]);
    if (circleKey !== lastCircles) {
      lastCircles = circleKey;
      circles.setStyles(circleStyles);
      inspector.setCircleStyles(circleStyles);
    }

    const markerStyles = new Map<string, MarkerStyle>();
    options.forEach((o, i) => {
      if (phase === "outcome") {
        // The history entry's own marker carries the "Intercepted" label.
        markerStyles.set(o.id, { color: "#8b949e", size: 9, visible: false, label: String(i + 1) });
        markerStyles.set(`${o.id}#closes`, { color: "#6e7681", size: 6, visible: false, label: "" });
        return;
      }
      const dim = phase === "expired" || (locked && flow.fired !== o.id);
      markerStyles.set(o.id, { color: dim ? "#8b949e" : optionColour(o), size: 9, visible: true, label: String(i + 1) });
      markerStyles.set(`${o.id}#closes`, {
        color: phase === "live" && isOpen(o, elapsed) ? "#ffffff" : "#6e7681", size: 6, visible: phase === "live" || phase === "expired", label: `${i + 1} closes`,
      });
    });
    const markerKey = JSON.stringify([...markerStyles]);
    if (markerKey !== lastMarkers) {
      lastMarkers = markerKey;
      markers.setStyles(markerStyles);
    }

    if (hovered || pinned) showInspector();
  }

  function detectNow(): void {
    if (flow.phase !== "standby" || !layersReady) return;
    closeSnapshot();
    flow = detect(flow);
    setLayersVisible(true);
    canvas.time.seek(start);
    canvas.time.play();
    render();
  }

  function reset(): void {
    flow = STANDBY;
    clearTimeout(closeTray);
    closeSnapshot();
    tray.hidden = false;
    hovered = pinned = null;
    recorded = runMarkReady = false; // the history keeps its entries and marks
    canvas.time.pause();
    canvas.time.seek(start);
    setLayersVisible(false);
    descent?.destroy();
    descent = undefined;
    path.setMarkerVisible(true);
    for (const burst of bursts.values()) burst.setVisible(false);
    inspector.close();
    render();
    frameCorridor();
  }

  playBtn.onclick = detectNow;
  restartBtn.onclick = reset;
  const onKey = (e: KeyboardEvent): void => {
    if (e.ctrlKey || e.metaKey || e.altKey || e.repeat) return;
    if (e.code === "Space") {
      e.preventDefault(); // also keeps Space from pressing whichever button has focus
      detectNow();
    } else if (/^[1-9]$/.test(e.key)) {
      const o = options[Number(e.key) - 1];
      if (o) { flow = select(flow, options, o.id, now()); render(); }
    } else if (e.key === "r" || e.key === "R") {
      reset();
    }
  };
  window.addEventListener("keydown", onKey);
  const offTick = canvas.on("clockTick", t => {
    inspector.syncTime(t);
    render();
  });

  render();
  frameCorridor();

  return {
    setBasemap: kind => inspector.setBasemap(kind),
    setLighting: preset => inspector.setLighting(preset),
    dispose() {
      disposed = true;
      clearTimeout(closeTray);
      offTick();
      window.removeEventListener("keydown", onKey);
      for (const entry of history) { entry.mark?.circle.destroy(); entry.mark?.marker.destroy(); }
      historyPanel.remove();
      openSnapshot?.remove();
      path.destroy();
      descent?.destroy();
      approach?.destroy();
      approachLabel?.destroy();
      markers.destroy();
      circles.destroy();
      inspector.dispose();
      tray.remove();
      presenter.remove();
    },
  };
}
