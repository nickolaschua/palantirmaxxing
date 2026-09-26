import type { ResultLoader } from "./source.js";

/** Owns requests and a single validated view; late settlements are inert. */
export function mountResultLoader<T, V extends { dispose(): void }>(
  parent: HTMLElement, label: string, load: ResultLoader,
  parse: (value: unknown) => T, render: (value: T) => V,
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
  let generation = 0;
  let disposed = false;
  let view: V | undefined;
  async function run() {
    if (disposed) return;
    const request = ++generation;
    status.hidden = false;
    message.textContent = label + ": Loading…";
    retryButton.hidden = true;
    try {
      const raw = await load();
      if (disposed || request !== generation) return;
      const parsed = parse(raw);
      view?.dispose();
      view = undefined;
      view = render(parsed);
      status.hidden = true;
    } catch (error) {
      if (disposed || request !== generation) return;
      message.textContent = label + ": Unavailable — " + (error instanceof Error ? error.message : String(error));
      retryButton.hidden = false;
    }
  }
  const retry = () => { void run(); };
  retryButton.onclick = retry;
  retry();
  return {
    retry,
    current: () => view,
    dispose() {
      if (disposed) return;
      disposed = true;
      ++generation;
      view?.dispose();
      view = undefined;
      status.remove();
    },
  };
}
