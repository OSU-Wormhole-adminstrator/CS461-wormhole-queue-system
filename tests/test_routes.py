# tests/test_routes.py
import csv
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from app import db
from app.models import SiteContent, Ticket, User
from app.time_utils import pacific_day_bounds_to_utc


def _login_as_admin(test_client):
    unique = uuid4().hex
    admin = User(
        username=f"site_admin_{unique}",
        email=f"site_admin_{unique}@example.com",
        is_admin=True,
    )
    admin.set_password("password")
    db.session.add(admin)
    db.session.commit()

    with test_client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["is_admin"] = True

    return admin


def test_health_check_route(test_client):
    """Test the /health route returns 200 and the correct JSON message."""
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"message": "Wormhole Queue System API is running"}


def test_404_for_unknown_route(test_client):
    """Test that a non-existent route returns a 404 error."""
    response = test_client.get("/non_existent_route")
    assert response.status_code == 404


def test_home_page_loads(test_client):
    """Verify the root route '/' loads the Student Home Page (index.html)."""
    response = test_client.get("/")
    assert response.status_code == 200
    assert b"Physics Collaboration and Help Center" in response.data


def test_instruction_pdf_routes_are_present_on_home(test_client):
    """Home page should link to instruction routes that serve PDF files."""
    response = test_client.get("/")
    assert response.status_code == 200
    assert b"/instructions/Wormhole_Student_Instructions.pdf" in response.data
    assert b"/instructions/MS_Teams_Instructions.pdf" in response.data


def test_homepage_uses_default_site_content(test_client):
    """Homepage should render safe default editable content when DB is empty."""
    response = test_client.get("/")

    assert response.status_code == 200
    assert b"The Wormhole is open for Spring 2026!" in response.data
    assert b"10 AM" in response.data
    assert b"Memorial Day" in response.data


def test_homepage_preserves_static_links_when_content_is_dynamic(test_client):
    """Dynamic schedule content should not remove existing static homepage links."""
    response = test_client.get("/")

    assert response.status_code == 200
    assert b"/createticket" in response.data
    assert b"/livequeue" in response.data
    assert b"Wormhole_Student_Instructions.pdf" in response.data
    assert b"MS_Teams_Instructions.pdf" in response.data


