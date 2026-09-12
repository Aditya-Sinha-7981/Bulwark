import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../services/api", () => ({
  getNetworkStatus: vi.fn(),
}));

import SovereigntyIndicator from "./SovereigntyIndicator";
import { getNetworkStatus } from "../services/api";

function healthyResponse(overrides = {}) {
  return {
    external_connections_detected: false,
    checked_at: new Date().toISOString(),
    monitoring_since: "2026-09-12T00:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  getNetworkStatus.mockReset();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("healthy state", () => {
  it("renders 0 external connections and monitoring_since on a fresh successful poll", async () => {
    getNetworkStatus.mockResolvedValue(healthyResponse());

    render(<SovereigntyIndicator />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByTestId("sovereignty-indicator")).toHaveAttribute(
      "data-variant",
      "healthy"
    );
    expect(screen.getByTestId("sovereignty-label")).toHaveTextContent(
      "0 external connections"
    );
    expect(screen.getByTestId("monitoring-since")).toHaveTextContent(
      "2026-09-12T00:00:00Z"
    );
  });
});

describe("polling cadence", () => {
  it("calls getNetworkStatus repeatedly on the ~2s interval and updates checked_at", async () => {
    let counter = 0;
    getNetworkStatus.mockImplementation(() =>
      Promise.resolve(healthyResponse({ checked_at: `checked-${counter++}` }))
    );

    render(<SovereigntyIndicator />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(getNetworkStatus).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("checked-at")).toHaveTextContent("checked-0");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(getNetworkStatus).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId("checked-at")).toHaveTextContent("checked-1");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(getNetworkStatus).toHaveBeenCalledTimes(3);
    expect(screen.getByTestId("checked-at")).toHaveTextContent("checked-2");
  });
});

describe("staleness", () => {
  it("switches to the stale state after 5s with no successful update, distinct from healthy", async () => {
    getNetworkStatus
      .mockResolvedValueOnce(healthyResponse())
      .mockRejectedValue(new Error("network down"));

    render(<SovereigntyIndicator />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByTestId("sovereignty-indicator")).toHaveAttribute(
      "data-variant",
      "healthy"
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });

    expect(screen.getByTestId("sovereignty-indicator")).toHaveAttribute(
      "data-variant",
      "stale"
    );
    expect(screen.getByTestId("sovereignty-label")).toHaveTextContent(
      "Monitor unavailable"
    );
  });

  it("never shows the healthy state for data older than 5s even without errors (stalled backend)", async () => {
    getNetworkStatus.mockResolvedValueOnce(healthyResponse());
    getNetworkStatus.mockImplementation(() => new Promise(() => {}));

    render(<SovereigntyIndicator />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByTestId("sovereignty-indicator")).toHaveAttribute(
      "data-variant",
      "healthy"
    );

    for (let i = 0; i < 6; i++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
    }

    expect(screen.getByTestId("sovereignty-indicator")).toHaveAttribute(
      "data-variant",
      "stale"
    );
  });
});

describe("alarm state", () => {
  it("renders an unmistakable alarm state when external_connections_detected is true", async () => {
    getNetworkStatus.mockResolvedValue(
      healthyResponse({ external_connections_detected: true })
    );

    render(<SovereigntyIndicator />);
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByTestId("sovereignty-indicator")).toHaveAttribute(
      "data-variant",
      "alarm"
    );
    expect(screen.getByTestId("sovereignty-label")).toHaveTextContent(
      "External connection detected"
    );
  });
});

describe("error handling and recovery", () => {
  it("shows stale/unavailable on endpoint error, keeps polling, and recovers to healthy", async () => {
    getNetworkStatus.mockRejectedValue(new Error("connection refused"));

    render(<SovereigntyIndicator />);
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByTestId("sovereignty-indicator")).toHaveAttribute(
      "data-variant",
      "stale"
    );
    expect(screen.getByTestId("sovereignty-label")).toHaveTextContent(
      "Monitor unavailable"
    );

    getNetworkStatus.mockResolvedValue(healthyResponse());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(screen.getByTestId("sovereignty-indicator")).toHaveAttribute(
      "data-variant",
      "healthy"
    );
    expect(getNetworkStatus).toHaveBeenCalledTimes(2);
  });
});

describe("unmount cleanup", () => {
  it("clears the polling interval on unmount -- no further calls after unmount", async () => {
    getNetworkStatus.mockResolvedValue(healthyResponse());

    const { unmount } = render(<SovereigntyIndicator />);
    await act(async () => {
      await Promise.resolve();
    });
    const callsBeforeUnmount = getNetworkStatus.mock.calls.length;

    unmount();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });

    expect(getNetworkStatus.mock.calls.length).toBe(callsBeforeUnmount);
  });
});

describe("network call surface", () => {
  it("never calls fetch() directly -- only the mocked getNetworkStatus service function", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    getNetworkStatus.mockResolvedValue(healthyResponse());

    render(<SovereigntyIndicator />);
    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(getNetworkStatus).toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});