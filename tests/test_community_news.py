"""Regression tests for the public community newsroom and relocated navigation."""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from website.app.database import Base
from website.app.models import SiteAnnouncement
from website.app.news import published_news


def test_newsroom_shows_only_current_staff_published_announcement(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'newsroom.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(engine)
    with session() as db:
        assert published_news(db) is None
        db.add(SiteAnnouncement(
            id=1, enabled=True, message="Boarding at JFK on Friday",
            tone="EVENT", link_label="See departures", link_path="/flights",
        ))
        db.commit()
        item = published_news(db)
        assert item is not None
        assert item["message"] == "Boarding at JFK on Friday"
        assert item["category"] == "Events & flights"
        assert item["link_path"] == "/flights"

        # Editors may hide or remove a banner, and previously withdrawn
        # announcements must never remain publicly displayed.
        row = db.get(SiteAnnouncement, 1)
        row.enabled = False
        db.commit()
        assert published_news(db) is None
        db.delete(row)
        db.commit()
        assert published_news(db) is None
    engine.dispose()


def test_main_navigation_moves_to_homepage_action_row():
    header = Path("website/templates/_unified_site_header.html").read_text()
    home = Path("website/templates/homepage.html").read_text()
    assert "request.url.path not in ['/', '/home']" not in header
    assert 'class="air-book-tabs air-site-links"' not in home
    assert 'class="standard-nav-row"' in header
    assert 'href="/home"' in header
    for label in ("Flights", "Forms", "News", "Partnerships", "SkyMiles"):
        assert f">{label}</a>" in header
    assert 'data-air-tab=' not in home


def test_newsroom_contains_only_community_updates():
    page = Path("website/templates/news.html").read_text()
    home = Path("website/templates/homepage.html").read_text()
    article_source = Path("website/app/news.py").read_text()
    assert "Announcements from our team" in home
    assert "Published by" in home
    assert "published_news" in article_source
    assert "article.body" in page
    assert "news.delta.com" not in page
    assert "news.delta.com" not in home
    assert "https://news.delta.com" not in article_source
