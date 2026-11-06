"""Public community newsroom, backed by the existing staff announcement editor.

No external airline news is injected. A post appears only while its
owner/staff-approved website announcement is explicitly published.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import SiteAnnouncement, CommunityNewsArticle, User
from .security import linked_user_from_session, permission

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


def published_news(db: Session):
    """Read the currently published community update; never expose removed drafts."""
    try:
        row = db.scalar(select(SiteAnnouncement).where(
            SiteAnnouncement.id == 1,
            SiteAnnouncement.enabled.is_(True),
        ))
        if row is None or not row.message.strip():
            return None
        author = db.get(User, row.updated_by) if row.updated_by is not None else None
        return {
            "message": row.message,
            "category": {
                "UPDATE": "Community update",
                "EVENT": "Events & flights",
                "IMPORTANT": "Important notice",
            }.get(row.tone, "Community update"),
            "date": row.updated_at.strftime("%B %d, %Y") if row.updated_at else None,
            "author": author.discord_display_name if author else "Delta Roblox Team",
            "link_label": row.link_label,
            "link_path": row.link_path,
        }
    except SQLAlchemyError:
        # A database outage must not leak unpublished content or break the newsroom.
        return None



def published_articles(db: Session, limit: int = 12):
    """Published owner news only, newest first; safe when migrations are pending."""
    try:
        rows = db.scalars(
            select(CommunityNewsArticle)
            .where(CommunityNewsArticle.published.is_(True))
            .order_by(CommunityNewsArticle.updated_at.desc(), CommunityNewsArticle.id.desc())
            .limit(limit)
        ).all()
        return rows
    except SQLAlchemyError:
        db.rollback()
        return []


@router.get("/news", response_class=HTMLResponse)
async def community_news(request: Request, db: Session = Depends(get_db)):
    articles = published_articles(db)
    try:
        user = linked_user_from_session(request, db)
        level = permission(user, get_settings()) if user else "MEMBER"
    except SQLAlchemyError:
        level = "MEMBER"
    manage_url = f"/{level.lower()}#news-article-editor" if level in ("OWNER", "ADMIN", "STAFF") else None
    return templates.TemplateResponse(
        "news.html",
        {"request": request, "articles": articles, "announcement": None, "manage_url": manage_url},
        headers={"Cache-Control": "private, no-store", "Vary": "Cookie"},
    )
