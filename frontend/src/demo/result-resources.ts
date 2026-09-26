import type { SingaporeCanvas } from "../lib/index.js";

/** Own a render attempt from its first layer, so partial construction is disposable. */
export class ResultResources {
  private cleanups = new Set<() => void>();
  private disposed = false;
  readonly canvas: SingaporeCanvas;

  constructor(canvas: SingaporeCanvas) {
    this.canvas = new Proxy(canvas, {
      get: (target, key, receiver) => {
        const original = Reflect.get(target, key, receiver);
        if (typeof key === "string" && ["addPath", "addMarkers", "addGroundCircles", "addLabels", "addBurst"].includes(key)) {
          return (...args: unknown[]) => {
            if (this.disposed) throw new Error("Result resources have been disposed");
            const layer = original.apply(target, args) as { destroy(): void };
            const destroy = layer.destroy.bind(layer);
            layer.destroy = this.use(destroy);
            return layer;
          };
        }
        if (key === "on") return (...args: unknown[]) => this.use(original.apply(target, args));
        return original;
      },
    });
  }

  use(cleanup: () => void): () => void {
    let done = false;
    const once = () => {
      if (done) return;
      done = true;
      this.cleanups.delete(once);
      cleanup();
    };
    if (this.disposed) once(); else this.cleanups.add(once);
    return once;
  }

  node<T extends HTMLElement>(node: T): T {
    this.use(() => node.remove());
    return node;
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    for (const cleanup of [...this.cleanups].reverse()) cleanup();
    this.cleanups.clear();
  }
}
