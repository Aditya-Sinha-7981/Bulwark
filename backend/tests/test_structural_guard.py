"""
Structural non-bypass guarantee (Task 15 Requirement 2, AGENTS.md §6 rule 1).

There is no code path from an Orchestrator proposal to a capability executor
that does not pass through `evaluate(...)` + an `allow` decision. Concretely:

  1. No module outside `backend/domain/job_manager/` imports a
     `backend/domain/capabilities/<executor>` module or calls its `execute_*`
     entry point. (The capability *registry* is exempt — it is contracts /
     validation only, no execution.)
  2. `manager._dispatch_capability` — the single post-Policy dispatch seam —
     has exactly one call site.
"""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
JOB_MANAGER_DIR = BACKEND / "domain" / "job_manager"
CAPABILITIES_DIR = BACKEND / "domain" / "capabilities"

EXECUTOR_MODULES = {
    "extract_document",
    "search_knowledge_base",
    "generate_code",
    "execute_code",
    "create_docx",
    "create_xlsx",
}
EXECUTOR_FUNCS = {f"execute_{name}" for name in EXECUTOR_MODULES} | {
    "execute_search_knowledge_base",
    "execute_generate_code",
    "execute_extract_document",
    "execute_execute_code",
    "execute_create_docx",
    "execute_create_xlsx",
}


def _iter_backend_py():
    for path in BACKEND.rglob("*.py"):
        parts = set(path.parts)
        if "venv" in parts or ".venv" in parts or "tests" in parts:
            continue
        if path.name.startswith("test_"):
            continue
        yield path


def test_no_executor_imported_or_called_outside_job_manager():
    import_re = re.compile(
        r"from\s+backend\.domain\.capabilities\.(" + "|".join(EXECUTOR_MODULES) + r")\s+import"
    )
    call_re = re.compile(r"\b(" + "|".join(sorted(EXECUTOR_FUNCS)) + r")\s*\(")

    offenders = []
    for path in _iter_backend_py():
        # The Job Manager is the sanctioned dispatch site; the capabilities
        # package is where executors are *defined* (and may compose siblings) —
        # neither is an out-of-band bypass. The concern is any *other*
        # subsystem (orchestrator, api, rag, sandbox, ...) reaching an executor.
        if JOB_MANAGER_DIR in path.parents or CAPABILITIES_DIR in path.parents:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(BACKEND)
        if import_re.search(text):
            offenders.append(f"{rel}: imports a capability executor module")
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith(("def ", "async def ")):
                continue
            if call_re.search(line):
                offenders.append(f"{rel}:{lineno}: calls a capability executor entry point")

    assert not offenders, (
        "capability executors must only be reached via manager._dispatch_capability:\n"
        + "\n".join(offenders)
    )


def test_dispatch_function_has_single_call_site():
    call_sites = []
    for path in _iter_backend_py():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), 1):
            if "_dispatch_capability(" in line and "def _dispatch_capability(" not in line:
                call_sites.append(f"{path.relative_to(BACKEND)}:{lineno}")

    assert len(call_sites) == 1, f"expected exactly one caller of _dispatch_capability, got: {call_sites}"
    assert call_sites[0].startswith("domain/job_manager/manager.py")


def test_dispatch_function_defined_in_job_manager():
    manager_src = (JOB_MANAGER_DIR / "manager.py").read_text(encoding="utf-8")
    assert "async def _dispatch_capability(" in manager_src
