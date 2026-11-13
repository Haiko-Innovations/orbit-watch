import { useCallback, useEffect, useState } from "react";

export type Resource<T> =
  | { state: "loading" }
  | { state: "ready"; value: T }
  | { state: "failed"; error: Error };

/** Loads ``load()`` once, and again on ``reload()``. */
export function useResource<T>(load: () => Promise<T>): [Resource<T>, () => void] {
  const [resource, setResource] = useState<Resource<T>>({ state: "loading" });
  const [round, setRound] = useState(0);
  // biome-ignore lint/correctness/useExhaustiveDependencies: a new `round` restarts the load.
  useEffect(() => {
    let current = true;
    setResource({ state: "loading" });
    load().then(
      (value) => current && setResource({ state: "ready", value }),
      (error: unknown) =>
        current &&
        setResource({
          state: "failed",
          error: error instanceof Error ? error : new Error(String(error)),
        }),
    );
    return () => {
      current = false;
    };
  }, [load, round]);
  const reload = useCallback(() => setRound((n) => n + 1), []);
  return [resource, reload];
}
