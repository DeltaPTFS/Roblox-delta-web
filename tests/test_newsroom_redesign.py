"""Visual and data-safety checks for the community newsroom redesign."""
from pathlib import Path

from fastapi.testclient import TestClient
from website.app.main import app

ROOT = Path("website")


def test_newsroom_has_real_layout_and_no_phantom_headlines():
    template = (ROOT / "templates/news.html").read_text(encoding="utf-8")
    assert 'class="news-hero"' in template
    assert 'class="news-update-card news-update-live"' in template
    assert 'class="news-update-card news-update-empty"' in template
    assert 'class="news-explore-grid"' in template
    assert 'class="news-footer"' in template
    assert "/static/gallery/delta-centennial.webp" in template
    assert 'href="/static/news-editorial.css?v=20261106-refresh"' in template
    assert 'href="/static/site-appearance.css?v=20261106-news"' in template
    assert "No ACTIVE NEWS" not in template
    assert "news.delta.com" not in template
    assert "announcement.message" in template
    assert "Nothing published yet." in template
    assert "if manage_url" in template
    assert "site-theme.js" in template


def test_newsroom_css_separates_cards_and_handles_dark_and_mobile():
    stylesheet = (ROOT / "static/news-editorial.css").read_text(encoding="utf-8")
    for element in (
        ".news-header-inner", ".news-hero", ".news-update-card",
        ".news-side-panel", ".news-explore-grid", ".news-explore-card",
        ".news-editor-panel", ".news-footer"
    ):
        assert element in stylesheet
    assert "grid-template-columns:repeat(3,minmax(0,1fr))" in stylesheet
    assert "grid-template-columns:1fr" in stylesheet
    assert "@media(max-width:760px)" in stylesheet
    assert '@media(prefers-reduced-motion:reduce)' in stylesheet
    assert 'html[data-site-theme="dark"]' in stylesheet
    assert "background:#101d37" in stylesheet


def test_public_newsroom_renders_and_is_styled_without_login():
    with TestClient(app) as client:
        page = client.get("/news")
        assert page.status_code == 200
        assert "Latest announcements" in page.text
        assert "Explore Delta Roblox" in page.text
        stylesheet = client.get("/static/news-editorial.css")
        assert stylesheet.status_code == 200
        assert "news-update-card" in stylesheet.text
