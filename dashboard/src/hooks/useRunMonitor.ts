import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, api, errorMessage } from '../services/api';
import type { ExecutionEvent, RunSummary } from '../types';
import { needsPolling } from '../lib/utils';

const POLL_MS = 1000;
const ERROR_RETRY_MS = 3000;
const STALLED_POLL_MS = 5000;
/** Consecutive identical summaries (while "active") before we assume the run is no longer progressing. */
const STALL_THRESHOLD = 20;
const MAX_EVENTS = 5000;

export interface RunMonitorState {
  summary: RunSummary | null;
  events: ExecutionEvent[];
  loading: boolean;
  error: string | null;
  polling: boolean;
  /** True when an "active" run has not changed for a while (e.g. the API restarted mid-run). */
  stalled: boolean;
  reload: () => void;
}

/**
 * Polls a run's summary and its events (incrementally with `after`) every second while the run is
 * PENDING/RUNNING or its promotion is pending, then stops. `onSettled` fires once when a run that was
 * being polled reaches a final state.
 */
export function useRunMonitor(
  projectId: string | null,
  runId: string | null,
  onSettled?: (summary: RunSummary) => void,
  onStatusChange?: (summary: RunSummary) => void,
): RunMonitorState {
  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [events, setEvents] = useState<ExecutionEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);
  const [stalled, setStalled] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  const onSettledRef = useRef(onSettled);
  const onStatusChangeRef = useRef(onStatusChange);
  onSettledRef.current = onSettled;
  onStatusChangeRef.current = onStatusChange;

  const reload = useCallback(() => setReloadToken((t) => t + 1), []);

  useEffect(() => {
    if (!projectId || !runId) {
      setSummary(null);
      setEvents([]);
      setPolling(false);
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let lastEventId: string | null = null;
    const seen = new Set<string>();
    let wasActive = false;
    let lastStatusKey = '';
    let lastFingerprint = '';
    let sameCount = 0;

    setSummary(null);
    setEvents([]);
    setError(null);
    setStalled(false);
    setLoading(true);
    setPolling(true);

    const tick = async () => {
      try {
        // Summary first, then events: everything logged before the summary was taken is then included.
        const next = await api.getRun(projectId, runId);
        if (cancelled) return;
        const fresh = await api.getRunEvents(projectId, runId, lastEventId);
        if (cancelled) return;

        const added = fresh.filter((e) => !seen.has(e.event_id));
        added.forEach((e) => seen.add(e.event_id));
        if (fresh.length) lastEventId = fresh[fresh.length - 1].event_id;
        if (added.length) {
          setEvents((prev) => {
            const merged = prev.concat(added);
            return merged.length > MAX_EVENTS ? merged.slice(merged.length - MAX_EVENTS) : merged;
          });
        }

        setSummary(next);
        setError(null);
        setLoading(false);

        const statusKey = `${next.execution_status}|${next.promotion?.state}|${next.current_agent}`;
        if (statusKey !== lastStatusKey) {
          if (lastStatusKey) onStatusChangeRef.current?.(next);
          lastStatusKey = statusKey;
        }

        const active = needsPolling(next);
        if (active) {
          wasActive = true;
          const fingerprint = `${statusKey}|${next.total_duration_ms}|${next.latest_event_timestamp ?? ''}|${next.progress_percent}`;
          sameCount = fingerprint === lastFingerprint && added.length === 0 ? sameCount + 1 : 0;
          lastFingerprint = fingerprint;
          const isStalled = sameCount >= STALL_THRESHOLD;
          setStalled(isStalled);
          timer = setTimeout(tick, isStalled ? STALLED_POLL_MS : POLL_MS);
        } else {
          setPolling(false);
          setStalled(false);
          if (wasActive) onSettledRef.current?.(next);
        }
      } catch (err) {
        if (cancelled) return;
        setError(errorMessage(err, 'Failed to load run'));
        setLoading(false);
        if (err instanceof ApiError && err.status === 404) {
          setPolling(false); // the run does not exist: retrying will not help
          return;
        }
        timer = setTimeout(tick, ERROR_RETRY_MS);
      }
    };

    void tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [projectId, runId, reloadToken]);

  return { summary, events, loading, error, polling, stalled, reload };
}