def test_create_ticket_flash_reminds_to_join_zoom(test_client):
    """Creating a Zoom ticket should include a Zoom join reminder."""
    response = test_client.post(
        "/createticket",
        data={
            "name": "Test Student",
            "phClass": "Ph 211",
            "location": "Zoom",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Ticket created - thank you! Please join Zoom now." in response.data


def test_create_ticket_flash_reminds_to_join_teams(test_client):
    """Creating a Teams ticket should include a Teams join reminder."""
    response = test_client.post(
        "/createticket",
        data={
            "name": "Test Student",
            "phClass": "Ph 211",
            "location": "Teams",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Ticket created - thank you! Please join Teams now." in response.data


def test_site_content_editor_requires_login(test_client):
    """The website editor should be protected from anonymous users."""
    response = test_client.get("/admin/site-content")

    assert response.status_code == 401


def test_admin_can_open_site_content_editor(test_client):
    """Admins should be able to open the website content editor."""
    _login_as_admin(test_client)

    response = test_client.get("/admin/site-content")

    assert response.status_code == 200
    assert b"Edit Website Content" in response.data
    assert b"Schedule Announcement" in response.data


def test_admin_can_update_schedule_content(test_client):
    """Admins should be able to update schedule content without code changes."""
    admin = _login_as_admin(test_client)

    response = test_client.post(
        "/admin/site-content",
        data={
            "homepage_banner": "The Wormhole will close early this Friday.",
            "schedule_announcement": "Updated schedule announcement",
            "schedule_hours": "Open Monday through Friday, 11 AM to 4 PM.",
            "schedule_note": "Reduced hours during finals week.",
            "holiday_closures": "Memorial Day — Closed",
            "schedule_embed_url": (
                "https://docs.google.com/spreadsheets/d/e/"
                "2PACX-1vExamplePublishedSheetId/pubhtml?widget=true&headers=false"
            ),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Website content updated successfully." in response.data
    assert b"The Wormhole will close early this Friday." in response.data
    assert b"Updated schedule announcement" in response.data
    assert b"Open Monday through Friday, 11 AM to 4 PM." in response.data

    stored = db.session.get(SiteContent, "schedule_announcement")
    assert stored is not None
    assert stored.value == "Updated schedule announcement"
    assert stored.updated_by_id == admin.id


def test_site_content_editor_rejects_non_google_embed_url(test_client):
    """The schedule iframe should reject non-Google Sheets URLs."""
    _login_as_admin(test_client)

    response = test_client.post(
        "/admin/site-content",
        data={
            "homepage_banner": "",
            "schedule_announcement": "Updated announcement",
            "schedule_hours": "Open Monday through Friday.",
            "schedule_note": "",
            "holiday_closures": "",
            "schedule_embed_url": "https://example.com/bad-embed",
        },
    )

    assert response.status_code == 200
    assert (
        b"Schedule embed URL must be a published Google Sheets pubhtml URL."
        in response.data
    )


def test_download_instruction_files_serves_known_pdfs(test_client):
    """Known instruction PDFs should be downloadable via the instructions route."""
    wormhole_response = test_client.get(
        "/instructions/Wormhole_Student_Instructions.pdf"
    )
    assert wormhole_response.status_code == 200
    assert "application/pdf" in wormhole_response.headers.get("Content-Type", "")

    teams_response = test_client.get("/instructions/MS_Teams_Instructions.pdf")
    assert teams_response.status_code == 200
    assert "application/pdf" in teams_response.headers.get("Content-Type", "")


def test_download_instruction_file_rejects_unknown_name(test_client):
    """Unknown or non-allowlisted instruction filename should return 404."""
    response = test_client.get("/instructions/not-allowed.pdf")
    assert response.status_code == 404


def test_login_route_exists(test_client):
    """Verify the login route is accessible."""
    response = test_client.get("/assistant-login")
    assert response.status_code == 200
    assert b"Sign In" in response.data


def test_assistant_login_page_loads(test_client):
    """Verify '/assistant-login' loads the Login Page (login.html)."""
    response = test_client.get("/assistant-login")
    assert response.status_code == 200
    assert b"Assistant Login" in response.data


def test_assistant_login_inactive_user(test_client, test_app):
    """Ensure that form-based login rejects inactive users."""
    with test_app.app_context():
        u = User(username="inactiveform", email="if@i.com", is_active=False)
        u.set_password("pass")
        db.session.add(u)
        db.session.commit()

    response = test_client.post(
        "/assistant-login",
        data={"username": "inactiveform", "password": "pass"},
        follow_redirects=True,
    )
    # should not redirect to hardware_list; instead show error message
    assert b"This account has been deactivated." in response.data


def test_dashboard_is_protected(test_client):
    """Verify that '/dashboard' blocks users who are NOT logged in."""
    response = test_client.get("/dashboard")
    assert response.status_code == 401


def test_dashboard_access_granted(test_client, test_app):
    """
    Verify that '/dashboard' allows users who ARE logged in.
    We simulate a login by manually setting the session cookie.
    """
    with test_app.app_context():
        u = User(username="testuser", email="test@example.com")
        u.set_password("password")
        db.session.add(u)
        db.session.commit()
        user_id = u.id

    # 1. Simulate a logged-in user by setting the session
    with test_client.session_transaction() as sess:
        sess["user_id"] = user_id  # Use real user ID
        sess["is_admin"] = False
    response = test_client.get("/dashboard")
    assert response.status_code == 200


def test_flush_route(test_client):
    """Test that flushing the queue closes all live tickets (Admin Only)."""
    admin = User(username="admin_flush", email="flush@test.com", is_admin=True)
    admin.set_password("pass")
    db.session.add(admin)

    t1 = Ticket(student_name="S1", table="T1", physics_course="Ph 211", status="live")
    t2 = Ticket(student_name="S2", table="T2", physics_course="Ph 212", status="live")
    t3 = Ticket(
        student_name="S3", table="T3", physics_course="Ph 213", status="in_progress"
    )
    db.session.add_all([t1, t2, t3])
    db.session.commit()

    with test_client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["is_admin"] = True

    response = test_client.post("/flush", follow_redirects=True)
    assert response.status_code == 200
    assert b"Queue flushed" in response.data  # Matches partial string check

    # Refresh objects from DB to see the update from the separate request context
    db.session.refresh(t1)
    db.session.refresh(t2)
    db.session.refresh(t3)
    assert t1.status == "closed"
    assert t1.closed_reason == "Queue Flushed"
    assert t1.number_of_students == 0
    assert t2.status == "closed"
    assert t2.closed_reason == "Queue Flushed"
    assert t2.number_of_students == 0
    assert t3.status == "closed"
    assert t3.closed_reason == "Queue Flushed"
    assert t3.number_of_students == 0

    # Verify that closed_at has been set recently for all flushed tickets
    now = datetime.now(timezone.utc)
    for ticket in (t1, t2, t3):
        assert ticket.closed_at is not None
        assert isinstance(ticket.closed_at, datetime)
        # Ensure ticket.closed_at is timezone-aware before comparison
        closed_at_aware = (
            ticket.closed_at.replace(tzinfo=timezone.utc)
            if ticket.closed_at.tzinfo is None
            else ticket.closed_at
        )
        assert now - closed_at_aware < timedelta(minutes=1)


def test_clear_queue_route_resets_ticket_index(test_client):
    """Clear queue should permanently remove tickets and restart IDs at 1."""
    admin = User(username="admin_clear", email="clear@test.com", is_admin=True)
    admin.set_password("pass")
    db.session.add(admin)

    t1 = Ticket(student_name="S1", table="T1", physics_course="Ph 211", status="live")
    t2 = Ticket(student_name="S2", table="T2", physics_course="Ph 212", status="closed")
    db.session.add_all([t1, t2])
    db.session.commit()

    with test_client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["is_admin"] = True

    response = test_client.post("/clear_queue", follow_redirects=True)
    assert response.status_code == 200
    assert b"Queue data cleared permanently" in response.data

    assert Ticket.query.count() == 0

    new_ticket = Ticket(
        student_name="AfterClear",
        table="T9",
        physics_course="Ph 213",
        status="live",
    )
    db.session.add(new_ticket)
    db.session.commit()
    assert new_ticket.id == 1


def test_export_archive(test_client):
    """Test archive export generates CSV with correct content."""
    admin = User(username="admin_arch", email="arch@test.com", is_admin=True)
    admin.set_password("pass")
    db.session.add(admin)

    # Build the test around a Pacific local day because the archive export
    # route interprets submitted dates in America/Los_Angeles.
    pacific = ZoneInfo("America/Los_Angeles")
    yesterday_local = datetime.now(pacific) - timedelta(days=1)
    closed_local = yesterday_local.replace(hour=12, minute=0, second=0, microsecond=0)
    t = Ticket(
        student_name="ExportMe", table="T1", physics_course="Ph 211", status="closed"
    )
    t.closed_at = closed_local.astimezone(timezone.utc)
    db.session.add(t)
    db.session.commit()

    with test_client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["is_admin"] = True

    data = {
        "start_date": closed_local.date().isoformat(),
        "end_date": closed_local.date().isoformat(),
    }

    response = test_client.post("/archive/export", data=data, follow_redirects=True)
    assert response.status_code == 200
    assert "text/html" in response.headers["Content-Type"]
    assert b"Archive created: wormhole_archive_" in response.data
    assert b"Create Archive" in response.data


def test_archive_page_lists_saved_files(test_client, test_app):
    """Archive page should show links for saved CSV files."""
    admin = User(username="admin_list", email="list@test.com", is_admin=True)
    admin.set_password("pass")
    db.session.add(admin)
    db.session.commit()

    archive_dir = Path(test_app.root_path) / "data" / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    filename = "wormhole_archive_test_listing.csv"
    file_path = archive_dir / filename
    file_path.write_text("id,name\n1,Test\n", encoding="utf-8")

    with test_client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["is_admin"] = True

    response = None
    try:
        response = test_client.get("/archive")
        assert response.status_code == 200
        assert filename.encode("utf-8") in response.data
    finally:
        if response is not None:
            response.close()
        if file_path.exists():
            file_path.unlink()


def test_download_archive_serves_csv_file(test_client, test_app):
    """Archive download route should return saved CSV file contents."""
    admin = User(username="admin_download", email="download@test.com", is_admin=True)
    admin.set_password("pass")
    db.session.add(admin)
    db.session.commit()

    archive_dir = Path(test_app.root_path) / "data" / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    filename = "wormhole_archive_test_download.csv"
    file_path = archive_dir / filename
    file_path.write_text("Ticket ID,Student Name\n1,DownloadMe\n", encoding="utf-8")

    with test_client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["is_admin"] = True

    response = None
    try:
        response = test_client.get(f"/archive/download/{filename}")
        assert response.status_code == 200
        assert b"DownloadMe" in response.data
        assert "attachment;" in response.headers.get("Content-Disposition", "")
    finally:
        if response is not None:
            response.close()
        if file_path.exists():
            file_path.unlink()


def test_delete_archives_removes_selected_file(test_client, test_app):
    """Archive delete route should remove selected CSV file(s)."""
    admin = User(username="admin_delete", email="delete@test.com", is_admin=True)
    admin.set_password("pass")
    db.session.add(admin)
    db.session.commit()

    archive_dir = Path(test_app.root_path) / "data" / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    filename = "wormhole_archive_test_delete.csv"
    file_path = archive_dir / filename
    file_path.write_text("Ticket ID,Student Name\n1,DeleteMe\n", encoding="utf-8")

    with test_client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["is_admin"] = True

    response = test_client.post(
        "/archive/delete",
        data={"filenames": [filename]},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Deleted 1 archive file(s)." in response.data
    assert not file_path.exists()


def test_delete_archives_with_no_selection(test_client, test_app):
    """Archive delete route should inform admin when nothing is selected."""
    admin = User(
        username="admin_delete_none", email="deletenone@test.com", is_admin=True
    )
    admin.set_password("pass")
    db.session.add(admin)
    db.session.commit()

    with test_client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["is_admin"] = True

    response = test_client.post("/archive/delete", data={}, follow_redirects=True)
    assert response.status_code == 200
    assert b"No archive files selected." in response.data


def test_download_current_users_csv(test_client):
    """Current user CSV export should include only active users and expected columns."""
    admin = User(
        username="admin_csv_current", email="currentcsv@test.com", is_admin=True
    )
    admin.set_password("pass")

    active = User(
        username="jdoe",
        email="jdoe@test.com",
        name="Jane Doe",
        is_active=True,
    )
    active.set_password("pass")

    inactive = User(
        username="olduser",
        email="olduser@test.com",
        name="Old User",
        is_active=False,
    )
    inactive.set_password("pass")

    db.session.add_all([admin, active, inactive])
    db.session.commit()

    with test_client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["is_admin"] = True

    response = test_client.get("/user_list/download/current")
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("Content-Type", "")
    assert "attachment; filename=current_users.csv" in response.headers.get(
        "Content-Disposition", ""
    )

    decoded = response.data.decode("utf-8")
    rows = list(csv.reader(StringIO(decoded)))
    assert rows[0] == ["first name", "last name", "onid"]
    assert ["Jane", "Doe", "jdoe"] in rows
    assert ["Old", "User", "olduser"] not in rows


def test_download_old_users_csv(test_client):
    """Old user CSV export should include only inactive users and expected columns."""
    admin = User(username="admin_csv_old", email="oldcsv@test.com", is_admin=True)
    admin.set_password("pass")

    active = User(
        username="activeuser",
        email="activeuser@test.com",
        name="Active User",
        is_active=True,
    )
    active.set_password("pass")

    inactive = User(
        username="retiredwa",
        email="retiredwa@test.com",
        name="Retired WA",
        is_active=False,
    )
    inactive.set_password("pass")

    db.session.add_all([admin, active, inactive])
    db.session.commit()

    with test_client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["is_admin"] = True

    response = test_client.get("/user_list/download/old")
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("Content-Type", "")
    assert "attachment; filename=old_users.csv" in response.headers.get(
        "Content-Disposition", ""
    )

    decoded = response.data.decode("utf-8")
    rows = list(csv.reader(StringIO(decoded)))
    assert rows[0] == ["first name", "last name", "onid"]
    assert ["Retired", "WA", "retiredwa"] in rows
    assert ["Active", "User", "activeuser"] not in rows


def test_download_current_users_csv_requires_login(test_client):
    """CSV export should require authentication."""
    response = test_client.get("/user_list/download/current")
    assert response.status_code == 401
    assert response.get_json() == {"error": "Authentication required"}


def test_download_old_users_csv_rejects_non_admin(test_client):
    """CSV export should reject authenticated non-admin users."""
    regular = User(username="regular_csv", email="regularcsv@test.com", is_admin=False)
    regular.set_password("pass")
    db.session.add(regular)
    db.session.commit()

    with test_client.session_transaction() as sess:
        sess["user_id"] = regular.id
        sess["is_admin"] = False

    response = test_client.get("/user_list/download/old")
    assert response.status_code == 403
    assert response.get_json() == {"error": "Admin access required"}


def test_download_current_users_csv_sanitizes_formula_cells(test_client):
    """CSV export should neutralize spreadsheet formula-leading values."""
    admin = User(
        username="admin_csv_sanitize", email="sanitize@test.com", is_admin=True
    )
    admin.set_password("pass")

    risky = User(
        username="=cmd",
        email="risky@test.com",
        name="=Jane +Doe",
        is_active=True,
    )
    risky.set_password("pass")

    db.session.add_all([admin, risky])
    db.session.commit()

    with test_client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["is_admin"] = True

    response = test_client.get("/user_list/download/current")
    assert response.status_code == 200

    decoded = response.data.decode("utf-8")
    rows = list(csv.reader(StringIO(decoded)))
    assert ["'=Jane", "'+Doe", "'=cmd"] in rows


def test_pastticket_resolution(test_client):
    """Test resolving a past ticket via POST (Happy Path)."""
    user = User(username="helper", email="help@test.com", is_admin=False)
    user.set_password("pass")
    db.session.add(user)

    t = Ticket(student_name="Old", table="T1", physics_course="Ph 211", status="live")
    db.session.add(t)
    db.session.commit()

    with test_client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["is_admin"] = False

    data = {"resolveReason": "helped", "numStds": 2}
    response = test_client.post(
        f"/pastticket/helper/{t.id}", data=data, follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Ticket resolved successfully" in response.data

    db.session.refresh(t)
    assert t.status == "closed"
    assert t.closed_reason == "helped"
    assert t.number_of_students == 2


def test_pastticket_forbidden_for_other_user(test_client):
    """Regular users should not resolve past tickets under another user's URL."""
    owner = User(username="owner", email="owner@test.com", is_admin=False)
    other = User(username="other", email="other@test.com", is_admin=False)
    owner.set_password("pass")
    other.set_password("pass")
    db.session.add_all([owner, other])

    t = Ticket(
        student_name="Student", table="T2", physics_course="Ph 212", status="live"
    )
    db.session.add(t)
    db.session.commit()

    with test_client.session_transaction() as sess:
        sess["user_id"] = owner.id
        sess["is_admin"] = False

    response = test_client.post(
        f"/pastticket/other/{t.id}", data={"resolveReason": "helped"}
    )
    assert response.status_code == 403


def test_pastticket_admin_can_access_any_user(test_client):
    """Admins should be able to resolve past tickets for any user's URL."""
    admin = User(username="admin_past", email="admin@test.com", is_admin=True)
    other = User(username="other_u", email="other@test.com", is_admin=False)
    admin.set_password("pass")
    other.set_password("pass")
    db.session.add_all([admin, other])

    t = Ticket(student_name="Old", table="T3", physics_course="Ph 213", status="live")
    db.session.add(t)
    db.session.commit()

    with test_client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["is_admin"] = True

    # Use a valid choice defined in ResolveTicketForm
    data = {"resolveReason": "helped", "numStds": 1}

    response = test_client.post(
        f"/pastticket/other_u/{t.id}", data=data, follow_redirects=True
    )

    assert response.status_code == 200

    db.session.refresh(t)
    assert t.status == "closed"
    assert t.closed_reason == "helped"


def test_flash_message_category_rendering(test_client):
    """Verify that flash messages are rendered with the correct CSS class."""
    # 1. Create a dummy admin user in the database (or use an existing one)

    admin = User(username="admin_test", email="admin_test@test.com", is_admin=True)
    admin.set_password("pass")
    db.session.add(admin)
    db.session.commit()

    # 2. Log in as the admin in the session
    with test_client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["is_admin"] = True

    # 3. Now trigger the 'success' flash via user registration
    data = {
        "first_name": "Test",
        "last_name": "User",
        "onid": "testflash",
        "is_admin": False,
    }

    # Submit the request
    response = test_client.post("/api/users_add", data=data, follow_redirects=True)

    # 4. Assertions
    assert response.status_code == 200
    assert b'class="flash-success"' in response.data
    assert b"User created successfully!" in response.data


def test_register_error_keeps_form_values_and_shows_suggestion(test_client):
    """Registration errors should keep entered values and provide guidance."""
    response = test_client.post(
        "/api/users_add",
        data={"first_name": "Jane", "last_name": "Doe", "onid": ""},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert b'value="Jane"' in response.data
    assert b'value="Doe"' in response.data
    assert b"ONID: This field is required." in response.data
    assert (
        b"Suggestion: Enter the ONID username only (for example: smithj)."
        in response.data
    )


def test_livequeuetickets_includes_in_progress_in_order(test_client):
    """Public live queue API should include both live and in-progress tickets in queue order."""
    t1 = Ticket(
        student_name="First", table="T1", physics_course="Ph 211", status="live"
    )
    t2 = Ticket(
        student_name="Second",
        table="T2",
        physics_course="Ph 212",
        status="in_progress",
    )
    t3 = Ticket(
        student_name="Third", table="T3", physics_course="Ph 213", status="live"
    )
    db.session.add_all([t1, t2, t3])
    db.session.commit()

    response = test_client.get("/api/livequeuetickets")

    assert response.status_code == 200
    payload = response.get_json()
    assert [ticket["student_name"] for ticket in payload] == [
        "First",
        "Second",
        "Third",
    ]
    assert [ticket["status"] for ticket in payload] == ["live", "in_progress", "live"]


def test_currentticket_displays_pacific_time(test_client):
    """Current ticket page should render UTC-backed timestamps in Pacific Time."""
    user = User(username="pacific_helper", email="pacific@test.com", is_admin=False)
    user.set_password("pass")
    db.session.add(user)

    t = Ticket(
        student_name="Time Test",
        table="T7",
        physics_course="Ph 211",
        status="in_progress",
        wa_id=user.id,
    )
    t.created_at = datetime(2026, 4, 2, 18, 58, 0, tzinfo=timezone.utc)
    db.session.add(t)
    db.session.commit()

    with test_client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["is_admin"] = False

    response = test_client.get(f"/currentticket/{t.id}")

    assert response.status_code == 200
    assert b"Apr 02 11:58:00 AM PDT" in response.data


def test_queue_closed_history_displays_pacific_opened_and_closed_times(test_client):
    """Queue history should render opened/closed times in Pacific Time."""
    user = User(username="queue_tz_user", email="queue_tz@test.com", is_admin=False)
    user.set_password("pass")
    db.session.add(user)

    t = Ticket(
        student_name="Queue Time Test",
        table="T11",
        physics_course="Ph 211",
        status="closed",
        wa_id=user.id,
    )
    t.created_at = datetime(2026, 4, 2, 18, 58, 0, tzinfo=timezone.utc)
    t.closed_at = datetime(2026, 4, 2, 20, 30, 0, tzinfo=timezone.utc)
    db.session.add(t)
    db.session.commit()

    with test_client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["is_admin"] = False

    response = test_client.get("/queue")

    assert response.status_code == 200
    # queue history currently renders Pacific-local clock times without TZ suffix
    assert b"Opened: 11:58 AM" in response.data
    assert b"Closed: 01:30 PM" in response.data
    # guard against regressing to raw UTC display
    assert b"Opened: 06:58 PM" not in response.data
    assert b"Closed: 08:30 PM" not in response.data


def test_export_archive_uses_pacific_date_boundaries(test_client, test_app):
    """Archive export should treat submitted dates as Pacific local dates, not UTC dates."""
    admin = User(username="admin_tz", email="admin_tz@test.com", is_admin=True)
    admin.set_password("pass")
    db.session.add(admin)

    pacific = ZoneInfo("America/Los_Angeles")
    closed_local = datetime(2026, 4, 2, 23, 30, 0, tzinfo=pacific)

    t = Ticket(
        student_name="LateLocalTicket",
        table="T9",
        physics_course="Ph 212",
        status="closed",
    )
    t.created_at = datetime(2026, 4, 2, 18, 15, 0, tzinfo=timezone.utc)
    t.closed_at = closed_local.astimezone(timezone.utc)
    db.session.add(t)
    db.session.commit()

    with test_client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["is_admin"] = True

    archive_dir = Path(test_app.root_path) / "data" / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)

    request_day = datetime.fromisoformat("2026-04-02").date()
    start_dt, _ = pacific_day_bounds_to_utc(request_day)
    _, end_dt = pacific_day_bounds_to_utc(request_day)
    expected_file = (
        archive_dir
        / f"wormhole_archive_{start_dt.date().isoformat()}_to_{end_dt.date().isoformat()}.csv"
    )
    existed_before = expected_file.exists()

    response = test_client.post(
        "/archive/export",
        data={"start_date": "2026-04-02", "end_date": "2026-04-02"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Archive created: wormhole_archive_" in response.data

    assert expected_file.exists()
    csv_content = expected_file.read_text(encoding="utf-8")
    assert "LateLocalTicket" in csv_content

    if not existed_before:
        expected_file.unlink()


def test_site_content_editor_rejects_google_sheets_edit_url(test_client):
    _login_as_admin(test_client)

    response = test_client.post(
        "/admin/site-content",
        data={
            "homepage_banner": "",
            "schedule_announcement": "Updated announcement",
            "schedule_hours": "Open Monday through Friday.",
            "schedule_note": "",
            "holiday_closures": "",
            "schedule_embed_url": (
                "https://docs.google.com/spreadsheets/d/" "abc123/edit#gid=0"
            ),
        },
    )

    assert response.status_code == 200
    assert (
        b"Schedule embed URL must be a published Google Sheets pubhtml URL."
        in response.data
    )


def test_site_content_editor_renders_multiple_holiday_closures(test_client):
    _login_as_admin(test_client)

    response = test_client.post(
        "/admin/site-content",
        data={
            "homepage_banner": "",
            "schedule_announcement": "Updated announcement",
            "schedule_hours": "Open Monday through Friday.",
            "schedule_note": "",
            "holiday_closures": "Memorial Day — Closed\nFinals Week — Reduced Hours",
            "schedule_embed_url": (
                "https://docs.google.com/spreadsheets/d/e/"
                "2PACX-1vExamplePublishedSheetId/pubhtml?widget=true&headers=false"
            ),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Memorial Day" in response.data
    assert b"Finals Week" in response.data


def test_site_content_editor_displays_audit_table(test_client):
    _login_as_admin(test_client)

    test_client.post(
        "/admin/site-content",
        data={
            "homepage_banner": "Audit test banner",
            "schedule_announcement": "Audit test announcement",
            "schedule_hours": "Open Monday through Friday.",
            "schedule_note": "",
            "holiday_closures": "",
            "schedule_embed_url": (
                "https://docs.google.com/spreadsheets/d/e/"
                "2PACX-1vExamplePublishedSheetId/pubhtml?widget=true&headers=false"
            ),
        },
    )

    response = test_client.get("/admin/site-content")

    assert response.status_code == 200
    assert b"Audit Information" in response.data
    assert b"schedule_announcement" in response.data
    assert b"site_admin" in response.data or b"example.com" in response.data
