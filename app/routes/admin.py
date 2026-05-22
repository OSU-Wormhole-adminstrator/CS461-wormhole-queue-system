# app/routes/admin.py
"""Admin monitoring routes for live roster and attendance health."""

from __future__ import annotations

import csv
import io
import math

from flask import Blueprint, Response, jsonify, render_template, request

from app import db
from app.auth_utils import admin_required
from app.models import AssistantSession, IdleEvent, User
from app.routes.queue_events import build_roster
from app.time_utils import format_pacific, serialize_datetime

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin/attendance-health", methods=["GET"])
@admin_required
def attendance_health():
    """Render the admin Attendance Health monitoring page."""
    return render_template("attendance_health.html", title="Attendance Health")


@admin_bp.route("/api/admin/roster", methods=["GET"])
@admin_required
def get_roster():
    """Return a live snapshot of assistant statuses."""
    return jsonify(build_roster())


@admin_bp.route("/api/admin/idle-log", methods=["GET"])
@admin_required
def get_idle_log():
    """Return a paginated exception log of idle assistant events."""
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = request.args.get("per_page", 25, type=int)
    per_page = min(max(per_page, 1), 100)

    base_query = (
        db.session.query(IdleEvent, User)
        .join(User, IdleEvent.user_id == User.id)
        .order_by(IdleEvent.triggered_at.desc())
    )
    total = base_query.count()
    rows = base_query.offset((page - 1) * per_page).limit(per_page).all()
    pages = math.ceil(total / per_page) if total else 0

    return jsonify(
        {
            "events": [
                {
                    "id": event.id,
                    "assistant": user.name or user.username,
                    "username": user.username,
                    "triggered_at": serialize_datetime(event.triggered_at),
                    "triggered_at_local": format_pacific(
                        event.triggered_at, "%a %b %d, %I:%M %p %Z"
                    ),
                    "open_ticket_count": event.open_ticket_count,
                    "oldest_ticket_wait_minutes": event.oldest_ticket_wait_minutes,
                }
                for event, user in rows
            ],
            "total": total,
            "pages": pages,
            "current_page": page,
            "per_page": per_page,
        }
    )


@admin_bp.route("/api/admin/export-sessions", methods=["GET"])
@admin_required
def export_sessions():
    """Export all assistant session rows as CSV for term-end records."""
    sessions = (
        db.session.query(AssistantSession, User)
        .join(User, AssistantSession.user_id == User.id)
        .order_by(AssistantSession.session_start.desc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "Assistant",
            "ONID",
            "Session Start (Pacific)",
            "Session End (Pacific)",
            "Duration (min)",
        ]
    )

    for assistant_session, user in sessions:
        writer.writerow(
            [
                user.name or user.username,
                user.username,
                format_pacific(assistant_session.session_start, "%Y-%m-%d %H:%M %Z"),
                format_pacific(assistant_session.session_end, "%Y-%m-%d %H:%M %Z")
                if assistant_session.session_end
                else "",
                assistant_session.duration_minutes
                if assistant_session.duration_minutes is not None
                else "",
            ]
        )

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=assistant_sessions.csv"},
    )
