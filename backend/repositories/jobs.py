"""
Repository for Job, JobStep, CapabilityExecution, and ModelExecution entities.

Handles CRUD operations for jobs and their sub-records.
"""

from datetime import datetime, timezone
from typing import List, Optional

from backend.utils.ids import new_id
from backend.repositories.db import (
    get_connection,
    row_to_dict,
    NotFoundError,
    ConstraintError,
)


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# Job operations

def create_job(
    conversation_id: str,
    input_message: str,
    status: str = "created",
) -> str:
    """
    Create a new job.

    Args:
        conversation_id: The conversation UUID.
        input_message: The triggering user message.
        status: Initial status ('created', 'running', 'completed', 'failed').

    Returns:
        The new job_id.

    Raises:
        ConstraintError: If conversation doesn't exist or status is invalid.
    """
    valid_statuses = ("created", "running", "completed", "failed")
    if status not in valid_statuses:
        raise ConstraintError(f"Invalid status: {status}. Must be one of {valid_statuses}")

    job_id = new_id()
    now = _now_iso()

    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO jobs (
                job_id, conversation_id, status, input_message,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (job_id, conversation_id, status, input_message, now, now),
        )
        conn.commit()

        if cursor.rowcount == 0:
            raise ConstraintError(f"Conversation not found: {conversation_id}")
    except sqlite3.IntegrityError as e:
        raise ConstraintError(f"Failed to create job: {e}") from e
    finally:
        conn.close()

    return job_id


def get_job(job_id: str) -> Optional[dict]:
    """
    Get a job by ID.

    Args:
        job_id: The job UUID.

    Returns:
        Job dict or None if not found.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?",
            (job_id,),
        )
        row = cursor.fetchone()
        return row_to_dict(row) if row else None
    finally:
        conn.close()


def update_job(
    job_id: str,
    status: Optional[str] = None,
    final_message: Optional[str] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    completed_at: Optional[str] = None,
) -> bool:
    """
    Update job fields.

    Args:
        job_id: The job UUID.
        status: New status.
        final_message: Final response message.
        error_code: Error code if failed.
        error_message: Error message if failed.
        completed_at: Completion timestamp (ISO-8601).

    Returns:
        True if updated, False if not found.

    Raises:
        ConstraintError: If status is invalid.
    """
    if status is not None:
        valid_statuses = ("created", "running", "completed", "failed")
        if status not in valid_statuses:
            raise ConstraintError(f"Invalid status: {status}. Must be one of {valid_statuses}")

    updates = []
    params = []

    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if final_message is not None:
        updates.append("final_message = ?")
        params.append(final_message)
    if error_code is not None:
        updates.append("error_code = ?")
        params.append(error_code)
    if error_message is not None:
        updates.append("error_message = ?")
        params.append(error_message)
    if completed_at is not None:
        updates.append("completed_at = ?")
        params.append(completed_at)

    if not updates:
        return False

    updates.append("updated_at = ?")
    params.append(_now_iso())
    params.append(job_id)

    conn = get_connection()
    try:
        cursor = conn.execute(
            f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = ?",
            params,
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def list_jobs_by_status(status: str, limit: int = 100, offset: int = 0) -> List[dict]:
    """
    List jobs by status, ordered by created_at.

    Args:
        status: Job status to filter by.
        limit: Maximum number of jobs to return.
        offset: Number of jobs to skip.

    Returns:
        List of job dicts ordered by created_at ascending.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT * FROM jobs
            WHERE status = ?
            ORDER BY created_at ASC
            LIMIT ? OFFSET ?
            """,
            (status, limit, offset),
        )
        return [row_to_dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def list_jobs_by_conversation(conversation_id: str, limit: int = 100, offset: int = 0) -> List[dict]:
    """
    List jobs for a conversation, ordered by created_at.

    Args:
        conversation_id: The conversation UUID.
        limit: Maximum number of jobs to return.
        offset: Number of jobs to skip.

    Returns:
        List of job dicts ordered by created_at ascending.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT * FROM jobs
            WHERE conversation_id = ?
            ORDER BY created_at ASC
            LIMIT ? OFFSET ?
            """,
            (conversation_id, limit, offset),
        )
        return [row_to_dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


# JobStep operations

def add_job_step(
    job_id: str,
    sequence: int,
    kind: str,
    input_payload: str,
    capability_name: Optional[str] = None,
    status: str = "pending",
) -> str:
    """
    Add a job step.

    Args:
        job_id: The job UUID.
        sequence: Order within the job.
        kind: Step kind ('orchestrator_reasoning' or 'capability_invocation').
        input_payload: JSON input payload.
        capability_name: Capability name (required for capability_invocation).
        status: Initial status ('pending', 'running', 'succeeded', 'failed', 'denied').

    Returns:
        The new job_step_id.

    Raises:
        ConstraintError: If job doesn't exist or kind/status invalid.
    """
    valid_kinds = ("orchestrator_reasoning", "capability_invocation")
    if kind not in valid_kinds:
        raise ConstraintError(f"Invalid kind: {kind}. Must be one of {valid_kinds}")

    valid_statuses = ("pending", "running", "succeeded", "failed", "denied")
    if status not in valid_statuses:
        raise ConstraintError(f"Invalid status: {status}. Must be one of {valid_statuses}")

    if kind == "capability_invocation" and not capability_name:
        raise ConstraintError("capability_name required for capability_invocation kind")

    job_step_id = new_id()

    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO job_steps (
                job_step_id, job_id, sequence, kind, capability_name,
                status, input_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (job_step_id, job_id, sequence, kind, capability_name, status, input_payload),
        )
        conn.commit()

        if cursor.rowcount == 0:
            raise ConstraintError(f"Job not found: {job_id}")
    except sqlite3.IntegrityError as e:
        raise ConstraintError(f"Failed to add job step: {e}") from e
    finally:
        conn.close()

    return job_step_id


def get_job_step(job_step_id: str) -> Optional[dict]:
    """
    Get a job step by ID.

    Args:
        job_step_id: The job step UUID.

    Returns:
        Job step dict or None if not found.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM job_steps WHERE job_step_id = ?",
            (job_step_id,),
        )
        row = cursor.fetchone()
        return row_to_dict(row) if row else None
    finally:
        conn.close()


