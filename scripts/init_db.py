#!/usr/bin/env python3
"""
Database schema initialization script for Bulwark.

Creates all tables and indexes from docs/data-model.md idempotently.
Safe to run repeatedly against an already-initialized database without data loss.
"""

import sqlite3
import sys
from pathlib import Path


def get_db_path() -> Path:
    """Get the database path, creating parent directories if needed."""
    repo_root = Path(__file__).resolve().parent.parent
    db_path = repo_root / "data" / "db" / "app.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Create a database connection with foreign keys enabled."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    """Create all tables from docs/data-model.md."""
    cursor = conn.cursor()

    # conversations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            conversation_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            message_id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user', 'orchestrator')),
            content TEXT NOT NULL,
            job_id TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations (conversation_id) ON DELETE CASCADE,
            FOREIGN KEY (job_id) REFERENCES jobs (job_id) ON DELETE SET NULL
        )
    """)

    # jobs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('created', 'running', 'completed', 'failed')),
            input_message TEXT NOT NULL,
            final_message TEXT,
            error_code TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (conversation_id) REFERENCES conversations (conversation_id) ON DELETE CASCADE
        )
    """)

    # job_steps table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_steps (
            job_step_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('orchestrator_reasoning', 'capability_invocation')),
            capability_name TEXT,
            status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'denied')),
            input_payload TEXT NOT NULL,
            output_payload TEXT,
            error_message TEXT,
            started_at TEXT,
            completed_at TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs (job_id) ON DELETE CASCADE
        )
    """)

    # documents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            document_id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            storage_path TEXT NOT NULL,
            uploaded_at TEXT NOT NULL
        )
    """)

    # artifacts table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS artifacts (
            artifact_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            type TEXT NOT NULL CHECK (type IN ('docx', 'xlsx', 'pptx')),
            filename TEXT NOT NULL,
            storage_path TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (job_id) REFERENCES jobs (job_id) ON DELETE CASCADE
        )
    """)

    # capability_executions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS capability_executions (
            capability_execution_id TEXT PRIMARY KEY,
            job_step_id TEXT NOT NULL,
            capability_name TEXT NOT NULL,
            resource_type TEXT CHECK (resource_type IN ('reasoning', 'code_generation', 'vision', 'embedding')),
            policy_decision TEXT NOT NULL CHECK (policy_decision IN ('allow', 'deny')),
            policy_reason TEXT,
            duration_ms INTEGER,
            FOREIGN KEY (job_step_id) REFERENCES job_steps (job_step_id) ON DELETE CASCADE
        )
    """)

    # model_executions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS model_executions (
            model_execution_id TEXT PRIMARY KEY,
            capability_execution_id TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            model_identifier TEXT NOT NULL,
            runtime TEXT NOT NULL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            duration_ms INTEGER,
            load_triggered INTEGER NOT NULL CHECK (load_triggered IN (0, 1)),
            FOREIGN KEY (capability_execution_id) REFERENCES capability_executions (capability_execution_id) ON DELETE CASCADE
        )
    """)

    # audit_events table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_events (
            event_id TEXT PRIMARY KEY,
            job_id TEXT,
            event_type TEXT NOT NULL,
            component TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            payload TEXT NOT NULL,
            FOREIGN KEY (job_id) REFERENCES jobs (job_id) ON DELETE CASCADE
        )
    """)

    # resource_state table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resource_state (
            resource_type TEXT PRIMARY KEY,
            model_identifier TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('unloaded', 'loading', 'loaded')),
            loaded_at TEXT,
            last_used_at TEXT
        )
    """)

    # knowledge_base_documents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_base_documents (
            kb_document_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            category TEXT,
            status TEXT NOT NULL CHECK (status IN ('ingesting', 'ready', 'failed')),
            storage_path TEXT NOT NULL,
            chunk_count INTEGER NOT NULL,
            ingested_at TEXT
        )
    """)

    conn.commit()


def create_indexes(conn: sqlite3.Connection) -> None:
    """Create all indexes from docs/data-model.md."""
    cursor = conn.cursor()

    # messages index
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
        ON messages (conversation_id, created_at)
    """)

    # jobs indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_jobs_conversation_created
        ON jobs (conversation_id, created_at)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_jobs_status
        ON jobs (status)
    """)

    # job_steps index
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_steps_job_sequence
        ON job_steps (job_id, sequence)
    """)

    # artifacts index
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_artifacts_job_id
        ON artifacts (job_id)
    """)

    # audit_events indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_events_job_timestamp
        ON audit_events (job_id, timestamp)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_events_type_timestamp
        ON audit_events (event_type, timestamp)
    """)

    conn.commit()


def verify_schema(conn: sqlite3.Connection) -> None:
    """Verify all tables and indexes were created."""
    cursor = conn.cursor()

    # Check tables
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """)
    tables = [row[0] for row in cursor.fetchall()]
    expected_tables = [
        'conversations', 'messages', 'jobs', 'job_steps',
        'documents', 'artifacts', 'capability_executions',
        'model_executions', 'audit_events', 'resource_state',
        'knowledge_base_documents'
    ]

    print("Tables found:")
    for table in tables:
        print(f"  - {table}")

    missing_tables = set(expected_tables) - set(tables)
    if missing_tables:
        print(f"\nWARNING: Missing tables: {missing_tables}")
    else:
        print("\nAll expected tables present.")

    # Check indexes
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='index' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """)
    indexes = [row[0] for row in cursor.fetchall()]
    expected_indexes = [
        'idx_messages_conversation_created',
        'idx_jobs_conversation_created',
        'idx_jobs_status',
        'idx_job_steps_job_sequence',
        'idx_artifacts_job_id',
        'idx_audit_events_job_timestamp',
        'idx_audit_events_type_timestamp'
    ]

    print("\nIndexes found:")
    for index in indexes:
        print(f"  - {index}")

    missing_indexes = set(expected_indexes) - set(indexes)
    if missing_indexes:
        print(f"\nWARNING: Missing indexes: {missing_indexes}")
    else:
        print("\nAll expected indexes present.")


def main() -> int:
    """Main entry point."""
    db_path = get_db_path()
    print(f"Initializing database at: {db_path}")

    conn = get_connection(db_path)
    try:
        create_tables(conn)
        create_indexes(conn)
        verify_schema(conn)
        print("\nDatabase initialization complete.")
        return 0
    except Exception as e:
        print(f"Error initializing database: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())