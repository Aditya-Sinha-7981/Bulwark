"""
Repository package for Bulwark.

Provides SQLite data access for all entities in data-model.md.
"""

from backend.repositories import conversations, jobs, documents, artifacts
from backend.repositories import audit_events, knowledge_base, resource_state
from backend.repositories.db import (
    get_connection,
    transaction,
    row_to_dict,
    DatabaseError,
    NotFoundError,
    ConstraintError,
)

__all__ = [
    "conversations",
    "jobs",
    "documents",
    "artifacts",
    "audit_events",
    "knowledge_base",
    "resource_state",
    "get_connection",
    "transaction",
    "row_to_dict",
    "DatabaseError",
    "NotFoundError",
    "ConstraintError",
]