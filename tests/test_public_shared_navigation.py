"""Public pages use one consistent homepage navigation without requiring sign-in."""
from pathlib import Path

from fastapi.testclient import TestClient
from website.app.main import app

ROOT = Path("website")


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_public_layout_owns_navigation_brand_and_actions():
    header = read("templates/_unified_site_header.html")
    base = read("templates/community_base.html")
    css = read("static/public-navigation.css")
    assert '{% set public_navigation = true %}' in base
    assert base.count('include "_unified_site_header.html"') == 1
    assert 'delta-public-site theme-' in base
    assert "public-navigation.css" in base
    assert 'class="delta-home-signup" href="/signup"' in header
    assert 'class="delta-home-login" href="/login"' in header
    assert 'class="delta-home-notifications" href="/news"' in header
    assert 'class="delta-home-flight-search" href="/flights"' in header
    assert "if public_navigation is defined and public_navigation" in header
    assert 'class="community-account-slot"' in header
    assert 'class="sky-nav-dropdown unified-menu-dropdown"' in header
    assert "body.delta-public-site" in css
    assert ".standard-nav-row{display:none!important}" in css
    assert "body.delta-public-site .delta-home-login" in css
    assert css.count("background:#06182e!important") >= 2


def test_newsroom_reuses_shared_header_and_preserves_article_editor():
    template = read("templates/news.html")
    route = read("app/news.py")
    base = read("templates/community_base.html")
    assert '{% extends "community_base.html" %}' in template
    assert 'class="news-site-header"' not in template
    assert "article.body" in template
    assert "if manage_url" in template
    assert 'class="news-footer"' in template
    assert "{% block footer %}" in template
    assert "{% block footer %}" in base
    assert "site_context(" in route
    assert "profile_user=user" in route
    assert "viewer=viewer" in route
    assert "Cache-Control" in route


def test_guest_can_navigate_public_home_news_and_partnerships():
    with TestClient(app) as client:
        for path in ("/home", "/news", "/partnerships", "/experience"):
            page = client.get(path)
            assert page.status_code == 200, (path, page.status_code)
            assert page.text.count('id="site-header"') == 1, path
            assert 'class="delta-home-signup" href="/signup"' in page.text, path
            assert 'class="delta-home-login" href="/login"' in page.text, path
            assert 'href="/news" aria-label="Community announcements"' in page.text, path
            assert 'id="sky-nav-panel"' in page.text, path
            assert "public-navigation.css" in page.text, path
            assert 'delta-public-site' in page.text, path
        news = client.get("/news")
        assert "Latest announcements" in news.text
        assert 'class="news-site-header"' not in news.text
        assert 'class="news-footer"' in news.text


def test_flight_permission_check_is_not_weakened():
    # The shared menu can link to Flights, but the route remains gated.
    main = read("app/main.py")
    assert 'if not user and not discord_member:' in main
    assert '"/login?intent=community&next=%2Fflights"' in main
