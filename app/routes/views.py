# app/routes/views.py
import csv
import io
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urljoin, urlparse

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

# Explicit imports for SQLAlchemy operators to ensure compatibility
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.archive_utils import (
    archive_dir as get_archive_dir,
)
from app.archive_utils import (
    archive_ticket_query,
    create_archive_file,
    list_archive_files,
)
from app.auth_utils import admin_required, login_required
from app.forms import (
    ChangePassForm,
    ClearQueueForm,
    DeleteArchiveForm,
    DeleteUserForm,
    EditUserForm,
    ExportArchiveForm,
    FlushQueueForm,
    LoginForm,
    RegisterBatchForm,
    RegisterForm,
    ResolveTicketForm,
    SiteContentForm,
    TicketForm,
)
from app.models import Skipped, Ticket, User
from app.queue_maintenance import flush_open_tickets
from app.site_content import (
    get_site_content,
    get_site_content_rows,
    save_site_content_bulk,
    split_lines,
)
from app.time_utils import (
    PACIFIC_TZ,
    format_pacific,
    pacific_day_bounds_to_utc,
    serialize_datetime,
)

views_bp = Blueprint("views", __name__)
INSTRUCTION_FILES = {
    "Wormhole_Student_Instructions.pdf",
    "MS_Teams_Instructions.pdf",
}


# --- Helper Functions ---


def is_safe_url(target):
    """Ensures a URL is a safe local path to prevent open redirects."""
    # Ensure target is a non-empty string before using it with urljoin/urlparse
    if not target or not isinstance(target, str):
        return False
    stripped_target = target.strip()
    if not stripped_target:
        return False
    # Reject protocol-relative URLs (e.g., "//example.com/path") to prevent open redirects
    if stripped_target.startswith("//"):
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, stripped_target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc


def _ticket_to_ns(ticket: Ticket):
    if ticket is None:
        return None
    assistant_display_name = (
        ticket.wormhole_assistant.name
        if ticket.wormhole_assistant and ticket.wormhole_assistant.name
        else (
            ticket.wormhole_assistant.username
            if ticket.wormhole_assistant
            else "Unassigned"
        )
    )
    return SimpleNamespace(
        id=ticket.id,
        name=ticket.student_name,
        table=ticket.table,
        phClass=ticket.physics_course,
        time_create=ticket.created_at,
        time_close=ticket.closed_at,
        time_create_pacific=format_pacific(ticket.created_at, "%I:%M %p"),
        time_close_pacific=format_pacific(ticket.closed_at, "%I:%M %p"),
        num_students=ticket.number_of_students,
        closed_reason=ticket.closed_reason,
        closed_by=assistant_display_name,
        assigned_to=assistant_display_name,
    )


def _split_user_name(full_name):
    if not full_name:
        return "", ""

    trimmed = full_name.strip()
    if not trimmed:
        return "", ""

    parts = trimmed.split(maxsplit=1)
    if len(parts) == 1:
        return parts[0], ""

    return parts[0], parts[1]


def _last_name_key(user: User):
    if not user.name:
        return "", user.username.lower()

    name_parts = user.name.split()
    if not name_parts:
        return "", user.username.lower()

    return name_parts[-1].lower(), user.username.lower()


def _csv_safe(value):
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


def _build_users_csv_response(users, filename):
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["first name", "last name", "onid"])

    for user in sorted(users, key=_last_name_key):
        first_name, last_name = _split_user_name(user.name)
        writer.writerow(
            [_csv_safe(first_name), _csv_safe(last_name), _csv_safe(user.username)]
        )

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# --- Routes ---


@views_bp.route("/")
@views_bp.route("/index", endpoint="index")
def index():
    content = get_site_content()

    return render_template(
        "index.html",
        content=content,
        holiday_closures=split_lines(content["holiday_closures"]),
    )


