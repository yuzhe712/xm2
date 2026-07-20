from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from intelliticket_backend.api.auth import router as auth_router
from intelliticket_backend.api.desks import router as desks_router
from intelliticket_backend.api.health import router as health_router
from intelliticket_backend.api.tickets import knowledge_router, router as tickets_router
from intelliticket_backend.config import get_settings
from intelliticket_backend.errors import register_exception_handlers

settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["content-type", "authorization"],
)
register_exception_handlers(app)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(tickets_router)
app.include_router(desks_router)
app.include_router(knowledge_router)
