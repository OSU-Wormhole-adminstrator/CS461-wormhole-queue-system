"""Queue maintenance helpers and CLI commands."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, cast

import click
from flask import Flask

from app import db
from app.models import AssistantSession, Ticket
from app.time_utils import ensure_aware_utc


def flush_open_tickets(reason: str = "Queue Flushed") -> int:
    """Close all active tickets and return how many were updated."""
    now = datetime.now(timezone.utc)
    count = cast(
        int,
        Ticket.query.filter(~Ticket.status.in_(["closed", "resolved"])).update(
            {
                Ticket.status: "closed",
                Ticket.closed_reason: reason,
                Ticket.closed_at: now,
                Ticket.number_of_students: 0,
            },
            synchronize_session=False,
        ),
    )

    db.session.commit()
    return count


def close_stale_assistant_sessions(
    *, max_open_hours: int = 12, exclude_session_ids: Iterable[int] | None = None
) -> int:
    """
    Close impossible open assistant sessions left behind by crashes/sleep.

    Socket disconnect events are best-effort. A laptop sleep, browser crash, or app
    restart can leave AssistantSession.session_end as NULL forever. This helper caps
    those ghost sessions so exports cannot show someone as working for thousands of
    hours.
    """
    if max_open_hours <= 0:
        return 0

    excluded = set(exclude_session_ids or [])
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max_open_hours)

    stale_sessions = (
        AssistantSession.query.filter(
            AssistantSession.session_end.is_(None),
            AssistantSession.session_start < cutoff,
        )
        .order_by(AssistantSession.session_start.asc())
        .all()
    )

    closed_count = 0
    for session_record in stale_sessions:
        if session_record.id in excluded:
            continue

        session_start = ensure_aware_utc(session_record.session_start)
        capped_end = min(now, session_start + timedelta(hours=max_open_hours))
        duration_seconds = (capped_end - session_start).total_seconds()

        session_record.session_end = capped_end
        session_record.duration_minutes = max(0, int(duration_seconds // 60))
        closed_count += 1

    if closed_count:
        db.session.commit()

    return closed_count


def register_queue_maintenance_cli(app: Flask) -> None:
    """Register queue maintenance commands on the Flask app."""

    @app.cli.command("flush-open-tickets")
    @click.option(
        "--reason",
        default="Queue Flushed",
        show_default=True,
        help="Reason stored in closed_reason for auto-closed tickets.",
    )
    def flush_open_tickets_command(reason: str) -> None:
        """Close all non-closed/resolved tickets."""
        count = flush_open_tickets(reason=reason)
        click.echo(f"Nightly queue flush complete: {count} ticket(s) closed")

    @app.cli.command("close-stale-assistant-sessions")
    @click.option(
        "--max-open-hours",
        default=12,
        show_default=True,
        type=int,
        help="Maximum believable open assistant session length.",
    )
    def close_stale_assistant_sessions_command(max_open_hours: int) -> None:
        """Close ghost AssistantSession rows left open by crashes or sleep."""
        count = close_stale_assistant_sessions(max_open_hours=max_open_hours)
        click.echo(f"Closed {count} stale assistant session(s)")
