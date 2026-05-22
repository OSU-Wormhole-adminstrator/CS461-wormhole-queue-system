# run.py
import os

import sqlalchemy as sa
from dotenv import load_dotenv
from sqlalchemy import orm

from app import create_app, db, socketio
from app.models import Skipped, Ticket, User

# Load project environment variables before importing the Flask app.  The app's
# config is evaluated during import, so these values must be available first.
load_dotenv("wormhole.env")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("ALLOW_SQLITE_FALLBACK", "1")
os.environ.setdefault("FORCE_HTTPS", "0")
os.environ.setdefault("ENABLE_HSTS", "0")
os.environ.setdefault("SESSION_COOKIE_SECURE", "0")
os.environ.setdefault("PREFERRED_URL_SCHEME", "http")

app = create_app()


@app.shell_context_processor
def make_shell_context():
    return {
        "sa": sa,
        "orm": orm,
        "db": db,
        "User": User,
        "Ticket": Ticket,
        "Skipped": Skipped,
    }


if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=5000)
