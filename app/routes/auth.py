# app/routes/auth.py
import sqlalchemy as sa
from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app import db
from app.email import send_password_reset_email
from app.forms import ResetPasswordForm, ResetPasswordRequestForm
from app.models import User

auth_bp = Blueprint("auth", __name__)


# -------------------------------
# POST /api/login (The Logic)
# -------------------------------
@auth_bp.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    user = User.query.filter_by(username=username).first()

    if user and user.check_password(password):
        if not user.is_active:
            return jsonify({"error": "This account has been deactivated"}), 401
        session["user_id"] = user.id
        session["is_admin"] = user.is_admin
        return jsonify({"message": "Login successful", "is_admin": user.is_admin}), 200

    return jsonify({"error": "Invalid credentials"}), 401


# -------------------------------
# POST /api/logout
# -------------------------------
@auth_bp.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out successfully"}), 200


# -------------------------------
# GET /api/check-session
# -------------------------------
@auth_bp.route("/api/check-session", methods=["GET"])
def check_session():
    if "user_id" in session:
        # ensure account still exists and is active
        user = User.query.get(session.get("user_id"))
        if user is None or not user.is_active:
            session.clear()
            return jsonify({"logged_in": False}), 200
        return jsonify(
            {"logged_in": True, "is_admin": session.get("is_admin", False)}
        ), 200

    return jsonify({"logged_in": False}), 200


# -------------------------------
# GET /reset_password_request (Render a simple reset request form)
# -------------------------------
@auth_bp.route("/reset_password_request", methods=["GET", "POST"])
def reset_password_request():
    form = ResetPasswordRequestForm()
    if request.method == "POST":
        if form.validate_on_submit():
            email = form.email.data.strip().lower()
            user = User.query.filter(sa.func.lower(User.email) == email).first()
            current_app.logger.info("Password reset requested for: %s", email)

            if user and user.is_active:
                try:
                    send_password_reset_email(user)
                except Exception:
                    current_app.logger.exception(
                        "Password reset email failed for user id %s", user.id
                    )

        flash(
            "If an account with that email exists, check your inbox for reset instructions.",
            "info",
        )
        return redirect(url_for("views.assistant_login"))
    return render_template("reset_password_request.html", form=form)


# -------------------------------
# GET /reset_password/<token> (Render password reset form)
# -------------------------------
@auth_bp.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = User.verify_reset_password_token(token)
    if user is None or not user.is_active:
        flash("That password reset link is invalid or has expired.", "error")
        return redirect(url_for("auth.reset_password_request"))

    form = ResetPasswordForm()
    if request.method == "POST":
        if not form.validate_on_submit():
            flash("Passwords do not match or are invalid.", "error")
            return render_template("reset_password.html", form=form)

        user.set_password(form.password.data)
        db.session.commit()
        flash("Your password has been reset. You may now sign in.", "success")
        return redirect(url_for("views.assistant_login"))
    return render_template("reset_password.html", form=form)
