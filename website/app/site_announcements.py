"""Public announcement displayed across Delta Roblox except on Forms pages.

This uses the durable database, not session data or deployment environment
variables: an owner can publish/hide the message and see changes immediately.
"""
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from .database import SessionLocal
from .models import SiteAnnouncement


def announcement_for_page(request):
    """A Jinja context processor (works across separate site template engines)."""
    path = request.url.path
    if path == "/forms" or path.startswith("/forms/"):
        return {"site_announcement": None}
    try:
        with SessionLocal() as db:
            row = db.scalar(select(SiteAnnouncement).where(SiteAnnouncement.id == 1))
            if row and row.enabled and row.message.strip():
                # Materialize while the transaction/session is still open.
                return {"site_announcement": {
                    "message": row.message,
                    "tone": row.tone if row.tone in ("UPDATE", "EVENT", "IMPORTANT") else "UPDATE",
                    "link_label": row.link_label,
                    "link_path": row.link_path,
                }}
    except SQLAlchemyError:
        # A database hiccup must never take down a public page or expose
        # unfinished schema migrations to visitors.
        pass
    return {"site_announcement": None}
