"""Ownership banner regression coverage."""
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from website.app.main import app
from website.app.database import Base
from website.app import site_announcements
from website.app.models import SiteAnnouncement


def src(path):
    return Path("website", path).read_text()


def request(path):
    return Request({"type": "http", "method": "GET", "path": path,
                    "root_path": "", "query_string": b"",
                    "headers": [], "scheme": "https", "server": ("example.test", 443)})


def test_forms_paths_are_omitted_from_announcement_rendering():
    # Critical privacy/intent: all Forms screens must stay announcement-free,
    # even when an announcement is enabled in the database.
    assert site_announcements.announcement_for_page(request("/forms")) == {"site_announcement": None}
    assert site_announcements.announcement_for_page(request("/forms/new")) == {"site_announcement": None}
    assert site_announcements.announcement_for_page(request("/forms/application/edit")) == {"site_announcement": None}


def test_published_announcement_visible_on_non_forms_pages(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'site-announcement.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine)
    with Session() as db:
        db.add(SiteAnnouncement(id=1, message="Our next flight starts soon!", enabled=True,
                                tone="EVENT", link_label="View flights", link_path="/flights"))
        db.commit()
    monkeypatch.setattr(site_announcements, "SessionLocal", Session)
    for path in ("/", "/flights", "/core-partnerships", "/owner", "/login",
                 "/dashboard", "/signup", "/signin/success", "/gallery/manage"):
        found = site_announcements.announcement_for_page(request(path))["site_announcement"]
        assert found["message"] == "Our next flight starts soon!"
        assert found["tone"] == "EVENT"
        assert found["link_path"] == "/flights"
    engine.dispose()


def test_hidden_announcement_not_shown(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'hidden.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine)
    with Session() as db:
        db.add(SiteAnnouncement(id=1, message="Archived news", enabled=False, tone="UPDATE"))
        db.commit()
    monkeypatch.setattr(site_announcements, "SessionLocal", Session)
    assert site_announcements.announcement_for_page(request("/")) == {"site_announcement": None}
    engine.dispose()


def test_only_owner_can_modify_announcement():
    main = src("app/main.py")
    editor = src("templates/admin.html")
    for expected in (
        '@app.post("/owner/announcement")',
        'check_csrf(request, csrf)',
        'actor = await require_owner(request, db)',
        'action="SITE_ANNOUNCEMENT_UPDATED"',
        'db.commit()',
    ):
        assert expected in main
    assert '{% if panel_level == \'OWNER\' %}' in editor
    assert 'action="/owner/announcement"' in editor
    assert 'id="owner-news-message"' in editor
    assert 'id="owner-news-enabled"' in editor
    assert '220 characters maximum' in editor


def test_announcement_is_shared_across_layouts_and_accessible():
    public = src("templates/community_base.html")
    member = src("templates/base.html")
    welcome = src("templates/signin_success.html")
    gallery = src("app/gallery.py")
    partial = src("templates/_site_announcement.html")
    css = src("static/site-announcement.css")
    for layout in (public, member, welcome):
        assert '{% include "_site_announcement.html" %}' in layout
        assert "/static/site-announcement.css" in layout
    assert "context_processors=[announcement_for_page]" in gallery
    assert 'role="region"' in partial
    assert 'aria-label="Community announcement"' in partial
    assert "site_announcement.link_path" in partial
    assert "@media(prefers-reduced-motion:reduce)" in css
    assert "deltaSiteNewsEnter" in css
