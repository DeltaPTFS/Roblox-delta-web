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
    user = None
    try:
        user = linked_user_from_session(request, db)
        level = permission(user, get_settings()) if user else "MEMBER"
    except SQLAlchemyError:
        level = "MEMBER"
    # The Newsroom is public. Reuse the same cached session identity as Home for
    # its shared header, without initiating authentication or role refreshes.
    guest = request.session.get("forms_identity")
    viewer = ({"id": user.discord_user_id, "name": user.discord_display_name}
              if user else guest if isinstance(guest, dict) else None)
    manage_url = "/owner#news-article-editor" if level == "OWNER" else (f"/{level.lower()}#site-announcement-editor" if level in ("ADMIN", "STAFF") else None)

    # Imported when handling a request to avoid creating an import cycle while
    # the main application imports and mounts this router.
    from .main import context as site_context
    page = site_context(
        request, articles=articles, announcement=None, manage_url=manage_url,
        viewer=viewer, profile_user=user, auth=level,
    )
    return templates.TemplateResponse(
        "news.html",
        page,
        headers={"Cache-Control": "private, no-store", "Vary": "Cookie"},
    )


@router.get("/amex", response_class=HTMLResponse)
async def amex_cards(request: Request, db: Session = Depends(get_db)):
    """Public information only; all roleplay card registration happens in Discord."""
    settings = get_settings()
    try:
        user = linked_user_from_session(request, db)
    except SQLAlchemyError:
        db.rollback()
        user = None
    guest = request.session.get("forms_identity")
    viewer = {"id": user.discord_user_id, "name": user.discord_display_name} if user else guest
    member = bool((user and user.discord_verified_at and user.discord_role_ids)
                  or (isinstance(guest, dict) and guest.get("main_member"))
                  or request.session.get("discord_join_status") in ("joined", "already_member"))
    from .main import context
    return templates.TemplateResponse("amex.html", context(
        request, viewer=viewer, profile_user=user, main_discord_member=member,
        discord_href="https://discord.com/channels/" + settings.discord_guild_id if member and settings.discord_guild_id else settings.discord_invite_url,
        auth=permission(user, settings) if user else "MEMBER",
    ), headers={"Cache-Control": "private, no-store", "Vary": "Cookie"})


@router.post("/internal/news/publish")
async def publish_bot_news(request: Request, db: Session = Depends(get_db)):
    """Use the same owner-only newsroom and audit log as the website editor."""
    import re
    import httpx
    from datetime import datetime, timezone
    from fastapi import HTTPException
    from .community import internal_secret
    from .models import AuditLog, Status

    internal_secret(request)
    settings = get_settings()
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(422, "Invalid news payload")
    actor_id = str(data.get("actor_id", ""))
    if not re.fullmatch(r"\d{15,22}", actor_id):
        raise HTTPException(422, "Invalid author")
    actor = db.scalar(select(User).where(User.discord_user_id == actor_id))
    if not actor or actor.account_status != Status.ACTIVE:
        raise HTTPException(403, "An active Ownership website account is required")
    if not settings.discord_guild_id or not settings.discord_bot_token:
        raise HTTPException(503, "Live Discord role verification unavailable")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                f"https://discord.com/api/v10/guilds/{settings.discord_guild_id}/members/{actor_id}",
                headers={"Authorization": "Bot " + settings.discord_bot_token})
    except httpx.HTTPError:
        raise HTTPException(503, "Live Discord role verification unavailable")
    if response.status_code == 404:
        raise HTTPException(403, "Not a member of Delta Discord")
    if response.status_code != 200:
        raise HTTPException(503, "Live Discord role verification unavailable")
    if not set(map(str, response.json().get("roles", []))) & settings.ids(settings.owner_discord_role_ids):
        raise HTTPException(403, "Only Ownership may publish news")
    title, body = data.get("title"), data.get("body")
    if not isinstance(title, str) or not isinstance(body, str):
        raise HTTPException(422, "Title and article are required")
    title = " ".join(title.split())
    body = body.replace("\r\n", "\n").strip()
    if not 1 <= len(title) <= 180 or not 1 <= len(body.split()) <= 10000 or len(body.encode("utf-8")) > 500000:
        raise HTTPException(422, "Invalid article length")
    published = data.get("published") is True
    article = CommunityNewsArticle(title=title, body=body, published=published, author_id=actor.id,
                                   created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    db.add(article)
    db.flush()
    db.add(AuditLog(staff_user_id=actor.id, target_user_id=None, action="COMMUNITY_NEWS_CREATED",
                    old_value=None, new_value={"id": article.id, "title": title, "published": published, "words": len(body.split())},
                    reason="Ownership saved article using /web-news",
                    security_metadata={"source": "deltaptfs-bot"}))
    db.commit()
    return {"id": article.id, "published": published}


@router.get("/release-info")
def release_info():
    """Public production deployment metadata for the community release notifier."""
    import os
    import re
    from fastapi.responses import JSONResponse
    sha = os.environ.get("VERCEL_GIT_COMMIT_SHA", "")
    if os.environ.get("VERCEL_ENV") != "production" or not re.fullmatch(r"[0-9a-f]{40}", sha):
        return JSONResponse({"status": "unavailable"}, status_code=503, headers={"Cache-Control": "no-store"})
    lines = os.environ.get("VERCEL_GIT_COMMIT_MESSAGE", "").splitlines()
    return JSONResponse({"commit": sha, "summary": (lines[0][:280] if lines else "Website update"), "environment": "production"}, headers={"Cache-Control": "no-store"})