@views_bp.route("/admin/site-content", methods=["GET", "POST"])
@admin_required
def edit_site_content():
    """Allow administrators to edit operational public homepage content."""

    content = get_site_content()

    # WTForms accepts a dictionary through data= for initial field population.
    # On POST, submitted form data takes precedence.
    form = SiteContentForm(data=content)

    if form.validate_on_submit():
        updated_by_id = session.get("user_id")
        updates = {
            "homepage_banner": form.homepage_banner.data or "",
            "schedule_announcement": form.schedule_announcement.data or "",
            "schedule_hours": form.schedule_hours.data or "",
            "schedule_note": form.schedule_note.data or "",
            "holiday_closures": form.holiday_closures.data or "",
            "schedule_embed_url": form.schedule_embed_url.data or "",
        }

        try:
            save_site_content_bulk(updates, updated_by_id=updated_by_id)
        except ValueError:
            db.session.rollback()
            flash("Invalid website content field.", "error")
            return render_template(
                "site_content_edit.html",
                form=form,
                content_rows=get_site_content_rows(),
            )

        flash("Website content updated successfully.", "success")
        return redirect(url_for("views.index"))

    return render_template(
        "site_content_edit.html",
        form=form,
        content_rows=get_site_content_rows(),
        title="Edit Website Content",
    )


@views_bp.route("/livequeue")
def livequeue():
    # Fetch current open tickets for initial page load
    open_tickets = (
        Ticket.query.filter_by(status="live", wa_id=None)
        .order_by(Ticket.created_at)
        .all()
    )
    ol = [_ticket_to_ns(t) for t in open_tickets]
    return render_template("livequeue.html", ol=ol)


@views_bp.route("/wiki")
def wiki():
    return render_template("wiki.html")


@views_bp.route("/queue")
@login_required
def queue():
    # 1. Fetch the REAL user to ensure template links use the correct username
    sid = session.get("user_id")
    current_user_obj = db.session.get(User, sid) if sid else None

    if not current_user_obj:
        return redirect(url_for("views.assistant_login"))

    # Fetch current queue data
    open_tickets = (
        Ticket.query.filter_by(status="live", wa_id=None)
        .order_by(Ticket.created_at)
        .all()
    )

    # Filter by 'in_progress' to match Ticket.assign_to() logic
    current_tickets = (
        Ticket.query.filter_by(status="in_progress").order_by(Ticket.created_at).all()
    )

    # Include both "closed" and "resolved" in the historical list
    closed_tickets = (
        Ticket.query.filter(Ticket.status.in_(["closed", "resolved"]))
        .order_by(Ticket.created_at.desc())
        .all()
    )

    ol = [_ticket_to_ns(t) for t in open_tickets]
    cul = [_ticket_to_ns(t) for t in current_tickets]
    cll = [_ticket_to_ns(t) for t in closed_tickets]

    # Use dedicated CSRF-protected forms for admin queue actions
    flush_form = FlushQueueForm()
    clear_form = ClearQueueForm()

    # Pass the real user object so permissions and usernames are correct in the template
    return render_template(
        "queue.html",
        ol=ol,
        cul=cul,
        cll=cll,
        user=current_user_obj,
        flush_form=flush_form,
        clear_form=clear_form,
    )


# -------------------------------
# POST /flush (Flush Queue)
# -------------------------------
@views_bp.route("/flush", methods=["POST"])
@admin_required
def flush():
    # Validate the form to enforce CSRF protection
    form = FlushQueueForm()
    if not form.validate_on_submit():
        flash("Invalid request or session expired.", "error")
        return redirect(url_for("views.queue"))

    count = flush_open_tickets(reason="Queue Flushed")

    flash(f"Queue flushed. {count} tickets closed.", "info")
    return redirect(url_for("views.queue"))


@views_bp.route("/clear_queue", methods=["POST"])
@admin_required
def clear_queue():
    """Permanently clear all queue ticket rows and reset ticket indexing."""
    form = ClearQueueForm()
    if not form.validate_on_submit():
        flash("Invalid request or session expired.", "error")
        return redirect(url_for("views.queue"))

    cleared_count = Ticket.query.count()
    bind = db.session.get_bind()
    dialect_name = bind.dialect.name if bind and bind.dialect else ""

    try:
        if dialect_name == "postgresql":
            db.session.execute(text("TRUNCATE TABLE tickets RESTART IDENTITY CASCADE"))
        elif dialect_name in {"mysql", "mariadb"}:
            db.session.execute(text("TRUNCATE TABLE tickets"))
        else:
            Ticket.query.delete(synchronize_session=False)
            if dialect_name == "sqlite":
                # Reset SQLite AUTOINCREMENT sequence (if sqlite_sequence exists).
                try:
                    db.session.execute(
                        text("DELETE FROM sqlite_sequence WHERE name = 'tickets'")
                    )
                except Exception:
                    pass

        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Unable to clear queue data.", "error")
        return redirect(url_for("views.queue"))

    flash(
        f"Queue data cleared permanently. {cleared_count} tickets removed.",
        "info",
    )
    return redirect(url_for("views.queue"))


