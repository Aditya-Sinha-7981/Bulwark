from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def get_health() -> dict:
    return {
        "status": "ok",
        "backend": "ok",
        "database": "ok",
        "model_runtime": "unavailable",
        "docker": "unavailable",
    }
