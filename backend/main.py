import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.health import router as health_router
from config import CORS_ALLOW_ORIGINS, DATA_SUBDIRS


def create_data_directories() -> None:
    for directory in DATA_SUBDIRS:
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
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1")
