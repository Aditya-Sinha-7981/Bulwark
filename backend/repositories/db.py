"""
Shared SQLite connection helper for Bulwark repositories.

Provides a connection factory with foreign keys enabled, row factory for
mapping-style rows, and a context-managed transaction helper.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, Optional

from backend.config import DATA_ROOT


class DatabaseError(Exception):
    """Base exception for database errors."""
    pass


class NotFoundError(DatabaseError):
    """Raised when a requested row is not found."""
    pass


class ConstraintError(DatabaseError):
    """Raised when a constraint violation occurs (unique, FK, etc.)."""
    pass


def get_db_path() -> Path:
    """Get the database path from settings or use fallback."""
    return DATA_ROOT / "db" / "app.db"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    Create a database connection with foreign keys enabled and row factory.

    Args:
        db_path: Optional custom database path. Uses default if not provided.

    Returns:
        Configured SQLite connection.

    Raises:
        DatabaseError: If database file or directory doesn't exist.
    """
    path = db_path or get_db_path()

    if not path.exists():
        raise DatabaseError(
            f"Database file not found at {path}. "
            f"Run 'python scripts/init_db.py' to initialize the database."
        )

    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for database transactions.

    Commits on success, rolls back on exception.

    Args:
        conn: An open SQLite connection.

    Yields:
        The same connection for use within the transaction.

    Raises:
        DatabaseError: If transaction fails.
    """
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise DatabaseError(f"Transaction failed: {e}") from e


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert a sqlite3.Row to a plain dictionary."""
    return dict(row)


def execute_script(conn: sqlite3.Connection, script: str) -> None:
    """Execute a multi-statement SQL script."""
    conn.executescript(script)