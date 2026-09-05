#!/usr/bin/env python3
"""Fail if a model identifier from config/resources.yaml appears in backend/
outside config/resources.yaml itself or backend/config.py.

Implements tasks/2-configuration-loading.md §7 Requirement 6 and
AGENTS.md §6 rule 3: capabilities/application code reference resource
*types* (reasoning, code_generation, vision, embedding) — model identifiers
live only in config/resources.yaml.

Usage:
    python scripts/check_no_hardcoded_models.py

Exits 0 if clean, non-zero (and prints each offending file/line) otherwise.
"""

from __future__ import annotations

import pathlib
import sys

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
RESOURCES_FILE = REPO_ROOT / "config" / "resources.yaml"
BACKEND_DIR = REPO_ROOT / "backend"

ALLOWED_FILES = {
    BACKEND_DIR / "config.py",
    # Asserts the loader surfaces the documented values from config/resources.yaml —
    # a legitimate reference to the string, not a hardcoded model dependency.
    BACKEND_DIR / "tests" / "test_config.py",
}
EXCLUDED_DIRS = {".venv", "__pycache__", ".pytest_cache"}


def _load_model_names() -> list[str]:
    with RESOURCES_FILE.open() as fh:
        data = yaml.safe_load(fh)
    return [entry["model"] for entry in data["resources"].values()]


def main() -> int:
    model_names = _load_model_names()
    violations: list[str] = []

    for path in BACKEND_DIR.rglob("*.py"):
        if path in ALLOWED_FILES:
            continue
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        text = path.read_text(errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for model_name in model_names:
                if model_name in line:
                    violations.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: found '{model_name}'")

    if violations:
        print("hardcoded model name(s) found outside config/resources.yaml and backend/config.py:", file=sys.stderr)
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        return 1

    print("no hardcoded model names found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
