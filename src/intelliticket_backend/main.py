from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from intelliticket_backend.api.ai_runs import router as ai_runs_router
from intelliticket_backend.api.admin_config import router as admin_config_router
from intelliticket_backend.api.auth import router as auth_router
from intelliticket_backend.api.desks import router as desks_router
from intelliticket_backend.api.health import router as health_router
from intelliticket_backend.api.ticket_workflow import router as ticket_workflow_router
from intelliticket_backend.api.tickets import knowledge_router
from intelliticket_backend.api.tickets import router as tickets_router
from intelliticket_backend.api.users import router as users_router
from intelliticket_backend.config import get_settings
from intelliticket_backend.errors import register_exception_handlers
from intelliticket_backend.services.bootstrap import bootstrap_admin

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    bootstrap_admin(settings)
    yield


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
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
app.include_router(users_router)
app.include_router(admin_config_router)
app.include_router(ai_runs_router)
app.include_router(ticket_workflow_router)
app.include_router(tickets_router)
app.include_router(desks_router)
app.include_router(knowledge_router)