@views_bp.route("/createticket", methods=["GET", "POST"])
def create_ticket_page():
    form = TicketForm()
    if form.validate_on_submit():
        t = Ticket(
            student_name=form.name.data,
            table=form.location.data,
            physics_course=form.phClass.data,
            number_of_students=1,
            status="live",
        )
        db.session.add(t)
        db.session.commit()

        # broadcast update to queue clients
        try:
            from app.routes.queue_events import broadcast_ticket_update

            broadcast_ticket_update(t.id)
        except Exception:
            pass

        join_target = {
            "zoom": "Zoom",
            "teams": "Teams",
        }.get((form.location.data or "").strip().lower())

        if join_target:
            flash(
                f"Ticket created - thank you! Please join {join_target} now.",
                "success",
            )
        else:
            flash("Ticket created - thank you!", "success")
        return redirect(url_for("views.livequeue"))

    return render_template("createticket.html", form=form)


@views_bp.route("/debug/tickets")
def debug_tickets():
    """List all tickets for debugging."""
    from flask import jsonify

    all_tickets = Ticket.query.all()
    return jsonify(
        {
            "total": len(all_tickets),
            "tickets": [
                {
                    "id": t.id,
                    "name": t.student_name,
                    "class": t.physics_course,
                    "table": t.table,
                    "status": t.status,
                    "created_at": serialize_datetime(t.created_at),
                    "created_at_local": format_pacific(
                        t.created_at, "%Y-%m-%d %H:%M:%S %Z"
                    ),
                }
                for t in all_tickets
            ],
        }
    )


@views_bp.route("/assistant-login", methods=["GET", "POST"])
def assistant_login():
    # support form-based login (POST) as well as rendering the login page (GET)
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            if not user.is_active:
                flash("This account has been deactivated.", "error")
                return render_template("login.html", form=form)
            session["user_id"] = user.id
            session["is_admin"] = user.is_admin
            if user.is_admin:
                return redirect(url_for("views.hardware_list"))
            return redirect(url_for("views.hardware_list"))

        flash("Invalid username or password.", "error")
        return render_template("login.html", form=form)

    return render_template("login.html", form=form)


@views_bp.route("/dashboard")
@login_required
def dashboard():
    return "<h1>Welcome! You are logged in to the Wormhole System.</h1>", 200


@views_bp.route("/hardware_list")
@login_required
def hardware_list():
    # Placeholder for hardware list - will be populated with actual data
    boxes = []
    return render_template("hardware_list.html", boxes=boxes)


@views_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("views.index"))


# -------------------------------
# POST /archive/export (Archive Export)
# -------------------------------
@views_bp.route("/archive/export", methods=["POST"])
@admin_required
def export_archive():
    form = ExportArchiveForm()
    if not form.validate_on_submit():
        flash("Invalid date format or missing fields.", "error")
        return redirect(url_for("views.archive"))

    # Interpret the selected dates in Pacific Time, then convert to UTC for querying.
    start_date, _ = pacific_day_bounds_to_utc(form.start_date.data)
    _, end_date = pacific_day_bounds_to_utc(form.end_date.data)

    # Logical Validation
    if start_date > end_date:
        flash("Start date cannot be after end date.", "error")
        return redirect(url_for("views.archive"))

    # Prevent exporting archives for future dates
    now_pacific = datetime.now(PACIFIC_TZ)
    now_pacific = now_pacific.replace(hour=23, minute=59, second=59, microsecond=999999)
    if (
        form.start_date.data > now_pacific.date()
        or form.end_date.data > now_pacific.date()
    ):
        flash("Dates cannot be in the future.", "error")
        return redirect(url_for("views.archive"))

    tickets_query = archive_ticket_query(start_date, end_date, include_end=True)

    # Optimization: Use limit(1) instead of count() to check for existence
    if tickets_query.limit(1).first() is None:
        flash("No closed or resolved tickets found for this period.", "info")
        return redirect(url_for("views.archive"))

    safe_start = start_date.date().isoformat()
    safe_end = end_date.date().isoformat()
    filename = f"wormhole_archive_{safe_start}_to_{safe_end}.csv"

    try:
        create_archive_file(
            root_path=current_app.root_path,
            start_utc=start_date,
            end_utc=end_date,
            filename=filename,
        )
    except OSError:
        flash("Failed to save archive file on server.", "error")
        return redirect(url_for("views.archive"))

    flash(f"Archive created: {filename}", "success")
    return redirect(url_for("views.archive"))