def update_job_step(
    job_step_id: str,
    status: Optional[str] = None,
    output_payload: Optional[str] = None,
    error_message: Optional[str] = None,
    started_at: Optional[str] = None,
    completed_at: Optional[str] = None,
) -> bool:
    """
    Update job step fields.

    Args:
        job_step_id: The job step UUID.
        status: New status.
        output_payload: JSON output payload.
        error_message: Error message if failed.
        started_at: Start timestamp.
        completed_at: Completion timestamp.

    Returns:
        True if updated, False if not found.

    Raises:
        ConstraintError: If status is invalid.
    """
    if status is not None:
        valid_statuses = ("pending", "running", "succeeded", "failed", "denied")
        if status not in valid_statuses:
            raise ConstraintError(f"Invalid status: {status}. Must be one of {valid_statuses}")

    updates = []
    params = []

    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if output_payload is not None:
        updates.append("output_payload = ?")
        params.append(output_payload)
    if error_message is not None:
        updates.append("error_message = ?")
        params.append(error_message)
    if started_at is not None:
        updates.append("started_at = ?")
        params.append(started_at)
    if completed_at is not None:
        updates.append("completed_at = ?")
        params.append(completed_at)

    if not updates:
        return False

    params.append(job_step_id)

    conn = get_connection()
    try:
        cursor = conn.execute(
            f"UPDATE job_steps SET {', '.join(updates)} WHERE job_step_id = ?",
            params,
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def list_job_steps(job_id: str) -> List[dict]:
    """
    List job steps for a job, ordered by sequence.

    Args:
        job_id: The job UUID.

    Returns:
        List of job step dicts ordered by sequence ascending.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT * FROM job_steps
            WHERE job_id = ?
            ORDER BY sequence ASC
            """,
            (job_id,),
        )
        return [row_to_dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


# CapabilityExecution operations

def add_capability_execution(
    job_step_id: str,
    capability_name: str,
    policy_decision: str,
    resource_type: Optional[str] = None,
    policy_reason: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> str:
    """
    Add a capability execution record.

    Args:
        job_step_id: The job step UUID.
        capability_name: Capability name.
        policy_decision: Policy decision ('allow' or 'deny').
        resource_type: Resource type if applicable.
        policy_reason: Reason for denial (required if denied).
        duration_ms: Execution duration in milliseconds.

    Returns:
        The new capability_execution_id.

    Raises:
        ConstraintError: If job_step doesn't exist or values invalid.
    """
    valid_decisions = ("allow", "deny")
    if policy_decision not in valid_decisions:
        raise ConstraintError(f"Invalid policy_decision: {policy_decision}. Must be one of {valid_decisions}")

    if policy_decision == "deny" and not policy_reason:
        raise ConstraintError("policy_reason required for deny decision")

    valid_resource_types = ("reasoning", "code_generation", "vision", "embedding", None)
    if resource_type not in valid_resource_types:
        raise ConstraintError(f"Invalid resource_type: {resource_type}")

    capability_execution_id = new_id()

    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO capability_executions (
                capability_execution_id, job_step_id, capability_name,
                resource_type, policy_decision, policy_reason, duration_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                capability_execution_id, job_step_id, capability_name,
                resource_type, policy_decision, policy_reason, duration_ms
            ),
        )
        conn.commit()

        if cursor.rowcount == 0:
            raise ConstraintError(f"Job step not found: {job_step_id}")
    except sqlite3.IntegrityError as e:
        raise ConstraintError(f"Failed to add capability execution: {e}") from e
    finally:
        conn.close()

    return capability_execution_id


def get_capability_execution(capability_execution_id: str) -> Optional[dict]:
    """
    Get a capability execution by ID.

    Args:
        capability_execution_id: The capability execution UUID.

    Returns:
        Capability execution dict or None if not found.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM capability_executions WHERE capability_execution_id = ?",
            (capability_execution_id,),
        )
        row = cursor.fetchone()
        return row_to_dict(row) if row else None
    finally:
        conn.close()


def list_capability_executions_by_job_step(job_step_id: str) -> List[dict]:
    """
    List capability executions for a job step.

    Args:
        job_step_id: The job step UUID.

    Returns:
        List of capability execution dicts.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM capability_executions WHERE job_step_id = ?",
            (job_step_id,),
        )
        return [row_to_dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


# ModelExecution operations

def add_model_execution(
    capability_execution_id: str,
    resource_type: str,
    model_identifier: str,
    runtime: str,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    duration_ms: Optional[int] = None,
    load_triggered: bool = False,
) -> str:
    """
    Add a model execution record.

    Args:
        capability_execution_id: The capability execution UUID.
        resource_type: Resource type.
        model_identifier: Model identifier (e.g., 'qwen3.5:9b').
        runtime: Runtime name (e.g., 'ollama').
        prompt_tokens: Number of prompt tokens.
        completion_tokens: Number of completion tokens.
        duration_ms: Execution duration in milliseconds.
        load_triggered: Whether this call triggered a fresh model load.

    Returns:
        The new model_execution_id.

    Raises:
        ConstraintError: If capability_execution doesn't exist.
    """
    model_execution_id = new_id()

    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO model_executions (
                model_execution_id, capability_execution_id, resource_type,
                model_identifier, runtime, prompt_tokens, completion_tokens,
                duration_ms, load_triggered
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                model_execution_id, capability_execution_id, resource_type,
                model_identifier, runtime, prompt_tokens, completion_tokens,
                duration_ms, 1 if load_triggered else 0
            ),
        )
        conn.commit()

        if cursor.rowcount == 0:
            raise ConstraintError(f"Capability execution not found: {capability_execution_id}")
    except sqlite3.IntegrityError as e:
        raise ConstraintError(f"Failed to add model execution: {e}") from e
    finally:
        conn.close()

    return model_execution_id


def get_model_execution(model_execution_id: str) -> Optional[dict]:
    """
    Get a model execution by ID.

    Args:
        model_execution_id: The model execution UUID.

    Returns:
        Model execution dict or None if not found.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM model_executions WHERE model_execution_id = ?",
            (model_execution_id,),
        )
        row = cursor.fetchone()
        return row_to_dict(row) if row else None
    finally:
        conn.close()


def list_model_executions_by_capability_execution(capability_execution_id: str) -> List[dict]:
    """
    List model executions for a capability execution.

    Args:
        capability_execution_id: The capability execution UUID.

    Returns:
        List of model execution dicts.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM model_executions WHERE capability_execution_id = ?",
            (capability_execution_id,),
        )
        return [row_to_dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


import sqlite3