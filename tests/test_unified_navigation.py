"""Shared Delta header and SkyMiles Navigation Hub regression coverage."""
from pathlib import Path

from fastapi.testclient import TestClient
from website.app.main import app
from website.app.database import Base, engine


def read(path):
    return Path("website", path).read_text()


def test_shared_header_is_reused_on_all_site_layouts():
    shared = read("templates/_unified_site_header.html")
    for page in ("community_base.html", "base.html", "signin_success.html"):
        source = read("templates/" + page)
        assert '{% include "_unified_site_header.html" %}' in source
        assert "/static/unified-delta-navigation.css" in source
        assert "/static/unified-delta-navigation.js" in source

    assert 'id="site-header"' in shared
    assert 'class="community-brand"' in shared
    assert 'class="community-primary-nav"' in shared
    assert 'class="sky-nav-dropdown unified-menu-dropdown"' in shared
    assert 'id="sky-nav-panel"' in shared
    assert 'class="sky-menu-heading"' in shared
    assert "Navigation Hub" in shared
    assert shared.count('id="delta-language-select"') == 1
    assert '{% include "_site_announcement.html" %}' in shared
    assert '{% include "_account_panel.html" %}' in shared


def test_menu_keeps_role_based_access_and_covers_all_destinations():
    header = read("templates/_unified_site_header.html")
    for path in ("/", "/flights", "/forms", "/core-partnerships",
                 "/dashboard", "/miles", "/trips", "/rewards",
                 "/profile", "/settings", "/activity"):
        assert 'href="' + path + '"' in header
    assert 'nav_level in ("OWNER","ADMIN","STAFF")' in header
    assert "'/owner' if nav_level == 'OWNER'" in header
    assert "'/admin' if nav_level == 'ADMIN'" in header
    assert "'/staff'" in header
    assert 'href="/forms/new"' in header
    assert 'href="/signup"' in header
    assert 'href="/login"' in header
    assert "main_discord_member" in header
    assert 'href="/gallery/manage"' not in header


def test_mobile_menu_and_account_panel_have_accessible_separate_behavior():
    js = read("static/unified-delta-navigation.js")
    css = read("static/unified-delta-navigation.css")
    assert "nav.addEventListener('toggle'" in js
    assert "account.addEventListener('toggle'" in js
    assert "account.open = false" in js
    assert "nav.open = false" in js
    assert "event.key === 'Escape'" in js
    assert "trigger?.focus()" in js
    assert "@media(max-width:540px)" in css
    assert "@media(max-width:1180px)" in css
    assert "prefers-reduced-motion:reduce" in css
    assert "unified-menu-dropdown:not([open])" in css


def test_public_routes_render_shared_navigation():
    # Other route tests may reset the SQLite schema; make this independent
    # of test execution order and lifespan configuration.
    Base.metadata.create_all(engine)
    with TestClient(app) as client:
        for path in ("/", "/core-partnerships", "/login"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.text.count('id="site-header"') == 1
            assert response.text.count('id="sky-nav-dropdown"') == 1
            assert response.text.count('id="delta-language-select"') == 1
            assert "Navigation Hub" in response.text
            assert 'href="/core-partnerships"' in response.text
            assert 'href="/signup"' in response.text
