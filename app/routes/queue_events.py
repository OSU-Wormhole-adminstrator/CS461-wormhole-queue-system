# app/routes/queue_events.py
"""
SocketIO events for real-time queue updates and admin monitoring.

The public queue still uses the /queue namespace. Assistant presence is tracked on
/assistant, and admin-only monitoring updates are emitted on /admin.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from flask import current_app, request, session

from app import db, socketio
from app.models import AssistantSession, IdleEvent, Ticket, User
from app.time_utils import ensure_aware_utc, format_pacific, serialize_datetime

connected_assistants: dict[str, dict[str, int]] = {}
_monitoring_task_started = False


@socketio.on("connect", namespace="/queue")
def handle_queue_connect():
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


@socketio.on("connect", namespace="/assistant")
def handle_assistant_connect():
    """Track a non-admin assistant connection and open an attendance session."""
    user = _session_user()
    if user is None or user.is_admin:
        return False

    session_record = AssistantSession(user_id=user.id)
    db.session.add(session_record)
    db.session.commit()

    connected_assistants[request.sid] = {
        "user_id": user.id,
        "session_id": session_record.id,
    }
    socketio.emit("roster_update", build_roster(), namespace="/admin")
    return None


@socketio.on("disconnect", namespace="/assistant")
def handle_assistant_disconnect():
    """Close the assistant attendance session and refresh the admin roster."""
    presence = connected_assistants.pop(request.sid, None)
    if not presence:
        return

    session_record = db.session.get(AssistantSession, presence["session_id"])
    if session_record and session_record.session_end is None:
        session_end = datetime.now(timezone.utc)
        session_start = ensure_aware_utc(session_record.session_start)
        duration_seconds = (session_end - session_start).total_seconds()
        session_record.session_end = session_end
        session_record.duration_minutes = max(0, int(duration_seconds // 60))
        db.session.commit()

    socketio.emit("roster_update", build_roster(), namespace="/admin")


@socketio.on("connect", namespace="/admin")
def handle_admin_connect():
    """Reject non-admin SocketIO clients from the admin monitoring namespace."""
    user = _session_user()
    if user is None or not user.is_admin:
        return False
    socketio.emit("roster_update", build_roster(), room=request.sid, namespace="/admin")
    return None


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

    roster = []
    for user in assistants:
        connected = user.id in active_wa_ids
        has_active_ticket = (
            Ticket.query.filter_by(wa_id=user.id, status="in_progress").count() > 0
        )

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


def _idle_connected_assistant_ids() -> list[int]:
    """Return connected assistant IDs that do not have an in-progress ticket."""
    idle_user_ids = []
    for user_id in _connected_user_ids():
        has_active_ticket = (
            Ticket.query.filter_by(wa_id=user_id, status="in_progress").count() > 0
        )
        if not has_active_ticket:
            idle_user_ids.append(user_id)
    return idle_user_ids


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
    now = datetime.now(timezone.utc)
    grace = current_app.config["IDLE_GRACE_MINUTES"]
    stale_cutoff = now - timedelta(minutes=grace)

    stale_ticket_count = Ticket.query.filter(
        Ticket.status == "live",
        Ticket.created_at < stale_cutoff,
    ).count()

    if stale_ticket_count == 0 or not connected_assistants:
        socketio.emit("roster_update", build_roster(), namespace="/admin")
        return

    idle_user_ids = _idle_connected_assistant_ids()
    if not idle_user_ids:
        socketio.emit("roster_update", build_roster(), namespace="/admin")
        return

    oldest_wait_minutes = _oldest_live_ticket_wait_minutes(now)
    _write_idle_events(
        idle_user_ids=idle_user_ids,
        stale_ticket_count=stale_ticket_count,
        oldest_wait_minutes=oldest_wait_minutes,
        now=now,
    )
    socketio.emit("roster_update", build_roster(), namespace="/admin")

    critical_wait = current_app.config["CRITICAL_WAIT_MINUTES"]
    critical_count_threshold = current_app.config["CRITICAL_TICKET_COUNT"]
    critical_cutoff = now - timedelta(minutes=critical_wait)
    critical_count = Ticket.query.filter(
        Ticket.status == "live",
        Ticket.created_at < critical_cutoff,
    ).count()

    all_connected_are_idle = len(idle_user_ids) == len(_connected_user_ids())
    if critical_count >= critical_count_threshold and all_connected_are_idle:
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

    _monitoring_task_started = True
    socketio.start_background_task(idle_checker, app)


def broadcast_ticket_update(ticket_id):
    """
    Broadcast a ticket update to all connected clients on the queue namespace.
    Called when a new ticket is created or updated.
    """
    try:
        t = Ticket.query.get(ticket_id)
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
            socketio.emit("roster_update", build_roster(), namespace="/admin")
            print(f"Broadcasted ticket update for ticket ID {ticket_id}")
    except Exception as e:
        print(f"Error broadcasting ticket update: {e}")


def broadcast_queue_refresh():
    """
    Broadcast a refresh signal to all connected clients.
    Triggers the client to refetch the queue.
    """
    socketio.emit("queue_refresh", {}, namespace="/queue")
    socketio.emit("roster_update", build_roster(), namespace="/admin")
