import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.artifacts import router as artifacts_router
from api.health import router as health_router
from api.jobs import router as jobs_router
from config import settings
from utils.paths import all_managed_dirs


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
    yield


app = FastAPI(title="Bulwark Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(artifacts_router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.app.host, port=settings.app.port)
