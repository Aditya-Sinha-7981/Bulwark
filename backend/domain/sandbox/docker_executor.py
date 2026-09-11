"""Docker sandbox executor (Task 13).

Implements the container lifecycle per docs/sandbox.md "Container lifecycle" (steps 1-7).

Locked constraints this module respects:
  - Docker is driven via the CLI (`subprocess`) only — no Docker SDK dependency
    (Task 13 §11, "Resolved (finalisation decision)").
  - `docker run` flags are exactly those in docs/sandbox.md / docs/capabilities.md#execute_code:
        --rm --network none --cpus <cpu_limit> --memory <memory_limit_mb>m --read-only
        -v {execution_id}/input:/workspace/input:ro
        -v {execution_id}/output:/workspace/output:rw
        --workdir /workspace
        bulwark-sandbox:latest
        python input/script.py
  - No OS-specific branch (`sys.platform` / `os.name`) anywhere in this file — identical
    behavior on macOS and Windows (ADR-05).
  - No runtime package installation path exists anywhere in this module.
  - This module returns *raw* results (including raw candidate output filenames, not
    artifact_ids) — the artifact_id substitution is a separate, downstream concern
    (Task 15), never performed here.

*** KNOWN OPEN ISSUE — flagged for the human reviewer, not silently resolved ***
docs/sandbox.md's own step ordering says: "6. Collect files written to output/ as
candidates" then "7. Clean up: remove the temp directory tree after results are
captured." Read literally, cleanup happens inside this same function call, before
Task 15 (the eventual Artifact-conversion step) would have any chance to read the
*bytes* of those output files — only their filenames survive past this call.
That's fine for this task's own scope (Task 13 explicitly must not create Artifacts),
but it means Task 15 cannot do its job unless one of the following is decided
upstream, which this build does NOT decide on its own:
  (a) cleanup is deferred — this module exposes execution_id/output_dir and a
      *separate* `cleanup_execution()` call, and the Job Manager calls cleanup only
      after Task 15 has copied whatever it needs into data/artifacts/, or
  (b) this module copies output bytes (not just names) into the returned result
      (e.g. base64) so the caller never needs the temp dir to still exist.
This build implements sandbox.md literally (cleanup happens here, inside
`run_in_sandbox`, in a `finally` block) because that is what's authoritative for
Task 13's own scope, but SEE THE WORK LOG for this flagged as an item that needs an
explicit decision before Task 15 is implemented.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from backend.config import settings
from backend.utils.paths import SANDBOX_ROOT

IMAGE_NAME = "bulwark-sandbox:latest"

# Grace period given to a killed container to flush stdout/stderr and exit before we
# give up waiting and forcibly kill our own subprocess handle. Not part of the
# docs/sandbox.md contract's timeout value itself — purely internal bookkeeping so a
# stuck `docker kill` can't hang the calling process forever.
_KILL_DRAIN_SECONDS = 10
_DOCKER_INFO_TIMEOUT_SECONDS = 10


class DockerUnavailableError(RuntimeError):
    """Raised when the Docker CLI/daemon cannot be reached.

    Callers (execute_code.py) MUST catch this and translate it into a structured
    failed capability result — this must never propagate as an unhandled crash
    (docs/sandbox.md "Failure recovery"; Task 13 acceptance criteria).
    """


@dataclass
class SandboxResult:
    execution_id: str
    stdout: str
    stderr: str
    exit_code: Optional[int]
    timed_out: bool
    output_files: List[str]  # raw filenames under output/, NOT artifact_ids


def _truncate(data: bytes, max_bytes: int) -> str:
    """Truncates raw process output to `max_bytes` before decoding, per
    config/capabilities.yaml `execute_code.max_output_bytes`."""
    if max_bytes is not None and len(data) > max_bytes:
        data = data[:max_bytes]
    return data.decode("utf-8", errors="replace")


def _check_docker_available() -> None:
    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=_DOCKER_INFO_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise DockerUnavailableError(f"Docker CLI unavailable: {exc}") from exc
    if proc.returncode != 0:
        stderr = proc.stderr.decode(errors="replace") if proc.stderr else ""
        raise DockerUnavailableError(f"Docker daemon unreachable: {stderr.strip()}")


def is_docker_available() -> bool:
    """Non-raising convenience check, mainly for tests deciding whether to
    skip the Docker-dependent integration suite."""
    try:
        _check_docker_available()
        return True
    except DockerUnavailableError:
        return False


def run_in_sandbox(
    code: str,
    input_files: Optional[List[str]] = None,
    *,
    sandbox_root: Path,
    cpu_limit: int = 1,
    memory_limit_mb: int = 512,
    timeout_seconds: int = 30,
    max_output_bytes: int = 65536,
    image: str = IMAGE_NAME,
) -> SandboxResult:
    """
    Executes `code` (a Python script) inside an isolated, network-denied Docker
    container, per docs/sandbox.md "Container lifecycle" steps 1-7.

    Raises DockerUnavailableError if the Docker daemon cannot be reached at all
    (before any container was attempted) — callers must catch this.

    Never raises for a failing *script* (non-zero exit, timeout, crash inside the
    container) — those are represented in the returned SandboxResult, per
    docs/sandbox.md "Failure recovery".
    """
    execution_id = str(uuid.uuid4())
    exec_dir = sandbox_root / execution_id
    input_dir = exec_dir / "input"
    output_dir = exec_dir / "output"

    stdout_bytes = b""
    stderr_bytes = b""
    exit_code: Optional[int] = None
    timed_out = False
    output_files: List[str] = []

    # Docker availability is checked BEFORE we touch the filesystem, so a
    # Docker-unavailable failure never leaves stray temp directories behind either.
    _check_docker_available()

    try:
        # Step 1: write the generated code to a fresh temp file.
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        script_path = input_dir / "script.py"
        script_path.write_text(code)

        # Step 2: copy any referenced input files into the same input directory.
        for raw_path in (input_files or []):
            src = Path(raw_path)
            if src.is_file():
                shutil.copy2(src, input_dir / src.name)
            # A referenced-but-missing input file is not treated as fatal at this
            # layer — it surfaces naturally as a runtime error *inside* the executed
            # script (e.g. FileNotFoundError -> non-zero exit), exactly like any
            # other execution failure. Resolving document_id -> real path is the
            # capability executor's job (execute_code.py), not this module's.

        # Step 3: run with EXACTLY the documented flags.
        container_name = f"bulwark-sbx-{execution_id}"
        cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--cpus", str(cpu_limit),
            "--memory", f"{memory_limit_mb}m",
            "--read-only",
            "-v", f"{input_dir.resolve()}:/workspace/input:ro",
            "-v", f"{output_dir.resolve()}:/workspace/output:rw",
            "--workdir", "/workspace",
            "--name", container_name,
            image,
            "python", "input/script.py",
        ]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            # `docker` disappeared between the availability check and the run —
            # rare, but must still be a structured failure, not a crash.
            raise DockerUnavailableError(f"Docker CLI not found: {exc}") from exc

        try:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout_seconds)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            # Step 4: hard-kill on expiry. Docker itself has no native per-run
            # timeout flag, so this is application-level orchestration around a
            # Docker-enforced isolation boundary (docs/sandbox.md "Timeout").
            timed_out = True
            subprocess.run(
                ["docker", "kill", container_name],
                capture_output=True,
                timeout=_DOCKER_INFO_TIMEOUT_SECONDS,
            )
            try:
                stdout_bytes, stderr_bytes = proc.communicate(timeout=_KILL_DRAIN_SECONDS)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout_bytes, stderr_bytes = proc.communicate()
            exit_code = None  # killed, not a normal exit — no meaningful exit code

        # Step 6: collect candidate output files (names only; bytes stay on disk
        # until cleanup below — see the module-level "KNOWN OPEN ISSUE" note).
        if output_dir.exists():
            output_files = sorted(p.name for p in output_dir.iterdir() if p.is_file())

        return SandboxResult(
            execution_id=execution_id,
            stdout=_truncate(stdout_bytes, max_output_bytes),
            stderr=_truncate(stderr_bytes, max_output_bytes),
            exit_code=exit_code,
            timed_out=timed_out,
            output_files=output_files,
        )
    finally:
        # Step 7: clean up on EVERY path (success, script failure, timeout, or any
        # exception raised above) — the container itself is already gone via --rm;
        # this removes the temp directory tree.
        if exec_dir.exists():
            shutil.rmtree(exec_dir, ignore_errors=True)