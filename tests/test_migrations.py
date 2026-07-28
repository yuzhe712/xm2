from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select

from intelliticket_backend.config import get_settings
from intelliticket_backend.db import session_scope
from intelliticket_backend.models import Ticket
from intelliticket_backend.repositories.ticket_history import TicketHistoryRepository
from scripts.migrate_legacy_sqlite import migrate

P0_TABLES = {
    "users",
    "teams",
    "tickets",
    "ticket_events",
    "ticket_comments",
    "ai_runs",
    "sla_policies",
}


def _upgrade(database_url: str, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")


def test_initial_alembic_migration_creates_p0_tables(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'p0.sqlite3').as_posix()}"

    _upgrade(database_url, monkeypatch)

    tables = set(inspect(create_engine(database_url)).get_table_names())
    assert P0_TABLES <= tables


def test_legacy_sqlite_migration_preserves_source_and_copies_ticket(
    tmp_path, monkeypatch
) -> None:
    source = tmp_path / "legacy.sqlite3"
    legacy = TicketHistoryRepository(source)
    legacy.save_pending_ticket(
        ticket_id="TCK-20260728-CCCCCCCC",
        text="legacy ticket",
        data_mode="mock",
        desk_id="ops",
        submitter="unknown-legacy-user",
    )
    destination_url = f"sqlite+pysqlite:///{(tmp_path / 'target.sqlite3').as_posix()}"
    _upgrade(destination_url, monkeypatch)

    report = migrate(source, destination_url)

    assert source.is_file()
    assert report.tickets_migrated == 1
    assert report.warnings
    with session_scope(destination_url) as session:
        ticket = session.scalar(
            select(Ticket).where(Ticket.ticket_id == "TCK-20260728-CCCCCCCC")
        )
        assert ticket is not None
        assert ticket.input_text == "legacy ticket"
        assert ticket.submitter == "unknown-legacy-user"