# -------------------------------
# Auxiliary page routes for testing templates
# -------------------------------
@views_bp.route("/archive")
@admin_required
def archive():
    # Instantiate form for the template to render CSRF token and fields
    form = ExportArchiveForm()
    delete_form = DeleteArchiveForm()
    archive_files = list_archive_files(current_app.root_path)
    tkt_list = []
    assoc_list = []
    return render_template(
        "archive.html",
        tkt_list=tkt_list,
        assoc_list=assoc_list,
        archive_files=archive_files,
        delete_form=delete_form,
        form=form,
    )


@views_bp.route("/archive/delete", methods=["POST"])
@admin_required
def delete_archives():
    form = DeleteArchiveForm()
    if not form.validate_on_submit():
        flash("Invalid request or session expired.", "error")
        return redirect(url_for("views.archive"))

    selected_files = request.form.getlist("filenames")
    if not selected_files:
        flash("No archive files selected.", "info")
        return redirect(url_for("views.archive"))

    archive_dir_path = get_archive_dir(current_app.root_path)
    deleted_count = 0

    for raw_name in selected_files:
        safe_name = Path(raw_name).name
        if safe_name != raw_name or not safe_name.lower().endswith(".csv"):
            continue

        archive_path = archive_dir_path / safe_name
        try:
            if archive_path.is_file():
                archive_path.unlink()
                deleted_count += 1
        except OSError:
            continue

    if deleted_count > 0:
        flash(f"Deleted {deleted_count} archive file(s).", "success")
    else:
        flash("No archive files were deleted.", "info")

    return redirect(url_for("views.archive"))


@views_bp.route("/archive/download/<path:filename>")
@admin_required
def download_archive(filename):
    safe_filename = Path(filename).name
    if safe_filename != filename or not safe_filename.lower().endswith(".csv"):
        abort(404)

    archive_dir_path = get_archive_dir(current_app.root_path)
    file_path = archive_dir_path / safe_filename
    if not file_path.is_file():
        abort(404)

    return send_from_directory(str(archive_dir_path), safe_filename, as_attachment=True)


@views_bp.route("/instructions/<path:filename>")
def download_instruction_file(filename):
    safe_filename = Path(filename).name
    if safe_filename != filename or safe_filename not in INSTRUCTION_FILES:
        abort(404)

    instructions_dir = Path(current_app.root_path) / "files"
    file_path = instructions_dir / safe_filename
    if not file_path.is_file():
        abort(404)

    return send_from_directory(
        str(instructions_dir), safe_filename, as_attachment=False
    )


@views_bp.route("/user/<username>")
def userpage(username):
    u = User.query.filter_by(username=username).first()
    if not u:
        abort(404)
    # Get user's current ticket (if any)
    current_ticket = Ticket.query.filter_by(wa_id=u.id, status="in_progress").first()
    # All Skipped?
    # Get IDs of tickets already skipped by the current user
    skipped_subquery = (
        db.session.query(Skipped.tkt_id)
        .filter(Skipped.wa_id == session["user_id"])
        .subquery()
        .select()
    )

    # Get all live tickets which the current user has not skipped
    ticket_count = (
        Ticket.query.filter_by(status="live")
        .filter(Ticket.id.notin_(skipped_subquery))
        .count()
    )
    skipped_all = ticket_count == 0
    # create minimal surface for template
    user_ns = SimpleNamespace(
        username=u.username,
        email=u.email,
        is_admin=u.is_admin,
        tkt=current_ticket,
        all_tkt_assoc_sorted=lambda: [],
    )
    current_user = user_ns
    return render_template(
        "userpage.html",
        user=user_ns,
        current_user=current_user,
        skipped_all=skipped_all,
    )


