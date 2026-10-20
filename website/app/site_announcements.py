"""Public announcement displayed across Delta Roblox except on Forms pages.

This uses the durable database, not session data or deployment environment
variables: an owner can publish/hide the message and see changes immediately.
"""
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from .database import SessionLocal
from .models import SiteAnnouncement, User


def announcement_for_page(request):
    """A Jinja context processor (works across separate site template engines)."""
    path = request.url.path
    if (path == "/forms" or path.startswith("/forms/")
            or (path == "/login" and request.query_params.get("intent") == "forms")):
        return {"site_announcement": None}
    try:
        with SessionLocal() as db:
            row = db.scalar(select(SiteAnnouncement).where(SiteAnnouncement.id == 1))
            if row and row.enabled and row.message.strip():
                # Materialize while the transaction/session is still open.
                author = db.get(User, row.updated_by) if row.updated_by else None
                avatar = (author.discord_avatar_url or "") if author else ""
                # Avatar values come from verified Discord OAuth, not Roblox.
                if not avatar.startswith(("https://cdn.discordapp.com/", "https://media.discordapp.net/")):
                    avatar = "/static/avatar.svg"
                return {"site_announcement": {
                    "message": row.message,
                    "tone": row.tone if row.tone in ("UPDATE", "EVENT", "IMPORTANT") else "UPDATE",
                    "link_label": row.link_label,
                    "link_path": row.link_path,
                    "author_name": author.discord_display_name if author else "Delta Leadership",
                    "author_username": author.discord_username if author else "",
                    "author_avatar": avatar,
                }}
    except SQLAlchemyError:
        # A database hiccup must never take down a public page or expose
        # unfinished schema migrations to visitors.
        pass
    return {"site_announcement": None}
