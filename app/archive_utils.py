"""Helpers and CLI commands for ticket archive CSV generation."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

import click
from flask import Flask
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models import Ticket
from app.time_utils import PACIFIC_TZ, ensure_aware_utc, format_pacific

ARCHIVE_HEADERS = [
    "Ticket ID",
    "Student Name",
    "Table",
    "Course",
    "Status",
    "Created At",
    "Closed At",
    "Students Helped",
    "Assistant Name",
    "Ticket Type",
]

CUMULATIVE_ARCHIVE_FILENAME = "wormhole_archive_all.csv"


def safe_archive_filename(filename: str) -> str:
    """Return a safe CSV filename for files stored in the archive directory."""
    safe_name = Path(filename).name.strip()
    if not safe_name:
        safe_name = CUMULATIVE_ARCHIVE_FILENAME
    if Path(safe_name).suffix.lower() != ".csv":
        safe_name = f"{safe_name}.csv"
    return safe_name


@dataclass(frozen=True)
class ArchiveWriteResult:
    """Summary of one archive write operation."""

    path: Path
    rows_written: int
    rows_skipped: int
    start_utc: datetime
    end_utc: datetime


def archive_dir(root_path: str | Path) -> Path:
    """Return the app archive directory, creating it when needed."""
    archive_path = Path(root_path) / "data" / "archives"
    archive_path.mkdir(parents=True, exist_ok=True)
    return archive_path


def list_archive_files(root_path: str | Path) -> list[str]:
    """List saved CSV archive files newest-first by filename."""
    return sorted(
        [path.name for path in archive_dir(root_path).glob("*.csv") if path.is_file()],
        reverse=True,
    )


def sanitize_csv_value(value):
    """Prevent spreadsheet formula execution when archive CSVs are opened."""
    if value and isinstance(value, str):
        normalized = value.lstrip()
        if normalized.startswith(("=", "+", "-", "@")):
            # Prepend quote to the ORIGINAL value so leading whitespace is preserved.
            return f"'{value}"
    return value


def archive_ticket_query(
    start_utc: datetime,
    end_utc: datetime,
    *,
    include_end: bool = True,
):
    """Build the ticket query used by manual and weekly archive exports."""
    normalized_start = ensure_aware_utc(start_utc)
    normalized_end = ensure_aware_utc(end_utc)

    if normalized_start is None or normalized_end is None:
        raise ValueError("start_utc and end_utc are required")

    closed_range: ColumnElement[bool]
    created_range: ColumnElement[bool]

    if include_end:
        closed_range = Ticket.closed_at.between(normalized_start, normalized_end)
        created_range = Ticket.created_at.between(normalized_start, normalized_end)
    else:
        closed_range = and_(
            Ticket.closed_at >= normalized_start,
            Ticket.closed_at < normalized_end,
        )
        created_range = and_(
            Ticket.created_at >= normalized_start,
            Ticket.created_at < normalized_end,
        )

    return (
        Ticket.query.options(selectinload(Ticket.wormhole_assistant))
        .filter(
            or_(
                and_(
                    Ticket.status.in_(["closed", "resolved"]),
                    closed_range,
                ),
                and_(
                    Ticket.status == "resolved",
                    Ticket.closed_at.is_(None),
                    created_range,
                ),
            )
        )
        .order_by(func.coalesce(Ticket.closed_at, Ticket.created_at).desc())
    )


def ticket_archive_row(ticket: Ticket) -> list[object]:
    """Convert one ticket to the shared CSV row format."""
    return [
        ticket.id,
        sanitize_csv_value(ticket.student_name),
        sanitize_csv_value(ticket.table),
        sanitize_csv_value(ticket.physics_course),
        ticket.closed_reason if ticket.closed_reason else "Not Provided",
        format_pacific(ticket.created_at, "%Y-%m-%d %H:%M:%S"),
        format_pacific(ticket.closed_at, "%Y-%m-%d %H:%M:%S"),
        ticket.number_of_students,
        sanitize_csv_value(
            ticket.wormhole_assistant.name
            if ticket.wormhole_assistant and ticket.wormhole_assistant.name
            else "N/A"
        ),
        "Zoom"
        if ticket.table == "Zoom"
        else "Teams"
        if ticket.table == "Teams"
        else "Box",
    ]


def render_archive_csv(tickets: Iterable[Ticket]) -> str:
    """Render tickets as a complete CSV document with one header row."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(ARCHIVE_HEADERS)

    for ticket in tickets:
        writer.writerow(ticket_archive_row(ticket))

    return output.getvalue()


