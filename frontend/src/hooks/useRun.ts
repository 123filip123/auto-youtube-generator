import { useCallback, useEffect, useState } from "react";

import { getRun } from "@/lib/api";
import { TERMINAL_STATUSES, type RunDetail } from "@/lib/types";

export interface UseRunResult {
  run: RunDetail | null;
  error: string | null;
  loading: boolean;
  /** Fetch immediately instead of waiting for the next poll. */
  refresh: () => void;
}

/**
 * Poll one run until it reaches a terminal status.
 *
 * A failed request does not stop the loop — the backend restarting mid-run
 * should not freeze the view — but the error is surfaced so the UI can say so.
 */
export function useRun(runId: string | null, intervalMs = 2000): UseRunResult {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(runId !== null);
  const [nonce, setNonce] = useState(0);

  const refresh = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    if (!runId) {
      setRun(null);
      setLoading(false);
      return;
    }

    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const tick = async () => {
      try {
        const next = await getRun(runId);
        if (!active) return;
        setRun(next);
        setError(null);
        if (!TERMINAL_STATUSES.has(next.status)) {
          timer = setTimeout(tick, intervalMs);
        }
      } catch (caught) {
        if (!active) return;
        setError(caught instanceof Error ? caught.message : String(caught));
        timer = setTimeout(tick, intervalMs);
      } finally {
        if (active) setLoading(false);
      }
    };

    void tick();

    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [runId, intervalMs, nonce]);

  return { run, error, loading, refresh };
}
