"""
Integration-tier tests per docs/testing.md "Sandbox tests" and Task 13 §8.
These require a running Docker daemon AND the built `bulwark-sandbox:latest` image:

    docker build -t bulwark-sandbox:latest ./sandbox
    cd backend && pytest tests/test_sandbox.py -v

Per Task 13 §10 "Known Risks" ("Docker-on-CI... may be integration-tier, skipped
where Docker is absent"), this module skips cleanly (not silently -- it prints a
skip reason) when Docker isn't available, rather than failing or being omitted
from the suite.
"""

from __future__ import annotations

import subprocess
import textwrap
import time
from pathlib import Path

import pytest

from backend.domain.sandbox.docker_executor import (
    IMAGE_NAME,
    is_docker_available,
    run_in_sandbox,
)

DOCKER_AVAILABLE = is_docker_available()


def _image_built() -> bool:
    if not DOCKER_AVAILABLE:
        return False
    proc = subprocess.run(
        ["docker", "image", "inspect", IMAGE_NAME],
        capture_output=True,
    )
    return proc.returncode == 0


IMAGE_BUILT = _image_built()

pytestmark = pytest.mark.skipif(
    not (DOCKER_AVAILABLE and IMAGE_BUILT),
    reason=(
        "Docker daemon and/or bulwark-sandbox:latest image not available in this "
        "environment. Build with `docker build -t bulwark-sandbox:latest ./sandbox` "
        "and ensure Docker Desktop is running, then re-run."
    ),
)


@pytest.fixture
def sandbox_root(tmp_path: Path) -> Path:
    root = tmp_path / "sandbox"
    root.mkdir()
    return root


def _running_containers_named(prefix: str) -> list:
    proc = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name={prefix}", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    )
    return [line for line in proc.stdout.splitlines() if line.strip()]


class TestKnownGoodScript:
    def test_correct_stdout_and_exit_zero(self, sandbox_root):
        code = "print('hello from sandbox')"
        result = run_in_sandbox(code, sandbox_root=sandbox_root)

        assert result.exit_code == 0
        assert "hello from sandbox" in result.stdout
        assert result.timed_out is False

    def test_container_and_tempdir_cleaned_up(self, sandbox_root):
        code = "print('cleanup check')"
        result = run_in_sandbox(code, sandbox_root=sandbox_root)

        exec_dir = sandbox_root / result.execution_id
        assert not exec_dir.exists(), "sandbox temp dir must be removed after the run"

        leftover = _running_containers_named(f"bulwark-sbx-{result.execution_id}")
        assert leftover == [], f"container(s) left behind: {leftover}"


class TestKnownFailingScript:
    def test_nonzero_exit_and_captured_stderr(self, sandbox_root):
        code = textwrap.dedent(
            """
            raise ValueError("deliberate failure for test_sandbox")
            """
        )
        result = run_in_sandbox(code, sandbox_root=sandbox_root)

        assert result.exit_code != 0
        assert result.exit_code is not None
        assert "ValueError" in result.stderr
        assert "deliberate failure" in result.stderr
        assert result.timed_out is False


class TestNetworkDenial:
    def test_outbound_call_fails_under_network_none(self, sandbox_root):
        code = textwrap.dedent(
            """
            import urllib.request
            import sys
            try:
                urllib.request.urlopen("http://example.com", timeout=5)
                print("UNEXPECTED: network call succeeded")
            except Exception as e:
                print(f"EXPECTED_FAILURE: {type(e).__name__}: {e}")
                sys.exit(1)
            """
        )
        result = run_in_sandbox(code, sandbox_root=sandbox_root, timeout_seconds=15)

        # The outbound call must fail -- proof of --network none.
        assert result.exit_code != 0
        assert "EXPECTED_FAILURE" in result.stdout or "EXPECTED_FAILURE" in result.stderr
        assert "UNEXPECTED" not in result.stdout


class TestTimeout:
    def test_runaway_script_hard_killed(self, sandbox_root):
        code = "import time\ntime.sleep(9999)\n"
        start = time.monotonic()
        result = run_in_sandbox(code, sandbox_root=sandbox_root, timeout_seconds=3)
        elapsed = time.monotonic() - start

        assert result.timed_out is True
        # Should not have waited anywhere near the full sleep duration.
        assert elapsed < 30

        exec_dir = sandbox_root / result.execution_id
        assert not exec_dir.exists()

        leftover = _running_containers_named(f"bulwark-sbx-{result.execution_id}")
        assert leftover == [], f"container(s) left behind after timeout: {leftover}"


class TestReadOnlyFilesystem:
    def test_write_outside_output_dir_fails(self, sandbox_root):
        code = textwrap.dedent(
            """
            try:
                with open("/workspace/forbidden.txt", "w") as f:
                    f.write("should not be allowed")
                print("UNEXPECTED: write succeeded")
            except Exception as e:
                print(f"EXPECTED_READONLY_FAILURE: {type(e).__name__}")
                raise
            """
        )
        result = run_in_sandbox(code, sandbox_root=sandbox_root)

        assert result.exit_code != 0
        assert "EXPECTED_READONLY_FAILURE" in result.stdout
        assert "UNEXPECTED" not in result.stdout


class TestOutputFileCollection:
    def test_file_written_to_output_dir_is_collected(self, sandbox_root):
        code = textwrap.dedent(
            """
            with open("/workspace/output/result.txt", "w") as f:
                f.write("produced by sandbox")
            print("wrote output file")
            """
        )
        result = run_in_sandbox(code, sandbox_root=sandbox_root)

        assert result.exit_code == 0
        assert "result.txt" in result.output_files


class TestImportError:
    def test_non_baked_package_surfaces_as_import_error(self, sandbox_root):
        code = "import this_package_does_not_exist_anywhere\n"
        result = run_in_sandbox(code, sandbox_root=sandbox_root)

        assert result.exit_code != 0
        assert "ModuleNotFoundError" in result.stderr or "ImportError" in result.stderr


class TestOutputTruncation:
    def test_stdout_truncated_to_max_output_bytes(self, sandbox_root):
        code = "print('x' * 200000)"
        result = run_in_sandbox(code, sandbox_root=sandbox_root, max_output_bytes=1024)

        assert len(result.stdout.encode("utf-8")) <= 1024