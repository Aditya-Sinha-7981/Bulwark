import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.artifacts import router as artifacts_router
from backend.api.conversations import router as conversations_router
from backend.api.documents import router as documents_router
from backend.api.health import router as health_router
from backend.api.jobs import router as jobs_router
from backend.api.knowledge_base import router as knowledge_base_router
from backend.api.network_status import router as network_status_router
from backend.config import settings
from backend.domain.monitoring import network_monitor
from backend.repositories.db import ConstraintError, DatabaseError, NotFoundError
from backend.utils import socket_guard
from backend.utils.paths import all_managed_dirs


def create_data_directories() -> None:
    for directory in all_managed_dirs():
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"fatal: could not create data directory {directory}: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_data_directories()
    # Zero-egress layer 6 (backstop) — installed before anything else opens a
    # socket, so no code path in this process can slip a connection out
    # before the guard is live (docs/security.md layer 6, Task 18).
    socket_guard.install()
    # Zero-egress monitor — layers 1-6 enforce; this is the live proof
    # (docs/security.md "Monitoring", Task 18 Requirement 7).
    await network_monitor.start()
    try:
        yield
    finally:
        await network_monitor.stop()


app = FastAPI(title="Bulwark Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Error mapping (docs/api.md "Error format" + status table) -----------------
# Domain code never builds an HTTP response (docs/backend.md "Errors"); the
# mapping from typed domain exceptions to the documented envelope lives here,
# at the router boundary only (Task 15 Requirement 5).

def _envelope(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


@app.exception_handler(NotFoundError)
async def _not_found_handler(_request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content=_envelope("not_found", str(exc)))


@app.exception_handler(ConstraintError)
async def _constraint_handler(_request: Request, exc: ConstraintError) -> JSONResponse:
    # A constraint violation surfaced to the HTTP layer is a bad request
    # (e.g. referencing a conversation that does not exist on job create is
    # handled explicitly as 404 in the router; anything reaching here is 400).
    return JSONResponse(status_code=400, content=_envelope("bad_request", str(exc)))


@app.exception_handler(DatabaseError)
async def _database_handler(_request: Request, exc: DatabaseError) -> JSONResponse:
    # The database is a required synchronous dependency for every request
    # (Task 15 Requirement 7): if it is unreachable, that request cannot proceed.
    return JSONResponse(
        status_code=503,
        content=_envelope("dependency_unavailable", f"database error: {exc}"),
    )


app.include_router(health_router, prefix="/api/v1")
app.include_router(network_status_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(artifacts_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(knowledge_base_router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.app.host, port=settings.app.port)
