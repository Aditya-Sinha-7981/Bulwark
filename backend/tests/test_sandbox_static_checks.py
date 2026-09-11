"""
Static source checks required by Task 13 acceptance criteria:
  - No sys.platform / os.name branch anywhere in the sandbox/execute_code code
    (identical behavior on macOS and Windows -- ADR-05).
  - Only docker_executor.py (and, transitively, execute_code.py which imports it)
    invoke Docker -- generate_code.py must not.
  - No Docker SDK import anywhere (subprocess/CLI only, per Task 13 §11).
"""

from __future__ import annotations

import re
from pathlib import Path

_TRIPLE_QUOTED_BLOCK = re.compile(r'("""|\'\'\')(.*?)(\1)', re.DOTALL)


def _strip_docstrings_and_comments(source: str) -> str:
    """Removes triple-quoted string blocks (docstrings) and `#` comments so static
    checks only look at actual executable code, not prose that legitimately
    *mentions* a forbidden pattern by name while explaining the rule."""
    without_triple_quoted = _TRIPLE_QUOTED_BLOCK.sub("", source)
    lines = []
    for line in without_triple_quoted.splitlines():
        code_part = line.split("#", 1)[0]
        lines.append(code_part)
    return "\n".join(lines)

THIS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = THIS_DIR.parent

FILES_UNDER_TEST = [
    BACKEND_DIR / "domain" / "sandbox" / "docker_executor.py",
    BACKEND_DIR / "domain" / "capabilities" / "execute_code.py",
    BACKEND_DIR / "domain" / "capabilities" / "generate_code.py",
]


def _read(path: Path) -> str:
    return path.read_text()


class TestNoOSSpecificBranching:
    def test_no_sys_platform_or_os_name_checks(self):
        """
        Looks for actual *use* of sys.platform / os.name as a branching condition
        (e.g. `sys.platform == "win32"`, `if os.name == "nt":`), not mere textual
        mentions -- this file's own docstrings legitimately reference the rule by
        name ("no sys.platform / os.name branch") without violating it.
        """
        offenders = []
        for f in FILES_UNDER_TEST:
            code_only = _strip_docstrings_and_comments(_read(f))
            for lineno, line in enumerate(code_only.splitlines(), start=1):
                if "sys.platform" in line or "os.name" in line:
                    offenders.append(f"{f}:{lineno}: {line.strip()}")
        assert offenders == [], f"OS-specific branching found: {offenders}"


class TestNoDockerSDK:
    def test_no_docker_sdk_import(self):
        offenders = []
        for f in FILES_UNDER_TEST:
            code_only = _strip_docstrings_and_comments(_read(f))
            if "import docker" in code_only or "from docker" in code_only:
                offenders.append(str(f))
        assert offenders == [], f"Docker SDK import found (must be CLI/subprocess only): {offenders}"


class TestDockerInvocationIsolated:
    def test_only_docker_executor_calls_subprocess_with_docker(self):
        executor_code = _strip_docstrings_and_comments(
            _read(BACKEND_DIR / "domain" / "sandbox" / "docker_executor.py")
        )
        assert '"docker"' in executor_code or "'docker'" in executor_code

        generate_code_code = _strip_docstrings_and_comments(
            _read(BACKEND_DIR / "domain" / "capabilities" / "generate_code.py")
        )
        assert "docker" not in generate_code_code.lower(), (
            "generate_code.py must never invoke Docker -- it only generates code, "
            "it does not execute it."
        )

        execute_code_code = _strip_docstrings_and_comments(
            _read(BACKEND_DIR / "domain" / "capabilities" / "execute_code.py")
        )
        # execute_code.py is allowed to *mention* docker only via importing
        # docker_executor -- it must not build its own `docker run` command directly.
        assert '"docker", "run"' not in execute_code_code
        assert "subprocess" not in execute_code_code, (
            "execute_code.py must delegate all subprocess/Docker calls to "
            "docker_executor.py, not invoke subprocess itself."
        )