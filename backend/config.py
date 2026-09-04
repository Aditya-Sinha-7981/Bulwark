"""Bootstrap configuration stub.

Task 1.a scope only: hardcoded constants needed to boot the process and
create data directories. Real YAML config loading (config/app.yaml) is
Task 2's responsibility.

# TODO(Task 2): replace this module with a validated `settings` object
# loaded from config/*.yaml per docs/configuration.md.
"""

import pathlib

HOST = "127.0.0.1"
PORT = 8000

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data"

DATA_SUBDIRS = [
    DATA_ROOT / "uploads",
    DATA_ROOT / "extraction",
    DATA_ROOT / "artifacts",
    DATA_ROOT / "sandbox",
    DATA_ROOT / "tmp",
    DATA_ROOT / "db",
    DATA_ROOT / "chroma",
]

CORS_ALLOW_ORIGINS = ["http://localhost:5173"]
