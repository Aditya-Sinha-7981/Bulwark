# Audit / Event Subsystem

## Principle

**AuditEvent is the single source of truth.** The Job trace shown live in the frontend is a filtered view over this stream, scoped to `job_id` — never a separately maintained log (ADR-11, `decisions.md`). If you're adding logging anywhere in this system, it should be an AuditEvent, not a print statement or a bespoke log line that nothing else reads.

## Event schema

Table definition: `data-model.md#AuditEvent`. Restated here for reference:

```json
{
  "event_id": "uuid",
  "job_id": "uuid | null",
  "event_type": "string",
  "component": "string",
  "timestamp": "iso8601",
  "payload": { }
}
```

`job_id` is null only for Job-independent events (currently just `network_check`, which runs continuously regardless of Job activity).

## Event types

| Type | Fired by | Payload includes |
|---|---|---|
| `job_created` | API/Job Layer | `conversation_id`, `input_message` |
| `orchestrator_step` | Orchestrator dispatch code | `action` (`respond`/`invoke_capability`), raw proposal |
| `policy_decision` | Policy Layer | `capability`, `decision` (`allow`/`deny`), `reason` |
| `tool_invoked` | Job Manager, on dispatch | `capability`, `arguments` |
| `model_invoked` | Model Runtime | `resource_type`, `model_identifier`, `prompt_tokens`, `completion_tokens`, `duration_ms` |
| `resource_loaded` | Resource/Model Lifecycle Manager | `resource_type`, `model_identifier`, `duration_ms` |
| `resource_unloaded` | Resource/Model Lifecycle Manager | `resource_type`, `model_identifier`, `reason` (`idle_timeout`/`evicted`) |
| `artifact_created` | Artifact Executor | `artifact_id`, `type`, `filename` |
| `error` | any component | `component`, `message`, `context` |
| `job_completed` | Job Manager | `status` (`completed`/`failed`), `duration_ms` |
| `network_check` | Monitoring component | `external_connections_detected` (bool), `checked_at` |

Do not introduce a new event type without adding it here first — this table is authoritative and other documents (`architecture.md`, `security.md`, `data-model.md`) reference it rather than redefining it.

## Correlation

Every Job-scoped event carries `job_id`. `conversation_id` is available by joining through the `Job` table where needed (not duplicated onto every event — avoids redundant fields). There is no separate "session ID" concept for SIH scope — a `conversation_id` serves that role.

## Storage

The `audit_events` SQLite table (`data-model.md`), indexed on `(job_id, timestamp)` and `(event_type, timestamp)` for both the live-trace query pattern and any later type-scoped debugging query.

## Retention

No rotation/deletion for the SIH build — hackathon data volumes don't warrant it (consistent with `data-model.md`'s retention note).

## SSE delivery to the frontend

`GET /api/v1/jobs/{job_id}/events` (`api.md`) streams new `AuditEvent` rows for that `job_id` as they're inserted, in the same JSON shape as the table above. Implementation approach: the event-write function (called by every component above) both inserts the row and pushes to any open SSE subscriptions for that `job_id` — a single write path, not a database-insert plus a separate broadcast mechanism that could drift out of sync.

## Job trace = filtered Audit/Event stream

Restated because it's easy to accidentally violate: `GET /api/v1/jobs/{job_id}/trace` (a point-in-time read) and the SSE stream above (live) are both **queries over `audit_events`** — there is no `job_trace` table, no separate trace-building logic that could disagree with what actually happened. If a bug ever causes the live trace and the audit log to show different things for the same Job, that's a correctness bug in the query, not two systems that need reconciling.
