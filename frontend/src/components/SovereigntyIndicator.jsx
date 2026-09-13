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

  // Dark-theme tokens matching the rest of the shell (bg-ink/txt-hi/etc,
  // see index.css) \u2014 this used to hardcode light-mode Tailwind colors
  // (bg-emerald-50/text-emerald-800/...) inside a dark app shell, and as a
  // full card (not a compact status-bar item) it visually overflowed the
  // thin StatusBar footer it's mounted in. Redesigned as a single-line
  // badge; the full detail (checked_at, monitoring_since, disclaimer) is
  // still in the DOM for tests/screen readers and available on hover via
  // `title`, rather than always taking vertical space it doesn't have.
  const variantClasses = {
    healthy: "border-ok/40 text-ok",
    alarm: "border-danger/50 text-danger",
    stale: "border-line text-txt-dim",
  };

  const dotClasses = {
    healthy: "bg-ok animate-pulse",
    alarm: "bg-danger",
    stale: "bg-txt-dim",
  };

  const tooltipParts = [
    status?.monitoring_since ? `Monitoring since: ${status.monitoring_since}` : null,
    "Live monitor of observed network activity \u2014 shown as proof, not itself a network control.",
  ].filter(Boolean);

  return (
    <div
      className={`sovereignty-indicator inline-flex items-center gap-1.5 rounded border px-2 py-0.5 ${variantClasses[variant]}`}
      data-testid="sovereignty-indicator"
      data-variant={variant}
      role="status"
      aria-live="polite"
      title={tooltipParts.join("\n")}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotClasses[variant]}`}
        data-testid="status-dot"
        aria-hidden="true"
      />
      <span className="sovereignty-indicator__label text-[11px] font-medium" data-testid="sovereignty-label">
        {label}
      </span>

      {status && status.checked_at && (
        <span className="sovereignty-indicator__checked-at hidden text-[11px] font-mono text-txt-dim md:inline" data-testid="checked-at">
          {"\u00b7"} {status.checked_at}
        </span>
      )}

      {status && status.monitoring_since && (
        <span className="sovereignty-indicator__monitoring-since sr-only" data-testid="monitoring-since">
          Monitoring since: {status.monitoring_since}
        </span>
      )}

      <span className="sovereignty-indicator__disclaimer sr-only" data-testid="disclaimer">
        {"Live monitor of observed network activity \u2014 shown as proof, not itself a network control."}
      </span>
    </div>
  );
}