"""Email helpers for Wormhole transactional messages."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import current_app, render_template, url_for

if TYPE_CHECKING:
    from app.models import User


def _ses_client():
    """Create an Amazon SES client using the configured AWS region."""
    import boto3

    return boto3.client("ses", region_name=current_app.config["SES_REGION"])


def send_email(
    subject: str,
    recipients: list[str],
    text_body: str,
    html_body: str,
) -> None:
    """Send a transactional email through Amazon SES.

    Email delivery can be disabled for local development and tests with
    EMAIL_ENABLED=0. When disabled, this function logs the skipped send without
    exposing reset tokens or other sensitive message contents.
    """
    if not current_app.config.get("EMAIL_ENABLED", True):
        current_app.logger.info(
            "Email sending disabled; skipped transactional email to %s",
            ", ".join(recipients),
        )
        return

    reply_to = current_app.config.get("MAIL_REPLY_TO")
    request: dict[str, object] = {
        "Source": current_app.config["MAIL_DEFAULT_SENDER"],
        "Destination": {"ToAddresses": recipients},
        "Message": {
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {
                "Text": {"Data": text_body, "Charset": "UTF-8"},
                "Html": {"Data": html_body, "Charset": "UTF-8"},
            },
        },
    }

    if reply_to:
        request["ReplyToAddresses"] = [reply_to]

    _ses_client().send_email(**request)


def send_password_reset_email(user: "User") -> None:
    """Send a password reset email to an existing active user."""
    token = user.get_reset_password_token()
    reset_url = url_for("auth.reset_password", token=token, _external=True)

    send_email(
        subject="Reset your Wormhole password",
        recipients=[user.email],
        text_body=render_template(
            "email/reset_password.txt", user=user, reset_url=reset_url
        ),
        html_body=render_template(
            "email/reset_password.html", user=user, reset_url=reset_url
        ),
    )
