from __future__ import annotations

from fastapi import APIRouter

from intelliticket_backend.config import get_settings

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """健康检查。"""
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.app_version,
        "data_mode": settings.data_mode,
    }
