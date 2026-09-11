# SOP-002 — Manual Valve Inspection, Leakage Classification, and Isolation

**Document type:** Standard Operating Procedure
**Applicable equipment:** Manually operated gate, globe, and butterfly valves used for system isolation in cooling water, process water, and low-pressure steam service
**Issuing authority:** Trishul Thermal Power Station (TTPS) — Mechanical Maintenance Department
**Revision:** 3
**Effective date:** 2026-02-01

> This is a synthetic, fictional procedure created for internal system testing. It does not describe any real facility, organization, or equipment.

## 1. Purpose and Scope

This procedure defines inspection frequency, leakage classification, isolation requirements, and return-to-service criteria for manually operated isolation valves at TTPS. It does not cover control valves or pressure relief valves (see SOP-003 for relief valve set-pressure verification).

## 2. Inspection Frequency

- Valves in continuous isolation duty (normally closed): visually inspected every 90 days.
- Valves in continuous throughput duty (normally open): visually inspected every 180 days.
- Any valve subject to an isolation certificate (Section 4) is inspected at the time the isolation is applied and again when it is removed.

## 3. External (Stem/Packing) Leakage Classification

Assessed at the valve stem packing gland, observed over a minimum 30-second window with the valve in its normal operating position.

| Grade | Description | Approximate rate | Required action |
|---|---|---|---|
| A | No visible leakage (dry) | 0 | No action |
| B | Light moisture / weeping, no dripping | Weeping, no drip formation | Acceptable; re-inspect at the next scheduled interval |
| C | Dripping | Less than 1 drop per 10 seconds | Schedule packing gland repacking within **14 days** |
| D | Continuous dripping or streaming | 1 drop per 10 seconds or more, or a continuous stream | Isolate the valve and repair **before** it is returned to service |

## 4. Internal (Seat) Leakage and Isolation Adequacy

A valve's internal seat leakage matters primarily when the valve is being relied on as an isolation point for downstream maintenance work. To check seat leakage adequacy for isolation purposes:

- Close the valve fully and monitor downstream temperature (for hot systems) or pressure (for pressurized systems) for 10 minutes.
- If downstream temperature rises by more than 2 °C within that 10-minute window (or downstream pressure fails to bleed down and hold at atmospheric), the valve exhibits seat leakage and **shall not be used as the sole isolation point**.

**A single valve, regardless of its seat leakage test result, is never sufficient isolation on its own for maintenance work.** Positive isolation requires one of the following, verified and recorded on an Isolation Certificate before work begins:

1. **Double block and bleed** — two valves in series in the closed position, with the bleed/vent valve between them open and tagged open, so any seat leakage past the first valve is visible and vented rather than reaching the work area; or
2. A **blank (spade)** installed at a flanged joint downstream of the isolation valve, verified by visual confirmation that the blank is in place.

Cross-reference: the lockout/tagout procedure for applying and controlling the isolation locks themselves is SOP-004.

## 5. Lockout/Tagout for Valve Isolation

- A locking device (multi-hole hasp or dedicated valve lockout device) is applied to the isolation valve's handwheel or lever in the closed position immediately after closing.
- The accompanying tag is signed and dated by the isolating authority and states the associated work order number.
- The isolation is logged in the plant Isolation Register at the time it is applied, referencing the Isolation Certificate number from Section 4.
- Only the person who applied the lock may remove it, **except** via the Lock Removal Authorization procedure in SOP-004 (used only when the applying person is unavailable).

## 6. Inspection Findings and Corrective Action — Summary

| Finding | Corrective action | Timeframe |
|---|---|---|
| Grade B external leakage | Monitor; re-inspect next cycle | Next scheduled interval |
| Grade C external leakage | Repack packing gland | 14 days |
| Grade D external leakage | Isolate and repair before return to service | Immediate |
| Seat leakage detected during isolation adequacy test | Do not rely on this valve alone; apply double block and bleed or a blank | Immediate, before work proceeds |

## 7. Return-to-Service Requirements

Before a valve that has been repaired or repacked is returned to service:

1. The valve is stroke-tested through one full open/close cycle and operates smoothly without excessive handwheel torque.
2. External leakage is re-verified as Grade A or Grade B.
3. If the valve was used as an isolation point, the isolation adequacy test in Section 4 is re-run and passes.
4. The associated Isolation Certificate (if one was raised) is formally closed out.
5. The work is signed off by the Valve Custodian or the Shift Engineer and recorded in the equipment history log.

A valve repacked for Grade C or D leakage does not meet return-to-service requirements on packing repair alone if it was also relied on as an isolation point — the isolation adequacy test in Section 4 must be independently re-verified.
