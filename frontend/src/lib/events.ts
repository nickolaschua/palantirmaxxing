type Handler<T> = (payload: T) => void;

/**
 * Minimal typed emitter. `on` returns its own disposer — there is deliberately
 * no `off(event, handler)`, because identity-matching handlers leaks whenever a
 * caller passes an inline arrow function.
 */
export class Emitter<Events extends Record<string, unknown>> {
  #handlers = new Map<keyof Events, Set<Handler<never>>>();

  on<K extends keyof Events>(event: K, handler: Handler<Events[K]>): () => void {
    let set = this.#handlers.get(event);
    if (!set) {
      set = new Set();
      this.#handlers.set(event, set);
    }
    const entry = handler as Handler<never>;
    set.add(entry);
    return () => {
      this.#handlers.get(event)?.delete(entry);
    };
  }

  emit<K extends keyof Events>(event: K, payload: Events[K]): void {
    const set = this.#handlers.get(event);
    if (!set) return;
    for (const handler of [...set]) (handler as Handler<Events[K]>)(payload);
  }

  clear(): void {
    this.#handlers.clear();
  }
}
