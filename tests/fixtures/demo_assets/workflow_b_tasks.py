"""Workflow B coding-task descriptions — tasks/19-sih-workflow-validation.md §7
Requirement 1. Used as `generate_code` task_description inputs by
backend/tests/test_sih_workflows.py; not imported by application code.

CLEAN_TASK is a small, unambiguous industrial calculation with an obvious
correct approach. TRICKY_TASK is the same class of problem but has several
places a first-shot attempt commonly goes wrong (unit handling, division
order, an edge case in the classification thresholds) — intended to exercise
the correction loop, though (per docs/testing.md's documented run-to-run
variance) this is not guaranteed on every run with a real model.
"""

# execute_code (backend/models/schemas.py ExecuteCodeInput) has no stdin/argv
# channel — only `code`, `language`, and `input_files` (sandbox-local file
# paths). So every value the script needs must be embedded as a literal in
# the generated code itself; the task descriptions below say so explicitly
# and give exact numbers, so the expected output is fully deterministic and
# checkable without needing to pipe anything into the sandbox.

CLEAN_TASK = (
    "Write a standalone Python script (no input() or stdin reads — hardcode "
    "the values below as literals) that computes a pump's hydraulic power "
    "in kilowatts, using discharge pressure = 5.2 bar and flow rate = 250 "
    "cubic meters per hour, with P_kW = (pressure_bar * 1e5 * flow_m3h / "
    "3600) / 1000. Print only the result rounded to 2 decimal places, "
    "nothing else."
)
# Expected: (5.2 * 1e5 * 250 / 3600) / 1000 = 36.11

TRICKY_TASK = (
    "Write a standalone Python script (no input() or stdin reads — hardcode "
    "the values below as literals) using flow rate = 0.05 cubic meters per "
    "second and target velocity = 2.0 meters per second. Using the "
    "continuity equation Q = A * v where A = pi * d^2 / 4, compute the "
    "required pipe diameter in meters and print it rounded to 4 decimal "
    "places on the first line. Then, assuming water at 20 degrees C with "
    "kinematic viscosity 1.004e-6 square meters per second, compute the "
    "Reynolds number Re = v * d / viscosity and print, on a second line, "
    "exactly one of 'laminar' (Re < 2300), 'transitional' "
    "(2300 <= Re <= 4000), or 'turbulent' (Re > 4000)."
)
# Expected: d = sqrt(4*0.05/(pi*2.0)) = 0.1784 ; Re = 2.0*0.1784/1.004e-6
# = 355363 -> 'turbulent'
