"""Friendly paths and lighter, uncropped Delta Roblox homepage regression tests."""
from pathlib import Path

from fastapi.testclient import TestClient

from website.app.main import app


def read(path):
    return Path("website", path).read_text()


def test_home_and_skymiles_are_real_get_routes():
    get_paths = {route.path for route in app.routes if "GET" in (getattr(route, "methods", set()) or set())}
    for path in (
        "/", "/home", "/dashboard", "/skymiles", "/flights", "/forms",
        "/partnerships", "/core-partnerships", "/miles", "/trips", "/activity",
        "/rewards", "/profile", "/settings", "/staff", "/admin", "/owner",
    ):
        assert path in get_paths


def test_new_home_alias_renders_same_public_page_as_root():
    with TestClient(app) as client:
        root = client.get("/")
        alias = client.get("/home")
    assert root.status_code == alias.status_code == 200
    assert 'id="cabin-experience"' in alias.text
    assert "Delta Air Lines Roblox" in alias.text
    assert 'href="/skymiles"' in alias.text
    assert 'href="/home"' in alias.text
    assert 'rel="canonical" href="https://roblox-delta-web.vercel.app/"' in alias.text


def test_skymiles_alias_keeps_login_required():
    with TestClient(app) as client:
        response = client.get("/skymiles", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?next=%2Fskymiles")


def test_all_homepage_links_use_friendly_paths():
    nav=read("templates/_unified_site_header.html")
    home=read("templates/homepage.html")
    account=read("templates/_account_panel.html")
    tour=read("static/skymiles-tour.js")
    assert nav.count('href="/home"') >= 2
    assert nav.count('href="/skymiles"') >= 2
    assert 'href="/skymiles"' in home
    assert 'href="/skymiles"' in account
    assert "path:'/skymiles'" in tour


def test_optimized_homepage_does_not_block_on_discord_or_replay_heavy_animations():
    main=read("app/main.py")
    start=main.index('async def homepage(')
    end=main.index('def safe_login_target(', start)
    homepage_handler=main[start:end]
    assert 'await crew_roles_for_display(' not in homepage_handler
    assert 'await main_roles_for_display(' not in homepage_handler
    assert 'crew_profile_roles' in homepage_handler
    animation=read("static/homepage-cinematic.js")
    css=read("static/homepage-cinematic.css")
    assert animation.count("new IntersectionObserver") == 1
    assert "window.addEventListener('scroll'" not in animation
    assert "observer.unobserve(entry.target)" in animation
    assert "content-visibility:auto" in css
    assert "object-fit:contain" in css
    assert ".cabin-experience .cabin-card-copy" in css
    assert "content-visibility:visible !important" in css
    assert "backdrop-filter:none !important" in css
    assert "'.cabin-experience .cabin-card'" not in animation
    assert ".cabin-experience .cabin-card::after" in css


def test_partnerships_has_clean_url_and_legacy_compatibility():
    with TestClient(app) as client:
        clean = client.get("/partnerships")
        legacy = client.get("/core-partnerships")
    assert clean.status_code == legacy.status_code == 200
    assert "Two airlines." in clean.text
    assert "Virgin Atlantic" in legacy.text
    assert 'href="/partnerships"' in clean.text
    assert 'rel="canonical" href="https://roblox-delta-web.vercel.app/partnerships"' in clean.text


def test_site_navigation_exposes_all_public_sections_as_clean_paths():
    header = read("templates/_unified_site_header.html")
    for slug in ("/home", "/flights", "/forms", "/partnerships", "/skymiles"):
        assert header.count('href="' + slug + '"') >= 2
    assert 'href="/core-partnerships"' not in header
    home = read("templates/homepage.html")
    assert 'href="/partnerships"' in home
    assert 'href="/skymiles"' in home
