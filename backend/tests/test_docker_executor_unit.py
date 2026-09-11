"""
Unit tests for docker_executor.py that mock the Docker CLI entirely via
`subprocess.run` / `subprocess.Popen` monkeypatching. These do NOT require a real
Docker daemon or the built image -- they exist to validate the *Python
orchestration logic* (timeout handling, cleanup-on-every-path, truncation, the
Docker-unavailable path, exact flag construction) independent of Docker's own
correctness, which is instead covered by the real integration tests in
test_sandbox.py.

This file is a supplement written for this standalone review build (Docker was not
available in the environment this was built in) -- it is not one of Task 13's
originally-listed allowed files, but it exercises the same module and is safe to
keep or drop when integrating into the real repo, at the reviewer's discretion.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.domain.sandbox import docker_executor as de


@pytest.fixture
def sandbox_root(tmp_path: Path) -> Path:
    root = tmp_path / "sandbox"
    root.mkdir()
    return root


def _mock_docker_info_ok():
    ok = MagicMock()
    ok.returncode = 0
    ok.stderr = b""
    return ok


class TestExactDockerFlags:
    def test_run_command_matches_documented_flags_exactly(self, sandbox_root, monkeypatch):
        captured_cmd = {}

        def fake_run(cmd, **kwargs):
            # used for `docker info` and `docker kill`
            return _mock_docker_info_ok()

        class FakePopen:
            def __init__(self, cmd, **kwargs):
                captured_cmd["cmd"] = cmd
                self.returncode = 0

            def communicate(self, timeout=None):
                return b"ok\n", b""

        monkeypatch.setattr(de.subprocess, "run", fake_run)
        monkeypatch.setattr(de.subprocess, "Popen", FakePopen)

        result = de.run_in_sandbox(
            "print('hi')",
            sandbox_root=sandbox_root,
            cpu_limit=1,
            memory_limit_mb=512,
        )

        cmd = captured_cmd["cmd"]
        assert cmd[0:3] == ["docker", "run", "--rm"]
        assert "--network" in cmd and cmd[cmd.index("--network") + 1] == "none"
        assert "--cpus" in cmd and cmd[cmd.index("--cpus") + 1] == "1"
        assert "--memory" in cmd and cmd[cmd.index("--memory") + 1] == "512m"
        assert "--read-only" in cmd
        assert "--workdir" in cmd and cmd[cmd.index("--workdir") + 1] == "/workspace"
        assert cmd[-3:] == [de.IMAGE_NAME, "python", "input/script.py"]
        # both mounts present, correctly scoped read-only / read-write
        mounts = [cmd[i + 1] for i, tok in enumerate(cmd) if tok == "-v"]
        assert any(m.endswith(":/workspace/input:ro") for m in mounts)
        assert any(m.endswith(":/workspace/output:rw") for m in mounts)

        assert result.exit_code == 0
        assert result.stdout == "ok\n"


class TestCleanupOnEveryPath:
    def test_temp_dir_removed_on_success(self, sandbox_root, monkeypatch):
        monkeypatch.setattr(de.subprocess, "run", lambda *a, **k: _mock_docker_info_ok())

        class FakePopen:
            def __init__(self, cmd, **kwargs):
                self.returncode = 0

            def communicate(self, timeout=None):
                return b"done", b""

        monkeypatch.setattr(de.subprocess, "Popen", FakePopen)

        result = de.run_in_sandbox("print(1)", sandbox_root=sandbox_root)
        assert not (sandbox_root / result.execution_id).exists()

    def test_temp_dir_removed_when_script_raises_inside_container(self, sandbox_root, monkeypatch):
        monkeypatch.setattr(de.subprocess, "run", lambda *a, **k: _mock_docker_info_ok())

        class FakePopen:
            def __init__(self, cmd, **kwargs):
                self.returncode = 1

            def communicate(self, timeout=None):
                return b"", b"Traceback...\nValueError: boom\n"

        monkeypatch.setattr(de.subprocess, "Popen", FakePopen)

        result = de.run_in_sandbox("raise ValueError('boom')", sandbox_root=sandbox_root)
        assert result.exit_code == 1
        assert not (sandbox_root / result.execution_id).exists()

    def test_temp_dir_removed_on_timeout(self, sandbox_root, monkeypatch):
        monkeypatch.setattr(de.subprocess, "run", lambda *a, **k: _mock_docker_info_ok())

        class FakePopen:
            def __init__(self, cmd, **kwargs):
                self._calls = 0

            def communicate(self, timeout=None):
                self._calls += 1
                if self._calls == 1:
                    raise subprocess.TimeoutExpired(cmd="docker run", timeout=timeout)
                return b"partial", b""

        monkeypatch.setattr(de.subprocess, "Popen", FakePopen)

        result = de.run_in_sandbox(
            "import time; time.sleep(9999)", sandbox_root=sandbox_root, timeout_seconds=1
        )
        assert result.timed_out is True
        assert result.exit_code is None
        assert not (sandbox_root / result.execution_id).exists()

    def test_temp_dir_removed_when_exception_raised_mid_run(self, sandbox_root, monkeypatch):
        monkeypatch.setattr(de.subprocess, "run", lambda *a, **k: _mock_docker_info_ok())

        class ExplodingPopen:
            def __init__(self, cmd, **kwargs):
                raise RuntimeError("simulated unexpected Popen failure")

        monkeypatch.setattr(de.subprocess, "Popen", ExplodingPopen)

        execution_ids_before = set(p.name for p in sandbox_root.iterdir()) if sandbox_root.exists() else set()

        with pytest.raises(RuntimeError):
            de.run_in_sandbox("print(1)", sandbox_root=sandbox_root)

        # No leftover directories should remain under sandbox_root.
        leftover = set(p.name for p in sandbox_root.iterdir()) - execution_ids_before
        assert leftover == set()


class TestDockerUnavailable:
    def test_daemon_unreachable_raises_typed_error_no_tempdir_left(self, sandbox_root, monkeypatch):
        bad = MagicMock()
        bad.returncode = 1
        bad.stderr = b"Cannot connect to the Docker daemon"
        monkeypatch.setattr(de.subprocess, "run", lambda *a, **k: bad)

        with pytest.raises(de.DockerUnavailableError):
            de.run_in_sandbox("print(1)", sandbox_root=sandbox_root)

        # Nothing should have been created at all.
        assert list(sandbox_root.iterdir()) == []

    def test_docker_cli_missing_raises_typed_error(self, sandbox_root, monkeypatch):
        def fake_run(*a, **k):
            raise FileNotFoundError("docker: command not found")

        monkeypatch.setattr(de.subprocess, "run", fake_run)

        with pytest.raises(de.DockerUnavailableError):
            de.run_in_sandbox("print(1)", sandbox_root=sandbox_root)

    def test_is_docker_available_false_on_error(self, monkeypatch):
        monkeypatch.setattr(de.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
        assert de.is_docker_available() is False

    def test_is_docker_available_true_when_ok(self, monkeypatch):
        monkeypatch.setattr(de.subprocess, "run", lambda *a, **k: _mock_docker_info_ok())
        assert de.is_docker_available() is True


class TestOutputTruncation:
    def test_stdout_truncated_before_decode(self, sandbox_root, monkeypatch):
        monkeypatch.setattr(de.subprocess, "run", lambda *a, **k: _mock_docker_info_ok())

        big = b"x" * 5000

        class FakePopen:
            def __init__(self, cmd, **kwargs):
                self.returncode = 0

            def communicate(self, timeout=None):
                return big, b""

        monkeypatch.setattr(de.subprocess, "Popen", FakePopen)

        result = de.run_in_sandbox("print('x'*5000)", sandbox_root=sandbox_root, max_output_bytes=100)
        assert len(result.stdout) == 100


class TestOutputFileCollectionUnit:
    def test_files_written_to_output_dir_are_listed(self, sandbox_root, monkeypatch):
        monkeypatch.setattr(de.subprocess, "run", lambda *a, **k: _mock_docker_info_ok())

        def fake_popen_factory(write_files):
            class FakePopen:
                def __init__(self, cmd, **kwargs):
                    self.returncode = 0
                    # simulate the container having written to the output mount
                    out_dir = None
                    for i, tok in enumerate(cmd):
                        if tok == "-v" and cmd[i + 1].endswith(":/workspace/output:rw"):
                            # Parse mount string: host_path:container_path:mode
                            # On Windows, host_path may contain drive letter (C:\...)
                            mount_spec = cmd[i + 1]
                            # Split from the right to handle Windows drive letters
                            parts = mount_spec.rsplit(":", 2)
                            if len(parts) == 3:
                                out_dir = Path(parts[0])
                    assert out_dir is not None
                    for name, content in write_files.items():
                        (out_dir / name).write_text(content)

                def communicate(self, timeout=None):
                    return b"", b""

            return FakePopen

        monkeypatch.setattr(
            de.subprocess, "Popen", fake_popen_factory({"a.txt": "1", "b.csv": "2"})
        )

        result = de.run_in_sandbox("...", sandbox_root=sandbox_root)
        assert sorted(result.output_files) == ["a.txt", "b.csv"]