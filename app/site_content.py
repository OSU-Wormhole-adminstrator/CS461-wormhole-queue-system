from __future__ import annotations

from typing import Optional

import sqlalchemy as sa

from app import db
from app.models import SiteContent

DEFAULT_SITE_CONTENT: dict[str, str] = {
    "homepage_banner": "",
    "schedule_announcement": "The Wormhole is open for collaboration during regular library hours.",
    "schedule_hours": (
        "Wormhole Assistant availability is shown in the schedule below."
    ),
    "schedule_note": (
        "NOTE: The Wormhole may close at 4 PM on Mondays and Wednesdays "
        "for departmental colloquia."
    ),
    "holiday_closures": "Assistants are unavailable on OSU holidays.",
    "schedule_embed_url": (
        "https://docs.google.com/spreadsheets/d/e/"
        "2PACX-1vRcotW2LQyMMUHgBjvig-ZcHnybkT4_0XfiHDp-IVeqkX7VGh4vtr"
        "XBuHmDfTAVHdmHM2jcHInYuwOn/pubhtml?widget=true&headers=false"
    ),
}


def get_site_content() -> dict[str, str]:
    """Return editable website content with database values overriding defaults."""

    content = DEFAULT_SITE_CONTENT.copy()

    rows = db.session.execute(sa.select(SiteContent)).scalars()
    for row in rows:
        content[row.key] = row.value

    return content


def get_site_content_rows() -> list[SiteContent]:
    """Return stored content rows for admin audit display."""

    return list(
        db.session.execute(sa.select(SiteContent).order_by(SiteContent.key)).scalars()
    )


def save_site_content(
    key: str,
    value: str,
    updated_by_id: Optional[int] = None,
) -> None:
    row = db.session.get(SiteContent, key)

    if row is None:
        row = SiteContent(
            key=key,
            value=value,
            updated_by_id=updated_by_id,
        )
        db.session.add(row)
    elif row.value != value:
        row.value = value
        row.updated_by_id = updated_by_id


def save_site_content_bulk(
    updates: dict[str, str],
    updated_by_id: Optional[int] = None,
) -> None:
    """Save all supported editable fields in a single database transaction."""

    allowed_keys = set(DEFAULT_SITE_CONTENT)

    for key, value in updates.items():
        if key not in allowed_keys:
            raise ValueError(f"Unsupported site content key: {key}")

        save_site_content(
            key=key,
            value=value.strip(),
            updated_by_id=updated_by_id,
        )

    db.session.commit()


def split_lines(value: str) -> list[str]:
    """Convert multiline text into clean non-empty lines."""

    return [line.strip() for line in value.splitlines() if line.strip()]
