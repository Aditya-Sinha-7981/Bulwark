import { useCallback, useEffect, useRef, useState } from "react";
import { getNetworkStatus } from "../services/api";

const POLL_INTERVAL_MS = 2000;
const STALE_THRESHOLD_MS = 5000;
const CLOCK_TICK_MS = 1000;

export default function SovereigntyIndicator() {
  const [status, setStatus] = useState(null);
  const [lastSuccessAt, setLastSuccessAt] = useState(null);
  const [now, setNow] = useState(() => Date.now());
  const cancelledRef = useRef(false);

  const poll = useCallback(async () => {
    try {
      const result = await getNetworkStatus();
      if (cancelledRef.current) return;
      setStatus(result);
      setLastSuccessAt(Date.now());
    } catch {
      // Deliberately swallow -- an error means "no successful update",
      // which the staleness calculation below already handles correctly by
      // simply not advancing lastSuccessAt. The stale/"monitor unavailable"
      // state IS the error state for this panel.
    }
  }, []);

  useEffect(() => {
    cancelledRef.current = false;
    poll();
    const pollId = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelledRef.current = true;
      clearInterval(pollId);
    };
  }, [poll]);

  useEffect(() => {
    const clockId = setInterval(() => setNow(Date.now()), CLOCK_TICK_MS);
    return () => clearInterval(clockId);
  }, []);

  const isStale =
    lastSuccessAt === null || now - lastSuccessAt > STALE_THRESHOLD_MS;
  const secondsSinceUpdate =
    lastSuccessAt === null ? null : Math.max(0, Math.floor((now - lastSuccessAt) / 1000));

  let variant;
  let label;
  if (isStale) {
    variant = "stale";
    label =
      lastSuccessAt === null
        ? "Monitor unavailable"
        : `Monitor unavailable \u2014 last updated ${secondsSinceUpdate}s ago`;
  } else if (status && status.external_connections_detected) {
    variant = "alarm";
    label = "External connection detected";
  } else {
    variant = "healthy";
    label = "0 external connections";
  }

  const variantClasses = {
    healthy: "bg-emerald-50 border-emerald-400 text-emerald-800",
    alarm: "bg-red-50 border-red-500 text-red-800",
    stale: "bg-amber-50 border-amber-400 text-amber-800",
  };

  const dotClasses = {
    healthy: "bg-emerald-500 animate-pulse",
    alarm: "bg-red-500",
    stale: "bg-amber-500",
  };

  return (
    <div
      className={`sovereignty-indicator border-2 rounded-lg p-4 ${variantClasses[variant]}`}
      data-testid="sovereignty-indicator"
      data-variant={variant}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-3">
        <div
          className={`w-3 h-3 rounded-full ${dotClasses[variant]}`}
          data-testid="status-dot"
          aria-hidden="true"
        />
        <div className="sovereignty-indicator__label font-medium" data-testid="sovereignty-label">
          {label}
        </div>
      </div>

      {status && status.checked_at && (
        <div className="sovereignty-indicator__checked-at mt-2 text-sm font-mono" data-testid="checked-at">
          Last checked: {status.checked_at}
        </div>
      )}

      {status && status.monitoring_since && (
        <div
          className="sovereignty-indicator__monitoring-since mt-1 text-sm font-mono" data-testid="monitoring-since"
        >
          Monitoring since: {status.monitoring_since}
        </div>
      )}

      <div className="sovereignty-indicator__disclaimer mt-3 text-xs text-slate-500" data-testid="disclaimer">
        {"Live monitor of observed network activity \u2014 shown as proof, not itself a network control."}
      </div>
    </div>
  );
}