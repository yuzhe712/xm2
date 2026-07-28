from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from redis import Redis
from sqlalchemy import text

from intelliticket_backend.config import get_settings
from intelliticket_backend.db import get_engine
from intelliticket_backend.metrics import prometheus_payload

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/api/v1/health", include_in_schema=False)
def health_check() -> dict[str, str]:
    """健康检查。"""
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.app_version,
        "data_mode": settings.data_mode,
    }


@router.get("/ready")
@router.get("/api/v1/ready", include_in_schema=False)
def readiness_check() -> JSONResponse:
    checks = {
        "database": _check_database(),
        "redis": _check_redis(),
    }
    ready = all(checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    content, content_type = prometheus_payload()
    return Response(content=content, headers={"content-type": content_type})


def _check_database() -> bool:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _check_redis() -> bool:
    settings = get_settings()
    broker_url = settings.celery_broker_url.get_secret_value()
    if not broker_url.startswith("redis://"):
        return False
    client: Redis | None = None
    try:
        client = Redis.from_url(
            broker_url,
            socket_connect_timeout=settings.readiness_timeout_seconds,
            socket_timeout=settings.readiness_timeout_seconds,
        )
        return bool(client.ping())
    except Exception:
        return False
    finally:
        if client is not None:
            client.close()
