"""Regression tests for final October SkyMiles/Ownership polish."""
from pathlib import Path

from fastapi.testclient import TestClient
from website.app.main import app


def src(path):
    return Path("website",path).read_text()


def test_announcement_uses_verified_discord_author_with_avatar():
    helper=src("app/site_announcements.py")
    banner=src("templates/_site_announcement.html")
    assert "author.discord_display_name" in helper
    assert "author.discord_username" in helper
    assert "author.discord_avatar_url" in helper
    assert "author.roblox_username" not in helper
    assert 'site_announcement.author_name' in banner
    assert 'site_announcement.author_avatar' in banner
    assert 'loading="lazy"' in banner


def test_automatic_signin_sound_has_no_replay_control():
    html=src("templates/signin_success.html")
    script=src("static/signin-success.js")
    assert 'id="signin-sound"' in html
    assert 'play-welcome-sound' not in html
    assert 'welcome-sound-hint' not in html
    assert 'sound.play()' in script
    assert "window.addEventListener('pageshow'" in script
    assert "document.addEventListener('pointerdown'" in script
    assert "document.addEventListener('keydown'" in script


def test_sparkles_and_dashboard_backdrop_are_lightweight():
    nav=src("static/unified-delta-navigation.css")
    hero=src("static/delta-dashboard-v2.css")
    assert "navPassingGlimmer" in nav
    assert "navStarlight" in nav
    assert "@media(prefers-reduced-motion:reduce)" in nav
    start=hero.index(".delta-dash-hero:before")
    assert "delta-tail.webp" not in hero[start:start+390]


def test_long_tour_uses_discord_grey_avatar_and_takes_members_through_every_page():
    partial=src("templates/_skymiles_tutorial.html")
    js=src("static/skymiles-tour.js")
    main=src("app/main.py")
    for page in ("/dashboard", "/flights", "/miles", "/trips", "/activity",
                 "/rewards", "/profile", "/settings"):
        assert "path:'"+page+"'" in js
    for name in ("Grey R.", "Cookie"):
        assert name in js
    assert "tutorial_grey_avatar" in partial
    assert 'discord_avatar_url' in main
    assert "sessionStorage.setItem" in js
    assert "window.location.assign" in js
    assert 'href="/tutorial/complete"' not in partial
    assert 'action="/tutorial/complete"' in partial


def test_staff_panels_limit_query_work_and_guide_staff():
    main=src("app/main.py")
    admin=src("templates/admin.html")
    assert ".limit(24).offset((directory_page-1)*24)" in main
    assert 'directory_total' in main
    assert "Booking.user_id.in_(ids)" in main
    assert "ModerationAction.user_id.in_(ids)" in main
    assert 'delta-admin-quickstart' in admin
    assert 'delta-admin-pagination' in admin


def test_bot_ledger_requires_live_admin_roles_and_audits_canonical_balances():
    endpoint=src("app/community.py")
    assert 'settings.admin_discord_role_ids' in endpoint
    assert 'settings.owner_discord_role_ids' in endpoint
    assert '/guilds/{settings.discord_guild_id}/members/{actor_id}' in endpoint
    assert 'BOT_SKYMILES_ADJUSTMENT' in endpoint
    assert "action not in" in endpoint and '"set"' in endpoint and '"history"' in endpoint
    assert "interaction_id" in endpoint and "duplicate" in endpoint


def test_bot_routes_never_accept_untrusted_public_balance_modifications():
    with TestClient(app) as client:
        response=client.post("/internal/skymiles/award",json={
            "user_id":"111111111111111111",
            "awarded_by_id":"222222222222222222",
            "miles":5000,"reason":"Unauthorized test",
            "interaction_id":"333333333333333333",
        })
        assert response.status_code == 401
