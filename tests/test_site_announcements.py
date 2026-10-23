"""Ownership banner regression coverage."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from website.app.main import app, _remove_site_announcement_record, _same_site_error_return, _expects_api_error
from website.app.database import Base
from website.app import site_announcements
from website.app.models import AuditLog, SiteAnnouncement


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


def test_ownership_and_staff_announcement_controls_are_permission_aware():
    main = src("app/main.py")
    editor = src("templates/admin.html")
    assert '@app.post("/owner/announcement")' in main
    assert '@app.post("/admin/announcement")' in main
    assert '@app.post("/staff/announcement")' in main
    for role in ("owner", "admin", "staff"):
        assert f'@app.post("/{role}/announcement/remove")' in main
    assert 'check_csrf(request, csrf)' in main
    assert 'actor = await require_owner(request, db)' in main
    assert 'actor = await require_admin(request, db)' in main
    assert 'actor = await require_staff(request, db)' in main
    assert 'announcement.updated_by != actor.id' in main
    assert 'action="SITE_ANNOUNCEMENT_REMOVED"' in main
    assert 'action="SITE_ANNOUNCEMENT_UPDATED"' in main
    assert 'id="owner-news-message"' in editor
    assert 'id="owner-news-enabled"' in editor
    assert '220 characters maximum' in editor
    assert 'action="/{{ panel_level|lower }}/announcement"' in editor
    assert 'action="/{{ panel_level|lower }}/announcement/remove"' in editor
    assert 'if announcement_can_remove' in editor
    assert 'Remove Website Announcement' in editor
    assert 'Remove your Announcement' in editor


def test_staff_cannot_remove_another_members_announcement(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'own-only.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine)
    with Session() as db:
        db.add(SiteAnnouncement(id=1, enabled=True, message="Crew notice", updated_by=1001))
        db.commit()
        with pytest.raises(HTTPException) as error:
            _remove_site_announcement_record(
                db, SimpleNamespace(id=2002), owner_override=False
            )
        assert error.value.status_code == 403
        assert db.get(SiteAnnouncement, 1).message == "Crew notice"
        assert db.scalar(select(AuditLog).where(AuditLog.action == "SITE_ANNOUNCEMENT_REMOVED")) is None
    engine.dispose()


def test_publisher_or_owner_removal_clears_banner_and_creates_audit(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'remove-owned.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine)
    with Session() as db:
        db.add(SiteAnnouncement(id=1, enabled=True, message="Staff announcement", updated_by=1001))
        db.commit()
        _remove_site_announcement_record(
            db, SimpleNamespace(id=1001), owner_override=False
        )
        assert db.get(SiteAnnouncement, 1) is None
        logged = db.scalar(select(AuditLog).where(AuditLog.action == "SITE_ANNOUNCEMENT_REMOVED"))
        assert logged.old_value["message"] == "Staff announcement"
        assert logged.new_value["removed_by"] == 1001
        db.add(SiteAnnouncement(id=1, enabled=True, message="Another author's news", updated_by=3003))
        db.commit()
        _remove_site_announcement_record(
            db, SimpleNamespace(id=9009), owner_override=True
        )
        assert db.get(SiteAnnouncement, 1) is None
        audits = db.scalars(select(AuditLog).where(AuditLog.action == "SITE_ANNOUNCEMENT_REMOVED")).all()
        assert len(audits) == 2
    engine.dispose()


def test_errors_are_modal_on_site_but_json_for_api_and_auth_stays_full_page():
    main = src("app/main.py")
    base = src("templates/base.html")
    community_base = src("templates/community_base.html")
    modal = src("templates/_site_error_modal.html")
    for layout in (base, community_base):
        assert '{% include "_site_error_modal.html" %}' in layout
        assert "/static/site-error-modal.css" in layout
    assert "popup.showModal()" in modal
    assert 'request.scope.get(\'session\', {}).pop(\'_site_error_popup\', none)' in modal
    assert '@app.exception_handler(HTTPException)' in main
    assert '@app.exception_handler(RequestValidationError)' in main
    assert '@app.exception_handler(Exception)' in main
    assert '"error.html"' in main
    assert '"application/json"' in main


def test_announcement_is_shared_across_layouts_and_accessible():
    public = src("templates/community_base.html")
    member = src("templates/base.html")
    welcome = src("templates/signin_success.html")
    header = src("templates/_unified_site_header.html")
    gallery = src("app/gallery.py")
    partial = src("templates/_site_announcement.html")
    css = src("static/site-announcement.css")
    for layout in (public, member, welcome):
        assert '{% include "_unified_site_header.html" %}' in layout
        assert "/static/site-announcement.css" in layout
    assert '{% include "_site_announcement.html" %}' in header
    assert "context_processors=[announcement_for_page]" in gallery
    assert 'role="region"' in partial
    assert 'aria-label="Community announcement"' in partial
    assert "site_announcement.link_path" in partial
    assert "@media(prefers-reduced-motion:reduce)" in css
    assert "deltaSiteNewsEnter" in css
