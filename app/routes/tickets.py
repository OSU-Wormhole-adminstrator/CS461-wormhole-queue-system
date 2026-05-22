# /app/routes/tickets.py
from collections import defaultdict, deque
from datetime import datetime, timezone
from time import monotonic

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    request,
    session,
    url_for,
)

from app import db
from app.models import Skipped, Ticket, User
from app.routes.queue_events import broadcast_ticket_update

_CREATE_TICKET_ATTEMPTS: dict[str, deque[float]] = defaultdict(deque)

tickets_bp = Blueprint("tickets", __name__, url_prefix="/api")


def _client_rate_limit_key() -> str:
    """Return a stable-ish client key for lightweight local rate limiting."""
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.remote_addr or "unknown"


def _ticket_create_rate_limited() -> bool:
    """Throttle anonymous ticket creation bursts without adding a dependency."""
    if current_app.config.get("TESTING"):
        return False

    limit = current_app.config.get("TICKET_CREATE_RATE_LIMIT_COUNT", 60)
    window_seconds = current_app.config.get("TICKET_CREATE_RATE_LIMIT_WINDOW_SECONDS", 60)
    if limit <= 0 or window_seconds <= 0:
        return False

    now = monotonic()
    attempts = _CREATE_TICKET_ATTEMPTS[_client_rate_limit_key()]
    while attempts and attempts[0] <= now - window_seconds:
        attempts.popleft()

    if len(attempts) >= limit:
        return True

    attempts.append(now)
    return False


def _wants_json_response() -> bool:
    """Return True when the caller expects an API-style JSON response."""
    if request.is_json:
        return True
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True

    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return (
        best == "application/json"
        and request.accept_mimetypes["application/json"]
        >= request.accept_mimetypes["text/html"]
    )


def _resolution_response(
    *,
    message: str,
    category: str,
    redirect_url: str,
    status_code: int = 200,
    payload: dict | None = None,
):
    """Return JSON for fetch callers and redirects for normal form posts."""
    if _wants_json_response():
        body = {"message": message, "category": category, "redirect_url": redirect_url}
        if payload:
            body.update(payload)
        return jsonify(body), status_code

    flash(message, category)
    return redirect(redirect_url)


# GET: API route to get all tickets
@tickets_bp.route("/tickets", methods=["GET"])
def get_tickets():
    tickets = Ticket.query.all()
    return jsonify([t.to_dict() for t in tickets])


# POST: API route to create a new ticket
@tickets_bp.route("/tickets", methods=["POST"])
def create_ticket():
    if _ticket_create_rate_limited():
        return (
            jsonify(
                {
                    "error": "Too many ticket submissions. Please wait a moment and try again."
                }
            ),
            429,
        )

    data = request.get_json(silent=True) or {}
    student_name = data.get("student_name")
    physics_course = data.get("class_name")
    table = data.get("table_number")

    # Validate required fields
    if not student_name or not physics_course or table is None:
        return jsonify({"error": "Missing required fields"}), 400

    # Create the new ticket
    new_ticket = Ticket(
        student_name=student_name,
        table=table,
        physics_course=physics_course,
        status="live",
    )

    # Add and commit the new ticket to the database
    db.session.add(new_ticket)
    db.session.commit()

    # Broadcast the new ticket to all connected queue clients
    broadcast_ticket_update(new_ticket.id)

    return jsonify(new_ticket.to_dict()), 201


# GET: API route to get all open tickets that the current user has not skipped
@tickets_bp.route("/unskippedtickets", methods=["GET"])
def get_unskipped_tickets():
    # skipped_subquery = get all tickets skipped by current user
    # get all live tickets not
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    # Get IDs of tickets already skipped by the current user
    skipped_subquery = (
        db.session.query(Skipped.tkt_id)
        .filter(Skipped.wa_id == user_id)
        .subquery()
        .select()
    )

    # Get all live tickets which the current user has not skipped
    tickets = (
        Ticket.query.filter_by(status="live")
        .filter(Ticket.id.notin_(skipped_subquery))
        .all()
    )

    return jsonify([t.to_dict() for t in tickets])


# GET: API route to get all open tickets
@tickets_bp.route("/opentickets", methods=["GET"])
def get_open_tickets():
    # Get all live tickets
    tickets = Ticket.query.filter_by(status="live").all()

    return jsonify([t.to_dict() for t in tickets])


@tickets_bp.route("/livequeuetickets", methods=["GET"])
def get_livequeue_tickets():
    """Return every active ticket shown on the public live queue."""
    tickets = (
        Ticket.query.filter(Ticket.status.in_(["live", "in_progress"]))
        .order_by(Ticket.created_at)
        .all()
    )

    return jsonify([t.to_dict() for t in tickets])


# API route to handle ticket resolution form submission
@tickets_bp.route("/resolveticket/<int:ticket_id>", methods=["POST"])
def resolve_ticket(ticket_id):
    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if user_id else None
    if user is None:
        return _resolution_response(
            message="Authentication required.",
            category="error",
            redirect_url=url_for("views.assistant_login"),
            status_code=401,
        )

    ticket = db.session.get(Ticket, ticket_id)
    if ticket is None:
        return _resolution_response(
            message="Ticket not found.",
            category="error",
            redirect_url=url_for("views.userpage", username=user.username),
            status_code=404,
        )

    resolved_as = request.form.get("resolve")
    number_students_raw = request.form.get("numstudents", "1")

    if resolved_as not in ["duplicate", "helped", "no_show", "return_to_queue"]:
        return _resolution_response(
            message="Invalid resolution option selected.",
            category="error",
            redirect_url=url_for("views.currentticket", tktid=ticket_id),
            status_code=400,
        )

    if resolved_as == "return_to_queue":
        ticket.status = "live"
        ticket.wa_id = None
        ticket.wormhole_assistant = None
        db.session.add(Skipped(wa_id=user.id, tkt_id=ticket_id))
        db.session.commit()
        broadcast_ticket_update(ticket.id)

        return _resolution_response(
            message="Ticket skipped and will be handled by another wormhole assistant.",
            category="info",
            redirect_url=url_for("views.userpage", username=user.username),
            payload={"ticket": ticket.to_dict()},
        )

    if resolved_as == "helped":
        try:
            number_students = int(number_students_raw)
        except (TypeError, ValueError):
            number_students = 1
        number_students = max(1, min(number_students, 100))
    else:
        number_students = 0

    ticket.close_ticket(closed_reason=resolved_as, num_students=number_students)
    broadcast_ticket_update(ticket.id)

    messages = {
        "duplicate": "Ticket marked as duplicate and closed successfully.",
        "helped": f"Ticket marked as helped and closed successfully ({number_students} students).",
        "no_show": "Ticket marked as no show and closed successfully.",
    }
    return _resolution_response(
        message=messages[resolved_as],
        category="success",
        redirect_url=url_for("views.userpage", username=user.username),
        payload={"ticket": ticket.to_dict()},
    )
