from app import db
from app.email import send_email
from app.models import User


def _create_user(email="helper@oregonstate.edu", password="old-password", active=True):
    user = User(username=email.split("@")[0], email=email, is_active=active)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def test_password_reset_request_sends_email_for_active_user(test_client, monkeypatch):
    user = _create_user()
    sent_to = []

    def fake_send_password_reset_email(found_user):
        sent_to.append(found_user.email)

    monkeypatch.setattr(
        "app.routes.auth.send_password_reset_email", fake_send_password_reset_email
    )

    response = test_client.post(
        "/reset_password_request",
        data={"email": "Helper@OregonState.edu"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert sent_to == [user.email]
    assert b"If an account with that email exists" in response.data


def test_password_reset_request_does_not_reveal_unknown_email(test_client, monkeypatch):
    sent_to = []

    def fake_send_password_reset_email(found_user):
        sent_to.append(found_user.email)

    monkeypatch.setattr(
        "app.routes.auth.send_password_reset_email", fake_send_password_reset_email
    )

    response = test_client.post(
        "/reset_password_request",
        data={"email": "missing@oregonstate.edu"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert sent_to == []
    assert b"If an account with that email exists" in response.data
    assert b"No account" not in response.data


def test_password_reset_token_changes_password(test_client):
    user = _create_user()
    token = user.get_reset_password_token()

    response = test_client.post(
        f"/reset_password/{token}",
        data={"password": "new-password", "password2": "new-password"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    db.session.refresh(user)
    assert user.check_password("new-password")
    assert not user.check_password("old-password")
    assert b"Your password has been reset" in response.data


def test_invalid_password_reset_token_is_rejected(test_client):
    response = test_client.get(
        "/reset_password/not-a-real-token", follow_redirects=True
    )

    assert response.status_code == 200
    assert b"That password reset link is invalid or has expired" in response.data


def test_send_email_uses_configured_ses_sender_and_reply_to(test_app, monkeypatch):
    calls = []

    class FakeSesClient:
        def send_email(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr("app.email._ses_client", lambda: FakeSesClient())

    test_app.config["EMAIL_ENABLED"] = True
    test_app.config[
        "MAIL_DEFAULT_SENDER"
    ] = "Wormhole Physics <no-reply@physics.oregonstate.edu>"
    test_app.config[
        "MAIL_REPLY_TO"
    ] = "Wormhole Physics <Wormhole.Physics@oregonstate.edu>"

    with test_app.app_context():
        send_email(
            subject="Reset your Wormhole password",
            recipients=["helper@oregonstate.edu"],
            text_body="Reset text",
            html_body="<p>Reset HTML</p>",
        )

    assert calls == [
        {
            "Source": "Wormhole Physics <no-reply@physics.oregonstate.edu>",
            "Destination": {"ToAddresses": ["helper@oregonstate.edu"]},
            "Message": {
                "Subject": {
                    "Data": "Reset your Wormhole password",
                    "Charset": "UTF-8",
                },
                "Body": {
                    "Text": {"Data": "Reset text", "Charset": "UTF-8"},
                    "Html": {"Data": "<p>Reset HTML</p>", "Charset": "UTF-8"},
                },
            },
            "ReplyToAddresses": ["Wormhole Physics <Wormhole.Physics@oregonstate.edu>"],
        }
    ]
