# SOP-001 — Cooling Water Pump Maintenance and Condition Monitoring

**Document type:** Standard Operating Procedure
**Applicable equipment:** Horizontal centrifugal cooling water pumps (e.g. CWP-2xx series), condenser cooling water and auxiliary cooling water systems
**Issuing authority:** Trishul Thermal Power Station (TTPS) — Mechanical Maintenance Department
**Revision:** 4
**Effective date:** 2026-01-15

> This is a synthetic, fictional procedure created for internal system testing. It does not describe any real facility, organization, or equipment.

## 1. Purpose and Scope

This procedure defines inspection, condition-monitoring, lubrication, and corrective-action requirements for horizontal centrifugal cooling water pumps in continuous service at TTPS. It applies to routine field inspections, condition-based maintenance rounds, and post-maintenance return-to-service checks.

## 2. Pump Inspection — Routine Checks

Every routine inspection of a cooling water pump shall record, at minimum:

- Overall vibration velocity (mm/s RMS) at both the inboard and outboard bearing housings, measured radially.
- Bearing housing temperature (°C), measured with a calibrated infrared thermometer or contact probe.
- Mechanical seal condition and leakage rate at the seal chamber drain.
- Coupling alignment status and coupling guard condition.
- General visual condition (corrosion, unusual noise, oil level in the bearing housing sight glass).

Inspections are conducted weekly for pumps in continuous service and daily during commissioning or after any corrective maintenance.

## 3. Vibration Measurement and Classification

Vibration velocity is measured as overall RMS value (10 Hz – 1 kHz band) at each bearing housing. Classify the **higher** of the two bearing readings against the table below:

| Band | Vibration velocity (mm/s RMS) | Classification | Required action |
|---|---|---|---|
| 1 | ≤ 4.5 | Normal | No action; continue routine monitoring |
| 2 | > 4.5 and ≤ 7.1 | Caution | Increase monitoring frequency to weekly-plus-spot-check; schedule a lubrication and alignment check within 14 days |
| 3 | > 7.1 and ≤ 11.0 | Alert | Schedule corrective maintenance within **7 days**; notify the Area Engineer |
| 4 | > 11.0 | Critical | Remove the pump from service within **24 hours**; mandatory escalation to the Maintenance Superintendent |

A pump found in Band 3 (Alert) or Band 4 (Critical) shall have its finding entered in the equipment deviation register at the time of inspection, not deferred to end-of-shift reporting.

## 4. Lubrication

- Bearing grease: NLGI Grade 2 lithium-complex grease (or approved equivalent listed in the plant lubricant schedule).
- Re-greasing interval: every 2000 operating hours **or** 90 calendar days, whichever occurs first, for pumps in continuous service.
- Bearing housing temperature classification:

| Bearing temperature | Classification | Required action |
|---|---|---|
| ≤ 70 °C | Normal | No action |
| > 70 °C and ≤ 85 °C | Caution | Verify lubrication is current; re-check within 48 hours |
| > 85 °C | Critical | Immediate shutdown; do not restart until the cause is identified and corrected |

Lubricant discoloration (milky, dark, or metallic-sheen grease/oil) observed during inspection shall be flagged for laboratory oil analysis and noted as an informational finding, even if no numeric threshold is exceeded.

## 5. Mechanical Seal Leakage Classification

Mechanical seal leakage is assessed at the seal chamber drain by visual observation over a minimum 60-second window.

| Class | Description | Approximate rate | Required action |
|---|---|---|---|
| I | No visible leakage (dry) | 0 drops/min | No action |
| II | Weeping / light moisture film | > 0 and ≤ 10 drops/min | Acceptable; continue routine monitoring |
| III | Steady drip | > 10 and ≤ 60 drops/min | Schedule mechanical seal replacement within **30 days** |
| IV | Streaming / continuous flow | > 60 drops/min, or a continuous stream | Immediate shutdown; seal shall be replaced **before** the pump is returned to service |

## 6. Coupling and Guard Inspection

- Coupling alignment tolerance (post-maintenance or if realignment is suspected): parallel misalignment ≤ 0.05 mm; angular misalignment ≤ 0.03 mm per 100 mm of coupling diameter. A coupling found outside tolerance shall be realigned before the pump is returned to service.
- The coupling guard shall be fully intact and secured with all fasteners present at every inspection.
- **A pump with a missing, damaged, or unsecured coupling guard shall not be started or left running.** Isolate and tag the pump per SOP-004 (Workplace Safety — Lockout/Tagout) until the guard is restored.

## 7. Corrective-Action Thresholds — Summary

Any single finding at "Alert" (vibration Band 3) or "Critical" (vibration Band 4, bearing temperature Critical, or seal Class IV) is a corrective-action-required finding. A finding at "Caution" (vibration Band 2, bearing temperature Caution) or seal Class II is a monitor-only finding and does not by itself require a work order.

## 8. Escalation Conditions

- Any single **Critical** finding (vibration Band 4, bearing temperature > 85 °C, or seal Class IV leakage): escalate to the Maintenance Superintendent within **4 hours** of the inspection and log the escalation in the deviation register.
- Two or more concurrent **Alert**-level or worse findings on the same pump (e.g., Band 3 vibration together with Class III seal leakage): escalate to the Area Engineer, regardless of whether any single finding individually reached Critical.
- A missing or damaged coupling guard is always escalated to the Area Engineer immediately, independent of any other reading, because it is a safety finding under SOP-004.

## 9. Return-to-Service Requirements

Before a pump that has had a corrective-action-required finding is returned to service, all of the following must be confirmed and recorded on the work order:

1. Vibration velocity at both bearings is within Band 1 (Normal) or Band 2 (Caution) — a pump may not be returned to service while still in Band 3 or 4.
2. Mechanical seal leakage is Class I or Class II.
3. Bearing temperature is Normal or Caution (≤ 85 °C) under load.
4. Coupling guard is reinstalled, intact, and all fasteners are secured.
5. Coupling alignment (if adjusted) is within the tolerances in Section 6.
6. The work order is signed off by the Shift Engineer and the finding is closed out in the equipment history log.

A pump does not meet return-to-service requirements on the basis of vibration or temperature alone if the mechanical seal leakage classification has not also been independently re-verified.
