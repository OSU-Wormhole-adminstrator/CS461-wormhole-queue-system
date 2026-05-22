# app/__init__.py
import os

from flask import Flask, jsonify, redirect, request
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config

# Extensions are initialized at the top level
db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO()


def create_app(testing=False):
    """
    Create and configure the Flask application instance.

    Parameters
    ----------
    testing : bool, optional
        If True, configure the application for testing. This enables
        Flask's testing mode, uses an in-memory SQLite database, disables
        CSRF protection, and sets a deterministic secret key.

    Returns
    -------
    Flask
        The configured Flask application instance.
    """
    app = Flask(__name__)

    # ---------------------------------------------------
    # Configuration
    # ---------------------------------------------------
    app.config.from_object(Config)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    if testing:
        app.config["TESTING"] = True
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["WTF_CSRF_ENABLED"] = False
        app.config["SECRET_KEY"] = "test-secret"
        app.config["SESSION_COOKIE_SECURE"] = False
        app.config["FORCE_HTTPS"] = False
        app.config["ENABLE_HSTS"] = False
        app.config["PREFERRED_URL_SCHEME"] = "http"
        app.config["EMAIL_ENABLED"] = False
    elif (
        os.environ.get("REQUIRE_DATABASE_URL") == "1"
        and not os.environ.get("DATABASE_URL")
        and os.environ.get("ALLOW_SQLITE_FALLBACK") != "1"
    ):
        raise RuntimeError(
            "DATABASE_URL must be set when REQUIRE_DATABASE_URL=1. "
            "Set ALLOW_SQLITE_FALLBACK=1 only for local development."
        )

    @app.before_request
    def enforce_https():
        if not app.config.get("FORCE_HTTPS", False):
            return None
        if request.path == "/health":
            return None
        if request.is_secure:
            return None
        if request.headers.get("X-Forwarded-Proto", "http").lower() == "https":
            return None
        return redirect(request.url.replace("http://", "https://", 1), code=308)

    @app.after_request
    def add_security_headers(response):
        if app.config.get("ENABLE_HSTS", False) and request.is_secure:
            response.headers[
                "Strict-Transport-Security"
            ] = "max-age=31536000; includeSubDomains"
        return response

    # ---------------------------------------------------
    # Initialize Extensions
    # ---------------------------------------------------
    db.init_app(app)
    migrate.init_app(app, db)
    socketio.init_app(app, cors_allowed_origins="*")

    from app.time_utils import format_pacific

    app.add_template_filter(format_pacific, "datetime_pacific")

    # ---------------------------------------------------
    # Internal Imports & Registration
    # ---------------------------------------------------
    # Moving these inside create_app prevents circular imports and E402 errors.
    # The '# noqa: F401' tells Ruff that although the import isn't used directly
    # in this file, it is intentional (for registering models and events).
    from app import models  # noqa: F401
    from app.archive_utils import register_archive_cli
    from app.queue_maintenance import register_queue_maintenance_cli
    from app.routes import queue_events  # noqa: F401
    from app.routes.auth import auth_bp
    from app.routes.error import error_bp
    from app.routes.tickets import tickets_bp
    from app.routes.views import views_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(tickets_bp)
    app.register_blueprint(error_bp)
    register_archive_cli(app)
    register_queue_maintenance_cli(app)

    # ---------------------------------------------------
    # Health Check Route
    # ---------------------------------------------------
    @app.route("/health")
    def health_check():
        return jsonify({"message": "Wormhole Queue System API is running"}), 200

    # ---------------------------------------------------
    # Template context processors
    # ---------------------------------------------------
    from types import SimpleNamespace

    @app.context_processor
    def inject_current_user():
        from flask import session

        try:
            if "user_id" in session:
                from app.models import User

                u = db.session.get(User, session["user_id"])
                if u:
                    return {
                        "current_user": SimpleNamespace(
                            is_admin=bool(u.is_admin),
                            is_anonymous=False,
                            username=u.username,
                        )
                    }
        except Exception:
            # keep silent on DB errors; fall back to anonymous
            pass

        return {
            "current_user": SimpleNamespace(
                is_admin=False, is_anonymous=True, username=""
            )
        }

    from app.routes.users import user_bp

    app.register_blueprint(user_bp)

    return app
