import type { ResultLoader, Snapshot } from "./source.js";
import { isSnapshot } from "./source.js";

/** Owns requests and a single validated view; late settlements are inert. */
export function mountResultLoader<T, V extends { dispose(): void }>(
  parent: HTMLElement, label: string, load: ResultLoader,
  parse: (value: unknown) => T, render: (value: T, snapshot?: Snapshot) => V,
) {
  const status = document.createElement("section");
  status.className = "result-load-status";
  status.setAttribute("aria-label", label + " result loading");
  const message = document.createElement("p");
  message.setAttribute("role", "status");
  const retryButton = document.createElement("button");
  retryButton.type = "button";
  retryButton.textContent = "Retry";
  status.append(message, retryButton);
  parent.append(status);
  const metadata = document.createElement("section");
  metadata.className = "result-metadata";
  metadata.dataset.kind = label.toLowerCase();
  metadata.setAttribute("aria-label", label + " snapshot");
  const identity = document.createElement("p");
  identity.className = "result-identity";
  identity.textContent = label + " · No snapshot loaded";
  const refreshButton = document.createElement("button");
  refreshButton.type = "button";
  refreshButton.textContent = `Refresh ${label.toLowerCase()}`;
  metadata.append(identity, refreshButton);
  parent.append(metadata);
  let generation = 0;
  let disposed = false;
  let view: V | undefined;
  let snapshot: Snapshot | undefined;
  let abort: AbortController | undefined;
  async function run(resultId?: string) {
    if (disposed) return;
    const request = ++generation;
    abort?.abort();
    abort = new AbortController();
    status.hidden = false;
    message.textContent = label + ": Loading…";
    retryButton.hidden = true;
    try {
      const raw = await load(resultId, abort.signal);
      if (disposed || request !== generation) return;
      const nextSnapshot = isSnapshot(raw) ? raw : undefined;
      const parsed = parse(nextSnapshot ? nextSnapshot.result : raw);
      // A render attempt owns its partial resources. Keep the preceding view
      // until the new view has successfully constructed.
      const next = render(parsed, nextSnapshot);
      view?.dispose();
      view = next;
      snapshot = nextSnapshot;
      metadata.dataset.resultId = snapshot?.resultId ?? "";
      identity.textContent = snapshot?.source === "http"
        ? `${label} · HTTP · ${snapshot.resultId} · Published ${snapshot.publishedAt}`
        : `${label} · Fixture mode · illustrative demo`;
      status.hidden = true;
    } catch (error) {
      if (disposed || request !== generation) return;
      message.textContent = label + ": Unavailable — " + (error instanceof Error ? error.message : String(error));
      retryButton.hidden = false;
    }
  }
  const retry = () => { void run(); };
  retryButton.onclick = refreshButton.onclick = retry;
  retry();
  return {
    retry,
    loadIdentity: (identity: string) => run(identity),
    snapshot: () => snapshot ? structuredClone(snapshot) : undefined,
    current: () => view,
    controls: metadata,
    dispose() {
      if (disposed) return;
      disposed = true;
      ++generation;
      abort?.abort();
      retryButton.onclick = refreshButton.onclick = null;
      view?.dispose();
      view = undefined;
      snapshot = undefined;
      status.remove();
      metadata.remove();
    },
  };
}
