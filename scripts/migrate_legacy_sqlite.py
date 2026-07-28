from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import make_url

from intelliticket_backend.config import get_settings
from intelliticket_backend.db import session_scope
from intelliticket_backend.models import AiRun, Ticket, User


@dataclass
class MigrationReport:
    source: str
    destination: str
    tickets_migrated: int = 0
    tickets_skipped: int = 0
    ai_runs_migrated: int = 0
    ai_runs_skipped: int = 0
    warnings: list[str] = field(default_factory=list)


def _rows(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    if exists is None:
        return []
    return [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"')]


def migrate(source: Path, destination_url: str) -> MigrationReport:
    if not source.is_file():
        raise FileNotFoundError(f"legacy SQLite database does not exist: {source}")
    report = MigrationReport(
        source=str(source.resolve()),
        destination=make_url(destination_url).render_as_string(hide_password=True),
    )

    with sqlite3.connect(source) as legacy:
        legacy.row_factory = sqlite3.Row
        ticket_rows = _rows(legacy, "tickets")
        run_rows = _rows(legacy, "runs")

    with session_scope(destination_url) as session:
        users_by_username = {
            user.username: user.id for user in session.scalars(select(User)).all()
        }
        for row in ticket_rows:
            ticket_id = row["ticket_id"]
            if session.get(Ticket, ticket_id) is not None:
                report.tickets_skipped += 1
                continue
            data_mode = row.get("data_mode")
            if data_mode not in {"mock", "real"}:
                report.tickets_skipped += 1
                report.warnings.append(
                    f"{ticket_id}: unsupported legacy data_mode {data_mode!r}; ticket skipped"
                )
                continue
            submitter = row.get("submitter")
            session.add(
                Ticket(
                    ticket_id=ticket_id,
                    title=row.get("report_title"),
                    description=row.get("input_text"),
                    input_text=row.get("input_text") or "",
                    desk_id=row.get("desk_id") or "ops",
                    data_mode=data_mode,
                    ticket_status=row.get("ticket_status") or "open",
                    priority=row.get("priority"),
                    submitter=submitter,
                    submitter_id=users_by_username.get(submitter),
                    assigned_team=row.get("assigned_team"),
                    claimed_by=row.get("claimed_by"),
                    summary=row.get("summary"),
                    affected_service=row.get("affected_service"),
                    report_title=row.get("report_title"),
                    resolution_summary=row.get("resolution_summary"),
                    root_cause=row.get("root_cause"),
                    fix_action=row.get("fix_action"),
                    verification=row.get("verification"),
                    assessed_priority=row.get("assessed_priority"),
                    assessed_priority_reason=row.get("assessed_priority_reason"),
                    sla_deadline=row.get("sla_deadline"),
                    closed_at=row.get("closed_at"),
                    latest_run_id=row.get("latest_run_id"),
                    created_at=row.get("created_at"),
                    updated_at=row.get("updated_at"),
                )
            )
            if submitter and submitter not in users_by_username:
                report.warnings.append(
                    f"{ticket_id}: submitter {submitter!r} has no database user mapping"
                )
            report.tickets_migrated += 1
        session.flush()

        known_tickets = set(session.scalars(select(Ticket.ticket_id)).all())
        for row in run_rows:
            run_id = row["run_id"]
            if session.get(AiRun, run_id) is not None:
                report.ai_runs_skipped += 1
                continue
            ticket_id = row["ticket_id"]
            if ticket_id not in known_tickets:
                report.ai_runs_skipped += 1
                report.warnings.append(f"{run_id}: ticket {ticket_id!r} is unavailable")
                continue
            ticket_input = next(
                (
                    item.get("input_text") or ""
                    for item in ticket_rows
                    if item["ticket_id"] == ticket_id
                ),
                "",
            )
            session.add(
                AiRun(
                    id=run_id,
                    ticket_id=ticket_id,
                    status=row.get("status") or "failed",
                    pipeline_version="legacy",
                    provider="legacy-unknown",
                    model="legacy-unknown",
                    prompt_version="legacy",
                    input_hash=hashlib.sha256(ticket_input.encode()).hexdigest(),
                    result_json=_json_object(row.get("response_json")),
                    error_code=_error_code(row.get("error_json")),
                    error_message=_error_message(row.get("error_json")),
                    retry_count=0,
                    started_at=_datetime(row.get("started_at")),
                    completed_at=_datetime(row.get("completed_at")),
                )
            )
            report.ai_runs_migrated += 1
    return report


def _json_object(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else {"legacy_value": parsed}


def _error_code(value: str | None) -> str | None:
    parsed = _json_object(value)
    return str(parsed.get("code")) if parsed and parsed.get("code") else None


def _error_message(value: str | None) -> str | None:
    parsed = _json_object(value)
    return str(parsed.get("message")) if parsed and parsed.get("message") else None


def _datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy IntelliTicket SQLite data")
    parser.add_argument("source", type=Path, help="legacy SQLite database path")
    parser.add_argument("--database-url", default=get_settings().sqlalchemy_database_url)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    report = migrate(args.source, args.database_url)
    output = json.dumps(asdict(report), ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
