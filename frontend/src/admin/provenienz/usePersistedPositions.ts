import { useCallback, useEffect, useRef, useState } from "react";

export interface XY {
  x: number;
  y: number;
}

const KEY_PREFIX = "provenienz:positions:";
const SAVE_DEBOUNCE_MS = 400;

/**
 * Persist tile positions across tab navigations / component remounts. Keyed
 * by sessionId in localStorage so each Provenienz session has its own layout
 * memory.
 *
 * Returns a snapshot map of view_id → {x, y} loaded once on mount, plus a
 * debounced ``savePositions`` setter the canvas calls on every node-position
 * change. The ``clear`` callback wipes saved positions for the current
 * session — used by the Reset button.
 */
export function usePersistedPositions(sessionId: string | null): {
  loaded: Map<string, XY>;
  ready: boolean;
  save: (positions: Map<string, XY>) => void;
  clear: () => void;
} {
  const [loaded, setLoaded] = useState<Map<string, XY>>(() => new Map());
  /** ``ready`` flips true once we've finished reading localStorage. The
   *  Canvas gates its save-effect on this so a fresh remount can't
   *  clobber saved positions with the temporary dagre defaults. */
  const [ready, setReady] = useState(false);
  const saveTimer = useRef<number | null>(null);

  // Load on session change.
  useEffect(() => {
    setReady(false);
    if (!sessionId) {
      setLoaded(new Map());
      setReady(true);
      return;
    }
    try {
      const raw = localStorage.getItem(KEY_PREFIX + sessionId);
      if (!raw) {
        setLoaded(new Map());
      } else {
        const obj = JSON.parse(raw) as Record<string, XY>;
        setLoaded(new Map(Object.entries(obj)));
      }
    } catch {
      setLoaded(new Map());
    }
    setReady(true);
  }, [sessionId]);

  const save = useCallback(
    (positions: Map<string, XY>) => {
      if (!sessionId) return;
      if (saveTimer.current !== null) {
        window.clearTimeout(saveTimer.current);
      }
      saveTimer.current = window.setTimeout(() => {
        try {
          const obj: Record<string, XY> = {};
          for (const [k, v] of positions) obj[k] = v;
          localStorage.setItem(KEY_PREFIX + sessionId, JSON.stringify(obj));
        } catch {
          /* quota exceeded or storage disabled — silently ignore */
        }
      }, SAVE_DEBOUNCE_MS);
    },
    [sessionId],
  );

  const clear = useCallback(() => {
    if (!sessionId) return;
    try {
      localStorage.removeItem(KEY_PREFIX + sessionId);
    } catch {
      /* ignore */
    }
    setLoaded(new Map());
  }, [sessionId]);

  // Flush any pending save on unmount.
  useEffect(() => {
    return () => {
      if (saveTimer.current !== null) {
        window.clearTimeout(saveTimer.current);
      }
    };
  }, []);

  return { loaded, ready, save, clear };
}
