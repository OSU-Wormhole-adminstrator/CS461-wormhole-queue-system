import os

basedir = os.path.abspath(os.path.dirname(__file__))


def _env_bool(name, default="0"):
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _is_production_deployment():
    """Return True when the app is running in a known production context."""
    app_env = os.environ.get("APP_ENV", os.environ.get("FLASK_ENV", "")).strip().lower()
    return (
        app_env in {"production", "prod"}
        or os.environ.get("REQUIRE_DATABASE_URL") == "1"
        or os.environ.get("AWS_EXECUTION_ENV") is not None
        or os.environ.get("EB_ENVIRONMENT_NAME") is not None
    )


_DEFAULT_SECURE = "1" if _is_production_deployment() else "0"
_DEFAULT_URL_SCHEME = "https" if _DEFAULT_SECURE == "1" else "http"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-key"

    # Local development should run over plain HTTP with `flask run`.
    # Production deployments should set APP_ENV=production or explicitly set
    # the HTTPS variables below to 1 in the server environment.
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", _DEFAULT_SECURE)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PREFERRED_URL_SCHEME = os.environ.get("PREFERRED_URL_SCHEME", _DEFAULT_URL_SCHEME)
    FORCE_HTTPS = _env_bool("FORCE_HTTPS", _DEFAULT_SECURE)
    ENABLE_HSTS = _env_bool("ENABLE_HSTS", _DEFAULT_SECURE)

    # Amazon SES / transactional email settings for password reset emails.
    SES_REGION = os.environ.get("SES_REGION", "us-west-2")
    MAIL_DEFAULT_SENDER = os.environ.get(
        "MAIL_DEFAULT_SENDER",
        "Wormhole Physics <no-reply@physics.oregonstate.edu>",
    )
    MAIL_REPLY_TO = os.environ.get(
        "MAIL_REPLY_TO",
        "Wormhole Physics <Wormhole.Physics@oregonstate.edu>",
    )
    EMAIL_ENABLED = _env_bool("EMAIL_ENABLED", _DEFAULT_SECURE)
    RESET_PASSWORD_TOKEN_MAX_AGE = int(
        os.environ.get("RESET_PASSWORD_TOKEN_MAX_AGE", "3600")
    )
    RESET_PASSWORD_TOKEN_SALT = os.environ.get(
        "RESET_PASSWORD_TOKEN_SALT", "password-reset-salt"
    )

    # In production (Elastic Beanstalk), DATABASE_URL must be set as an
    # environment variable pointing to an RDS instance.
    # The SQLite fallback is kept only for local development.
    _db_url = os.environ.get("DATABASE_URL")
    if _db_url and _db_url.startswith("postgres://"):
        # SQLAlchemy 1.4+ requires "postgresql://" instead of "postgres://"
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _db_url or "sqlite:///" + os.path.join(basedir, "app.db")