def write_archive_file(path: Path, tickets: Iterable[Ticket]) -> ArchiveWriteResult:
    """Write a standalone archive CSV, replacing any existing file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows_written = 0

    with path.open("w", encoding="utf-8", newline="") as archive_file:
        writer = csv.writer(archive_file)
        writer.writerow(ARCHIVE_HEADERS)
        for ticket in tickets:
            writer.writerow(ticket_archive_row(ticket))
            rows_written += 1

    # start/end are not meaningful for this low-level helper; callers that need
    # those values should use create_archive_file or append_weekly_archive.
    return ArchiveWriteResult(
        path=path,
        rows_written=rows_written,
        rows_skipped=0,
        start_utc=datetime.min.replace(tzinfo=timezone.utc),
        end_utc=datetime.min.replace(tzinfo=timezone.utc),
    )


def create_archive_file(
    *,
    root_path: str | Path,
    start_utc: datetime,
    end_utc: datetime,
    filename: str,
) -> ArchiveWriteResult:
    """Create or replace a manual archive file for an explicit date range."""
    tickets = archive_ticket_query(start_utc, end_utc, include_end=True).yield_per(1000)
    path = archive_dir(root_path) / safe_archive_filename(filename)
    write_result = write_archive_file(path, tickets)
    return ArchiveWriteResult(
        path=path,
        rows_written=write_result.rows_written,
        rows_skipped=write_result.rows_skipped,
        start_utc=start_utc,
        end_utc=end_utc,
    )


def _row_dedupe_key(row: list[object]) -> tuple[str, str, str]:
    """
    Build a stable key for duplicate prevention in cumulative archives.

    The queue can reset ticket IDs after an admin clears data, so ID alone is not
    safe. Combining ID with created/closed timestamps keeps the weekly append
    command idempotent without blocking newly-created tickets that reuse an old ID.
    """
    return (str(row[0]), str(row[5]), str(row[6]))


def _existing_archive_keys(path: Path) -> set[tuple[str, str, str]]:
    """Read existing cumulative archive rows so repeat jobs do not duplicate rows."""
    if not path.exists() or path.stat().st_size == 0:
        return set()

    keys: set[tuple[str, str, str]] = set()
    with path.open("r", encoding="utf-8", newline="") as archive_file:
        reader = csv.DictReader(archive_file)
        for row in reader:
            ticket_id = row.get("Ticket ID")
            created_at = row.get("Created At")
            closed_at = row.get("Closed At")
            if (
                ticket_id is not None
                and created_at is not None
                and closed_at is not None
            ):
                keys.add((ticket_id, created_at, closed_at))
    return keys


def previous_saturday_week_bounds(
    now: Optional[datetime] = None,
) -> tuple[datetime, datetime]:
    """
    Return the previous completed Saturday-to-Saturday week in UTC.

    The intended production schedule is Saturday at 00:00 Pacific. This helper is
    also safe if an admin manually runs the command later; it archives the most
    recent completed week ending at the latest Saturday midnight Pacific.
    """
    if now is None:
        now_local = datetime.now(PACIFIC_TZ)
    else:
        aware_now = ensure_aware_utc(now)
        if aware_now is None:
            raise ValueError("now cannot be None")
        now_local = aware_now.astimezone(PACIFIC_TZ)

    days_since_saturday = (now_local.weekday() - 5) % 7
    end_date = now_local.date() - timedelta(days=days_since_saturday)
    end_local = datetime.combine(end_date, time.min, tzinfo=PACIFIC_TZ)
    start_local = end_local - timedelta(days=7)

    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def append_weekly_archive(
    *,
    root_path: str | Path,
    now: Optional[datetime] = None,
    filename: str = CUMULATIVE_ARCHIVE_FILENAME,
) -> ArchiveWriteResult:
    """Append the latest completed week of tickets to the cumulative archive CSV."""
    start_utc, end_utc = previous_saturday_week_bounds(now)
    archive_path = archive_dir(root_path) / safe_archive_filename(filename)
    tickets = sorted(
        archive_ticket_query(start_utc, end_utc, include_end=False).yield_per(1000),
        key=lambda ticket: ticket.id,
        reverse=True,
    )

    existing_keys = _existing_archive_keys(archive_path)
    rows_written = 0
    skipped = 0

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not archive_path.exists() or archive_path.stat().st_size == 0

    with archive_path.open("a", encoding="utf-8", newline="") as archive_file:
        writer = csv.writer(archive_file)
        if needs_header:
            writer.writerow(ARCHIVE_HEADERS)

        for ticket in tickets:
            row = ticket_archive_row(ticket)
            key = _row_dedupe_key(row)
            if key in existing_keys:
                skipped += 1
                continue

            existing_keys.add(key)
            writer.writerow(row)
            rows_written += 1

    return ArchiveWriteResult(
        path=archive_path,
        rows_written=rows_written,
        rows_skipped=skipped,
        start_utc=start_utc,
        end_utc=end_utc,
    )


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse an optional ISO datetime for deterministic CLI/testing use."""
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=PACIFIC_TZ)
    return parsed


def register_archive_cli(app: Flask) -> None:
    """Register archive maintenance commands on the Flask app."""

    @app.cli.command("archive-weekly")
    @click.option(
        "--now",
        "now_value",
        help="Optional ISO datetime used as the current time, mainly for testing.",
    )
    @click.option(
        "--filename",
        default=CUMULATIVE_ARCHIVE_FILENAME,
        show_default=True,
        help="Cumulative archive filename inside app/data/archives.",
    )
    def archive_weekly_command(now_value: Optional[str], filename: str) -> None:
        """Append the latest completed Saturday-to-Saturday archive week."""
        result = append_weekly_archive(
            root_path=app.root_path,
            now=_parse_iso_datetime(now_value),
            filename=filename,
        )

        click.echo(
            "Weekly archive complete: "
            f"{result.rows_written} row(s) appended, "
            f"{result.rows_skipped} duplicate row(s) skipped, "
            f"file={result.path.name}"
        )