@views_bp.route("/getnewticket/<username>")
@login_required
def getnewticket(username):
    # Assign the next available live ticket to the given user and redirect
    u = User.query.filter_by(username=username).first()
    if not u:
        abort(404)

    # Get IDs of tickets already skipped by the current user
    skipped_subquery = (
        db.session.query(Skipped.tkt_id)
        .filter(Skipped.wa_id == session["user_id"])
        .subquery()
        .select()
    )

    # Get the live ticket which the current user has not skipped that is first in line
    t = (
        Ticket.query.filter_by(status="live")
        .filter(Ticket.id.notin_(skipped_subquery))
        .first()
    )

    if not t:
        # no tickets available; redirect back to user page
        flash("No available tickets to claim.", "info")
        return redirect(url_for("views.userpage", username=username))

    t.assign_to(u)

    try:
        from app.routes.queue_events import broadcast_ticket_update

        broadcast_ticket_update(t.id)
    except Exception:
        pass

    return redirect(url_for("views.currentticket", tktid=t.id))


@views_bp.route("/user_list")
@admin_required
def user_list():
    current_users = User.query.filter_by(is_active=True).all()
    old_users = User.query.filter_by(is_active=False).all()

    new_users = sorted(current_users, key=_last_name_key)
    old_users = sorted(old_users, key=_last_name_key)

    return render_template("user_list.html", new_users=new_users, old_users=old_users)


@views_bp.route("/user_list/download/current")
@admin_required
def download_current_users():
    try:
        current_users = User.query.filter_by(is_active=True).all()
    except SQLAlchemyError:
        db.session.rollback()
        flash("Unable to export current users right now.", "error")
        return redirect(url_for("views.user_list"))
    return _build_users_csv_response(current_users, "current_users.csv")


@views_bp.route("/user_list/download/old")
@admin_required
def download_old_users():
    try:
        old_users = User.query.filter_by(is_active=False).all()
    except SQLAlchemyError:
        db.session.rollback()
        flash("Unable to export old users right now.", "error")
        return redirect(url_for("views.user_list"))
    return _build_users_csv_response(old_users, "old_users.csv")


@views_bp.route("/register", methods=["GET"])
@admin_required
def register():
    form = RegisterForm()
    return render_template("register.html", form=form)


@views_bp.route("/register_batch", methods=["GET"])
@admin_required
def register_batch():
    form = RegisterBatchForm()
    return render_template("register_batch.html", form=form)


@views_bp.route("/delete/<username>", methods=["GET", "POST"])
@admin_required
def delete_user(username):
    u = User.query.filter_by(username=username).first()
    if not u:
        abort(404)
    # Parse first and last name from the name field
    name_parts = u.name.split() if u.name else ["", ""]
    first_name = name_parts[0] if len(name_parts) > 0 else ""
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
    delete_form = DeleteUserForm()
    edit_form = EditUserForm()
    # Handle POST requests
    if request.method == "POST":
        # Check which form was submitted
        if delete_form.submit.data and delete_form.validate():
            if delete_form.confirm.data == "DELETE":
                username_to_delete = u.username
                db.session.delete(u)
                db.session.commit()
                flash(
                    f"User {username_to_delete} has been deleted permanently.",
                    "success",
                )
                return redirect(url_for("views.user_list"))
            else:
                flash('Please type "DELETE" to confirm user deletion.', "error")
        elif edit_form.submit.data and edit_form.validate():
            # Update user fields based on form data
            if edit_form.first_name.data or edit_form.last_name.data:
                new_first = edit_form.first_name.data or first_name
                new_last = edit_form.last_name.data or last_name
                u.name = f"{new_first} {new_last}".strip()
            if edit_form.onid.data:
                # ONID is the username, which is unique and shouldn't be changed easily
                # For now, we'll skip this or validate it
                if edit_form.onid.data != u.username:
                    existing_user = User.query.filter_by(
                        username=edit_form.onid.data
                    ).first()
                    if existing_user:
                        flash("This ONID is already in use.", "error")
                        return render_template(
                            "delete_user.html",
                            user=SimpleNamespace(username=u.username),
                            delete_form=delete_form,
                            edit_form=edit_form,
                        )
                    u.username = edit_form.onid.data
            if edit_form.email.data:
                if edit_form.email.data != u.email:
                    existing_user = User.query.filter_by(
                        email=edit_form.email.data
                    ).first()
                    if existing_user:
                        flash("This email is already in use.", "error")
                        return render_template(
                            "delete_user.html",
                            user=SimpleNamespace(username=u.username),
                            delete_form=delete_form,
                            edit_form=edit_form,
                        )
                    u.email = edit_form.email.data
            if edit_form.is_admin.data:
                u.is_admin = edit_form.is_admin.data == "true"
            if edit_form.is_active.data:
                u.is_active = edit_form.is_active.data == "true"
            db.session.commit()
            flash("User information has been updated successfully.", "success")
            # Refresh the page with updated data
            return redirect(url_for("views.delete_user", username=u.username))
    user_ns = SimpleNamespace(username=u.username)
    return render_template(
        "delete_user.html",
        user=user_ns,
        delete_form=delete_form,
        edit_form=edit_form,
        user_data=SimpleNamespace(
            first_name=first_name,
            last_name=last_name,
            onid=u.username,
            email=u.email,
            is_admin=u.is_admin,
            is_active=u.is_active,
        ),
    )


