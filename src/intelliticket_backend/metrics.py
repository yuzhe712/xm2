from __future__ import annotations

import logging

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from redis import Redis

from intelliticket_backend.config import get_settings
from intelliticket_backend.db import session_scope
from intelliticket_backend.repositories.tickets import TicketRepository

logger = logging.getLogger(__name__)

HTTP_REQUESTS = Counter(
    "intelliticket_http_requests_total",
    "HTTP requests processed by the API.",
    ("method", "route", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "intelliticket_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
)
AI_TASKS = Counter(
    "intelliticket_ai_tasks_total",
    "AI task lifecycle events.",
    ("outcome",),
)
AI_QUEUE_LENGTH = Gauge(
    "intelliticket_ai_queue_length",
    "Number of tasks waiting in the configured Celery queue.",
)
SLA_OVERDUE = Gauge(
    "intelliticket_sla_overdue_tickets",
    "Open tickets currently overdue by SLA deadline type.",
    ("deadline",),
)


def observe_http_request(method: str, route: str, status_code: int, duration: float) -> None:
    HTTP_REQUESTS.labels(method=method, route=route, status=str(status_code)).inc()
    HTTP_REQUEST_DURATION.labels(method=method, route=route).observe(duration)


def refresh_operational_gauges() -> None:
    _refresh_queue_length()
    _refresh_sla_overdue()


def prometheus_payload() -> tuple[bytes, str]:
    refresh_operational_gauges()
    return generate_latest(), CONTENT_TYPE_LATEST


def _refresh_queue_length() -> None:
    settings = get_settings()
    broker_url = settings.celery_broker_url.get_secret_value()
    if not broker_url.startswith("redis://"):
        AI_QUEUE_LENGTH.set(float("nan"))
        return
    client: Redis | None = None
    try:
        client = Redis.from_url(
            broker_url,
            socket_connect_timeout=settings.readiness_timeout_seconds,
            socket_timeout=settings.readiness_timeout_seconds,
        )
        AI_QUEUE_LENGTH.set(client.llen(settings.celery_queue_name))
    except Exception as exc:
        logger.warning("Unable to collect Celery queue length: %s", type(exc).__name__)
        AI_QUEUE_LENGTH.set(float("nan"))
    finally:
        if client is not None:
            client.close()


def _refresh_sla_overdue() -> None:
    try:
        with session_scope() as session:
            overdue = TicketRepository(session).overdue()
        SLA_OVERDUE.labels(deadline="response").set(
            sum(1 for ticket in overdue if ticket.response_overdue)
        )
        SLA_OVERDUE.labels(deadline="resolution").set(
            sum(1 for ticket in overdue if ticket.resolution_overdue)
        )
    except Exception as exc:
        logger.warning("Unable to collect SLA overdue metrics: %s", type(exc).__name__)
        SLA_OVERDUE.labels(deadline="response").set(float("nan"))
        SLA_OVERDUE.labels(deadline="resolution").set(float("nan"))
