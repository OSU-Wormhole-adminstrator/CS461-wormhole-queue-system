import calendar
from datetime import date
from urllib.parse import urlparse

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import (
    BooleanField,
    DateField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    NumberRange,
    Optional,
    ValidationError,
)


def _subtract_months(from_date: date, months: int) -> date:
    """Return a date shifted back by whole months without external dependencies."""
    total_months = from_date.year * 12 + from_date.month - 1 - months
    target_year = total_months // 12
    target_month = (total_months % 12) + 1
    target_day = min(from_date.day, calendar.monthrange(target_year, target_month)[1])
    return date(target_year, target_month, target_day)


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Remember Me")
    submit = SubmitField("Sign In")


class TicketForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired()])
    phClass = SelectField(
        "Class",
        choices=[
            ("211", "211"),
            ("212", "212"),
            ("213", "213"),
            ("Ph 20x", "Ph 20x"),
            ("20X Ecampus", "20X Ecampus"),
            ("21X Ecampus", "21X Ecampus"),
        ],
        validators=[DataRequired()],
    )
    location = SelectField(
        "Location",
        choices=[("Teams", "Teams"), ("Zoom", "Zoom")],
        validators=[DataRequired()],
    )
    submit = SubmitField("Create")


class RegisterForm(FlaskForm):
    first_name = StringField("First Name", validators=[DataRequired()])
    last_name = StringField("Last Name", validators=[DataRequired()])
    onid = StringField("ONID", validators=[DataRequired()])
    is_admin = BooleanField("Administrator")
    submit = SubmitField("Create")


class RegisterBatchForm(FlaskForm):
    user_csv = FileField(
        "User CSV",
        validators=[FileRequired(), FileAllowed(["csv"], "Please upload a CSV file.")],
    )
    submit = SubmitField("Register Batch")


class ResetPasswordRequestForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Request Reset")


class ResetPasswordForm(FlaskForm):
    password = PasswordField("New Password", validators=[DataRequired()])
    password2 = PasswordField(
        "Re-enter Password", validators=[DataRequired(), EqualTo("password")]
    )
    submit = SubmitField("Change Password")


class DeleteUserForm(FlaskForm):
    confirm = StringField('Type "DELETE" to confirm', validators=[DataRequired()])
    submit = SubmitField("Confirm")


class ChangePassForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    old_password = PasswordField("Old Password", validators=[DataRequired()])
    password = PasswordField("New Password", validators=[DataRequired()])
    password2 = PasswordField(
        "Re-enter New Password", validators=[DataRequired(), EqualTo("password")]
    )
    submit = SubmitField("Change Password")


class EditUserForm(FlaskForm):
    first_name = StringField("First Name", validators=[Optional()])
    last_name = StringField("Last Name", validators=[Optional()])
    onid = StringField("ONID", validators=[Optional()])
    email = StringField("Email", validators=[Optional(), Email()])
    is_admin = SelectField(
        "Is Admin",
        choices=[
            ("", "Update"),
            ("true", "True"),
            ("false", "False"),
        ],
        validators=[Optional()],
    )
    is_active = SelectField(
        "Is Active",
        choices=[
            ("", "Update"),
            ("true", "True"),
            ("false", "False"),
        ],
        validators=[Optional()],
    )
    submit = SubmitField("Update")


class ResolveTicketForm(FlaskForm):
    numStds = IntegerField(
        "Number of Students", validators=[Optional(), NumberRange(min=1)]
    )
    resolveReason = SelectField(
        "Resolution Reason",
        choices=[
            ("helped", "Helped"),
            ("no_show", "No Show"),
            ("duplicate", "Duplicate"),
        ],
        validators=[DataRequired(message="Please select a reason.")],
    )
    submit = SubmitField("Submit")


class ExportArchiveForm(FlaskForm):
    start_date = DateField(
        "Start Date",
        validators=[DataRequired()],
        default=lambda: _subtract_months(date.today(), 3),
    )
    end_date = DateField("End Date", validators=[DataRequired()], default=date.today)
    submit = SubmitField("Download CSV")


class DeleteArchiveForm(FlaskForm):
    submit = SubmitField("Delete Selected")


class FlushQueueForm(FlaskForm):
    """Simple form to handle CSRF protection for the Flush Queue action."""

    submit = SubmitField("Flush Queue")


class ClearQueueForm(FlaskForm):
    """Simple form to handle CSRF protection for the Clear Queue action."""

    submit = SubmitField("Clear Queue")


class SiteContentForm(FlaskForm):
    """Admin-facing form for simple public homepage content fields.

    This form intentionally avoids raw HTML and large rich-text homepage
    sections. Sections containing links remain hardcoded in templates so admins
    cannot accidentally remove important navigation or introduce unsafe markup.
    """

    homepage_banner = TextAreaField(
        "Homepage Banner",
        validators=[Optional(), Length(max=500)],
        description="Optional message shown near the top of the homepage.",
    )
    schedule_announcement = StringField(
        "Schedule Announcement",
        validators=[DataRequired(), Length(max=200)],
    )
    schedule_hours = StringField(
        "Schedule Hours",
        validators=[DataRequired(), Length(max=250)],
    )
    schedule_note = TextAreaField(
        "Schedule Note",
        validators=[Optional(), Length(max=500)],
    )
    holiday_closures = TextAreaField(
        "Holiday Closures",
        validators=[Optional(), Length(max=1000)],
        description="Enter one closure per line.",
    )
    schedule_embed_url = StringField(
        "Google Sheets Schedule Embed URL",
        validators=[Optional(), Length(max=1000)],
    )
    submit = SubmitField("Save Website Changes")

    def validate_schedule_embed_url(self, field):
        value = (field.data or "").strip()

        if not value:
            return

        parsed = urlparse(value)

        is_https = parsed.scheme == "https"
        is_google_sheets = parsed.netloc == "docs.google.com"
        is_published_sheet = parsed.path.startswith(
            "/spreadsheets/d/e/"
        ) and parsed.path.endswith("/pubhtml")

        if not (is_https and is_google_sheets and is_published_sheet):
            raise ValidationError(
                "Schedule embed URL must be a published Google Sheets pubhtml URL."
            )