@views_bp.route("/changepass", methods=["GET", "POST"])
@login_required
def changepass():
    form = ChangePassForm()
    if form.validate_on_submit():
        username = form.username.data
        user = User.query.filter_by(username=username).first()
        if not user:
            flash("User not found.", "error")
            return render_template("changepass.html", form=form)

        # get current session user
        sid = session.get("user_id")
        cur = User.query.get(sid) if sid else None
        if not cur:
            flash("Not authorized.", "error")
            return render_template("changepass.html", form=form)

        # allow admins to change without old password
        if cur.id != user.id and not cur.is_admin:
            flash("Not authorized to change this user's password.", "error")
            return render_template("changepass.html", form=form)

        # if changing own password, verify old password
        if cur.id == user.id and not user.check_password(form.old_password.data):
            flash("Old password is incorrect.", "error")
            return render_template("changepass.html", form=form)

        # set new password
        user.set_password(form.password.data)
        db.session.commit()
        flash("Password updated successfully.", "success")
        return redirect(url_for("views.userpage", username=user.username))

    return render_template("changepass.html", form=form)


@views_bp.route("/currentticket/<int:tktid>")
@login_required
def currentticket(tktid):
    # Use session.get for SQLAlchemy 2.0 compliance
    t = db.session.get(Ticket, tktid)
    if not t:
        abort(404)
    form = ResolveTicketForm()
    ticket_ns = _ticket_to_ns(t)
    return render_template("currentticket.html", ticket=ticket_ns, form=form)


# -------------------------------
# POST /pastticket (Past Ticket Resolution)
# -------------------------------
@views_bp.route("/pastticket/<username>/<int:tktid>", methods=["GET", "POST"])
@login_required
def pastticket(username, tktid):
    # Validate authorization first: Ensure path username matches logged-in user or admin
    sid = session.get("user_id")
    current_user_obj = db.session.get(User, sid) if sid else None

    if not current_user_obj or (
        current_user_obj.username != username and not current_user_obj.is_admin
    ):
        abort(403)

    # Use session.get for SQLAlchemy 2.0 compliance
    t = db.session.get(Ticket, tktid)
    if not t:
        abort(404)
    form = ResolveTicketForm()

    if form.validate_on_submit():
        # Delegate closing logic to the model method
        # Standardize num_stds retrieval logic
        num_stds = form.numStds.data if form.numStds.data is not None else 1

        # Persist the user performing the close so history can show who resolved it.
        t.wa_id = current_user_obj.id

        t.close_ticket(closed_reason=form.resolveReason.data, num_students=num_stds)

        flash("Ticket resolved successfully.", "success")

        # Open Redirect Protection
        next_page = request.args.get("next")
        if is_safe_url(next_page):
            return redirect(next_page)

        return redirect(url_for("views.queue"))

    ticket_ns = _ticket_to_ns(t)
    return render_template("pastticket.html", ticket=ticket_ns, form=form)
