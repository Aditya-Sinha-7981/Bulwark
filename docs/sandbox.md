# Sandbox (Docker — macOS and Windows, identical)

## Principle

One Sandbox Capability contract (`execute_code` in `capabilities.md`), one implementation (Docker), used identically on the M4 Pro reference deployment and every Windows development machine (ADR-05, `decisions.md`). No OS-specific application logic.

## Docker image

A minimal, purpose-built image (`bulwark-sandbox:latest`, built locally during provisioning — never pulled from a public registry at runtime, per zero-egress requirements in `security.md`) containing only the Python runtime and standard library needed to execute generated code. No network tools, no package manager access at container runtime (packages needed for a task must already be in the image — see Package policy below).

## Container lifecycle

Per invocation of `execute_code`:

1. Write the generated code to a fresh temp file under `data/sandbox/{execution_id}/input/`.
2. Copy any referenced `input_files` (from the capability's input schema) into that same directory.
3. Run:
   ```
   docker run --rm \
     --network none \
     --cpus 1 \
     --memory 512m \
     --read-only \
     -v data/sandbox/{execution_id}/input:/workspace/input:ro \
     -v data/sandbox/{execution_id}/output:/workspace/output:rw \
     --workdir /workspace \
     bulwark-sandbox:latest \
     python input/script.py
   ```
4. Enforce the timeout (`configuration.md`, default 30s) via the calling process, hard-killing the container (`docker kill`) on expiry.
5. Capture stdout/stderr/exit code from the Docker process.
6. Collect any files written to `data/sandbox/{execution_id}/output/` as candidate output artifacts.
7. Clean up: remove the temp directory tree after results are captured (container itself is already gone via `--rm`).

## Input mounts

`data/sandbox/{execution_id}/input/` — read-only inside the container. Contains the generated script and any explicitly referenced input documents.

## Output mounts

`data/sandbox/{execution_id}/output/` — the only writable path inside the container. Anything written here is what `execute_code`'s `output_files` can reference.

## Filesystem restrictions

Container filesystem is `--read-only` except the output mount. No access to the host filesystem beyond the two explicit mounts. No access to any other Job's sandbox directory.

## Network denial

`--network none` — this is real, Docker-enforced network denial, not an application-level check. This is one concrete layer of the zero-egress defense described in `security.md`, not the whole story by itself.

## CPU/memory limits

`--cpus 1 --memory 512m` by default (configurable, `configuration.md`). Chosen conservatively — SIH demo tasks are small, deliberately-scoped scripts, not compute-heavy workloads.

## Timeout

30s default (configurable). Enforced by the calling Python process wrapping the `docker run` invocation with its own timeout and a `docker kill` fallback — Docker itself has no native per-run timeout flag, so this is application-level orchestration around a Docker-enforced isolation boundary, not a gap in enforcement.

## Process handling

Exactly one process per container (the invoked script) — no daemonization, no background processes expected or supported.

## stdout/stderr

Captured directly from the Docker CLI invocation's output streams, returned verbatim (truncated to a configured max size, `configuration.md`, to avoid an oversized/runaway-output response) in the capability's output schema.

## Exit codes

Captured and returned as `exit_code` in the capability's output schema (`capabilities.md`). `0` = success by convention; non-zero is returned as-is for the Orchestrator to interpret, not translated into a pass/fail judgment by the Executor itself.

## Cleanup

`--rm` removes the container immediately on exit. The temp directory tree under `data/sandbox/{execution_id}/` is deleted after results are captured — nothing from a sandbox execution persists beyond that Job's recorded output files (which are copied into `data/artifacts/` as proper Artifacts if they're meant to be kept, not left in the ephemeral sandbox directory).

## Image management

The `bulwark-sandbox:latest` image is built once during provisioning (`deployment.md`) from a Dockerfile checked into the repository. It is never rebuilt or pulled at runtime — this matters for both reliability (no build-time surprises mid-demo) and zero-egress (no registry pull needed after provisioning).

## Package policy

Only packages baked into the image at build time are available inside the sandbox. Generated code that imports something not in the image fails with an `ImportError`, surfaced through `stderr`/`exit_code` like any other execution failure — the Orchestrator can react to this (e.g., regenerate simpler code) but the system will not install packages at runtime, ever, since that would require network access.

## Security boundaries

The sandbox is reachable only through the `execute_code` capability's Executor (`agent.md` — Policy interaction) — no other component invokes Docker directly. Combined with `--network none`, `--read-only`, and the scoped mounts, this gives defense in depth even though the code being run is (by design) generated by a model the team controls, not arbitrary untrusted internet input.

## Failure recovery

Container crash, timeout, or Docker daemon unavailability are all returned to the Orchestrator as a structured failed result (never an unhandled exception that crashes the Job) — see `capabilities.md`'s `execute_code` failure modes and `architecture.md`'s failure boundaries table.
