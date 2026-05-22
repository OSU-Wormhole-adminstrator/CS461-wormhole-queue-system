# app/routes/queue_events.py
"""
SocketIO events for real-time queue updates and admin monitoring.

The public queue still uses the /queue namespace. Assistant presence is tracked on
/assistant, and admin-only monitoring updates are emitted on /admin.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import current_app, request, session

from app import db, socketio
from app.models import AssistantSession, IdleEvent, Ticket, User
from app.queue_maintenance import close_stale_assistant_sessions
from app.time_utils import ensure_aware_utc, format_pacific, serialize_datetime

connected_assistants: dict[str, dict[str, int]] = {}
connected_admin_sids: set[str] = set()
_last_roster_signature: tuple[tuple[int, str, bool, bool], ...] | None = None
_monitoring_task_started = False


@socketio.on("connect", namespace="/queue")
def handle_queue_connect(auth=None):
    """Handle client connection to queue namespace."""
    print("Client connected to /queue")


@socketio.on("disconnect", namespace="/queue")
def handle_queue_disconnect():
    """Handle client disconnect from queue namespace."""
    print("Client disconnected from /queue")


def _session_user() -> User | None:
    """Return the active user from the Flask session, if one exists."""
    user_id = session.get("user_id")
    if not user_id:
        return None

    user = db.session.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def _connected_user_ids() -> set[int]:
    """Return user IDs for assistants currently connected to /assistant."""
    return {entry["user_id"] for entry in connected_assistants.values()}


def _connected_session_ids() -> set[int]:
    """Return AssistantSession ids currently owned by live sockets."""
    return {entry["session_id"] for entry in connected_assistants.values()}


def _session_id_for_connected_user(user_id: int) -> int | None:
    """Return an open AssistantSession id if this user already has a socket."""
    for entry in connected_assistants.values():
        if entry["user_id"] == user_id:
            return entry["session_id"]
    return None


def _has_other_connection_for_session(
    *, sid: str, user_id: int, session_id: int
) -> bool:
    """Return True when another socket still owns this attendance session."""
    return any(
        other_sid != sid
        and entry["user_id"] == user_id
        and entry["session_id"] == session_id
        for other_sid, entry in connected_assistants.items()
    )


def _busy_wa_ids() -> set[int]:
    """Return WA IDs that currently own an in-progress ticket in one query."""
    return {
        wa_id
        for (wa_id,) in db.session.query(Ticket.wa_id)
        .filter(Ticket.status == "in_progress", Ticket.wa_id.isnot(None))
        .all()
    }


def _reopen_recent_session(user_id: int) -> int | None:
    """Reuse a just-closed session so refreshes do not inflate CSV exports."""
    grace_seconds = current_app.config.get(
        "ASSISTANT_SESSION_REJOIN_GRACE_SECONDS", 90
    )
    if grace_seconds <= 0:
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=grace_seconds)
    recent_session = (
        AssistantSession.query.filter(
            AssistantSession.user_id == user_id,
            AssistantSession.session_end.isnot(None),
            AssistantSession.session_end >= cutoff,
        )
        .order_by(AssistantSession.session_end.desc())
        .first()
    )
    if recent_session is None:
        return None

    recent_session.session_end = None
    recent_session.duration_minutes = None
    db.session.commit()
    return recent_session.id


@socketio.on("connect", namespace="/assistant")
def handle_assistant_connect(auth=None):
    """Track a non-admin assistant connection and open an attendance session."""
    user = _session_user()
    if user is None or user.is_admin:
        return False

    session_id = _session_id_for_connected_user(user.id)
    if session_id is None:
        session_id = _reopen_recent_session(user.id)

    if session_id is None:
        session_record = AssistantSession(user_id=user.id)
        db.session.add(session_record)
        db.session.commit()
        session_id = session_record.id

    connected_assistants[request.sid] = {
        "user_id": user.id,
        "session_id": session_id,
    }
    emit_roster_update_if_changed()
    return None


@socketio.on("disconnect", namespace="/assistant")
def handle_assistant_disconnect():
    """Close the assistant attendance session and refresh the admin roster."""
    presence = connected_assistants.pop(request.sid, None)
    if not presence:
        return

    if not _has_other_connection_for_session(
        sid=request.sid,
        user_id=presence["user_id"],
        session_id=presence["session_id"],
    ):
        session_record = db.session.get(AssistantSession, presence["session_id"])
        if session_record and session_record.session_end is None:
            session_end = datetime.now(timezone.utc)
            session_start = ensure_aware_utc(session_record.session_start)
            duration_seconds = (session_end - session_start).total_seconds()
            session_record.session_end = session_end
            session_record.duration_minutes = max(0, int(duration_seconds // 60))
            db.session.commit()

    emit_roster_update_if_changed()


@socketio.on("connect", namespace="/admin")
def handle_admin_connect(auth=None):
    """Reject non-admin SocketIO clients from the admin monitoring namespace."""
    user = _session_user()
    if user is None or not user.is_admin:
        return False

    connected_admin_sids.add(request.sid)
    emit_roster_update_if_changed(room=request.sid)
    return None


@socketio.on("disconnect", namespace="/admin")
def handle_admin_disconnect():
    """Stop doing admin-only roster work once the admin tab is gone."""
    connected_admin_sids.discard(request.sid)


def _oldest_live_ticket_wait_minutes(now: datetime) -> int | None:
    oldest_ticket = (
        Ticket.query.filter_by(status="live").order_by(Ticket.created_at.asc()).first()
    )
    if oldest_ticket is None:
        return None

    created_at = ensure_aware_utc(oldest_ticket.created_at)
    return max(0, int((now - created_at).total_seconds() // 60))


def build_roster() -> list[dict[str, Any]]:
    """Build the admin-facing assistant roster with active/idle/offline status."""
    now = datetime.now(timezone.utc)
    active_wa_ids = _connected_user_ids()
    grace = current_app.config["IDLE_GRACE_MINUTES"]
    stale_cutoff = now - timedelta(minutes=grace)

    stale_ticket_exists = (
        Ticket.query.filter(
            Ticket.status == "live", Ticket.created_at < stale_cutoff
        ).count()
        > 0
    )

    assistants = (
        User.query.filter_by(is_admin=False, is_active=True)
        .order_by(User.name.asc(), User.username.asc())
        .all()
    )

    busy_wa_ids = _busy_wa_ids()

    roster = []
    for user in assistants:
        connected = user.id in active_wa_ids
        has_active_ticket = user.id in busy_wa_ids

        if not connected:
            status = "offline"
        elif has_active_ticket or not stale_ticket_exists:
            status = "active"
        else:
            status = "idle"

        roster.append(
            {
                "user_id": user.id,
                "name": user.name or user.username,
                "username": user.username,
                "status": status,
                "connected": connected,
                "has_active_ticket": has_active_ticket,
            }
        )

    return roster


def _roster_signature(
    roster: list[dict[str, Any]],
) -> tuple[tuple[int, str, bool, bool], ...]:
    """Return the fields that matter for deciding whether to re-emit the roster."""
    return tuple(
        (
            int(row["user_id"]),
            str(row["status"]),
            bool(row["connected"]),
            bool(row["has_active_ticket"]),
        )
        for row in roster
    )


def emit_roster_update_if_changed(*, force: bool = False, room: str | None = None) -> None:
    """
    Emit admin roster updates only when useful.

    Ticket events can be very frequent. If no admin tabs are connected, skip the
    roster DB work entirely. If admins are connected, emit only when the roster's
    status-bearing fields changed. A room-targeted emit is used for a newly
    connected admin tab and always sends the current snapshot to that tab.
    """
    global _last_roster_signature

    if room is None and not connected_admin_sids:
        return

    roster = build_roster()
    signature = _roster_signature(roster)

    if room is not None:
        socketio.emit("roster_update", roster, room=room, namespace="/admin")
        _last_roster_signature = signature
        return

    if force or signature != _last_roster_signature:
        socketio.emit("roster_update", roster, namespace="/admin")
        _last_roster_signature = signature


def _idle_connected_assistant_ids() -> list[int]:
    """Return connected assistant IDs that do not have an in-progress ticket."""
    busy_wa_ids = _busy_wa_ids()
    return [user_id for user_id in _connected_user_ids() if user_id not in busy_wa_ids]


def _write_idle_events(
    *,
    idle_user_ids: list[int],
    stale_ticket_count: int,
    oldest_wait_minutes: int | None,
    now: datetime,
) -> None:
    grace = current_app.config["IDLE_GRACE_MINUTES"]
    recent_cutoff = now - timedelta(minutes=grace)

    for user_id in idle_user_ids:
        already_logged = IdleEvent.query.filter(
            IdleEvent.user_id == user_id,
            IdleEvent.triggered_at > recent_cutoff,
        ).first()
        if already_logged:
            continue

        db.session.add(
            IdleEvent(
                user_id=user_id,
                open_ticket_count=stale_ticket_count,
                oldest_ticket_wait_minutes=oldest_wait_minutes,
            )
        )

    db.session.commit()


def run_idle_check_once() -> None:
    """Run one monitoring cycle. Kept separate so tests can call it directly."""
    close_stale_assistant_sessions(
        max_open_hours=current_app.config.get("ASSISTANT_SESSION_MAX_OPEN_HOURS", 12),
        exclude_session_ids=_connected_session_ids(),
    )

    now = datetime.now(timezone.utc)
    grace = current_app.config["IDLE_GRACE_MINUTES"]
    stale_cutoff = now - timedelta(minutes=grace)

    stale_ticket_count = Ticket.query.filter(
        Ticket.status == "live",
        Ticket.created_at < stale_cutoff,
    ).count()

    if stale_ticket_count == 0:
        emit_roster_update_if_changed()
        return

    if not connected_assistants:
        return

    idle_user_ids = _idle_connected_assistant_ids()
    if not idle_user_ids:
        emit_roster_update_if_changed()
        return

    oldest_wait_minutes = _oldest_live_ticket_wait_minutes(now)
    _write_idle_events(
        idle_user_ids=idle_user_ids,
        stale_ticket_count=stale_ticket_count,
        oldest_wait_minutes=oldest_wait_minutes,
        now=now,
    )
    emit_roster_update_if_changed()

    critical_wait = current_app.config["CRITICAL_WAIT_MINUTES"]
    critical_count_threshold = current_app.config["CRITICAL_TICKET_COUNT"]
    critical_cutoff = now - timedelta(minutes=critical_wait)
    critical_count = Ticket.query.filter(
        Ticket.status == "live",
        Ticket.created_at < critical_cutoff,
    ).count()

    all_connected_are_idle = len(idle_user_ids) == len(_connected_user_ids())
    if (
        connected_admin_sids
        and critical_count >= critical_count_threshold
        and all_connected_are_idle
    ):
        socketio.emit(
            "critical_alert",
            {
                "message": (
                    f"{critical_count} students have waited over {critical_wait} "
                    "minutes while all connected assistants appear idle."
                )
            },
            namespace="/admin",
        )


def idle_checker(app):
    """Background task that periodically logs idle assistant exceptions."""
    while True:
        socketio.sleep(60)
        with app.app_context():
            run_idle_check_once()


def start_admin_monitoring_task(app) -> None:
    """Start the background monitor once per process."""
    global _monitoring_task_started
    if _monitoring_task_started:
        return
    if app.config.get("TESTING"):
        return
    if not app.config.get("ADMIN_MONITORING_ENABLED", True):
        return
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return

    _monitoring_task_started = True
    socketio.start_background_task(idle_checker, app)


def broadcast_ticket_update(ticket_id):
    """
    Broadcast a ticket update to all connected clients on the queue namespace.
    Called when a new ticket is created or updated.
    """
    try:
        t = db.session.get(Ticket, ticket_id)
        if t:
            ticket_data = {
                "id": t.id,
                "student_name": t.student_name,
                "table": t.table,
                "physics_course": t.physics_course,
                "created_at": serialize_datetime(t.created_at),
                "created_at_local": format_pacific(
                    t.created_at, "%Y-%m-%d %H:%M:%S %Z"
                ),
                "status": t.status,
            }
            socketio.emit("new_ticket", ticket_data, namespace="/queue")
            emit_roster_update_if_changed()
            print(f"Broadcasted ticket update for ticket ID {ticket_id}")
    except Exception as e:
        print(f"Error broadcasting ticket update: {e}")


def broadcast_queue_refresh():
    """
    Broadcast a refresh signal to all connected clients.
    Triggers the client to refetch the queue.
    """
    socketio.emit("queue_refresh", {}, namespace="/queue")
    emit_roster_update_if_changed()
