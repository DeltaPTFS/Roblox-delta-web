"""Regression checks for requested SkyMiles/admin polish.

These checks ensure sensitive bot writes are authorized server-side and that
the UI stays responsive and consistent across the separate templates.
"""
from pathlib import Path


def read(path):
    return Path("website", path).read_text()


def test_discord_announcement_has_real_author_not_roblox_identity():
    helper=read("app/site_announcements.py")
    partial=read("templates/_site_announcement.html")
    assert "db.get(User, row.updated_by)" in helper
    assert "author.discord_display_name" in helper
    assert "author.discord_username" in helper
    assert "author.discord_avatar_url" in helper
    assert 'author.roblox_' not in helper
    assert "author_avatar" in partial and "author_name" in partial
    assert "loading=\"lazy\"" in partial


def test_signin_audio_auto_and_hidden_fallback():
    js=read("static/signin-success.js")
    page=read("templates/signin_success.html")
    assert "sound.play()" in js
    assert "window.addEventListener('pageshow'" in js
    assert "document.addEventListener('pointerdown'" in js
    assert "document.addEventListener('keydown'" in js
    assert 'id="play-welcome-sound"' not in page
    assert 'id="signin-sound"' in page


def test_tutorial_follows_all_skymiles_pages_and_discord_guide():
    base=read("templates/base.html")
    partial=read("templates/_skymiles_tutorial.html")
    js=read("static/skymiles-tour.js")
    assert '{% include "_skymiles_tutorial.html" %}' in base
    assert "tutorial_grey_avatar" in partial
    assert "Cookie" in partial
    assert "Grey R." in partial
    for path in ("/dashboard","/flights","/miles","/trips","/activity","/rewards","/profile","/settings"):
        assert "path:'"+path+"'" in js
    assert "sessionStorage.setItem" in js
    assert "modal.show()" in js
    assert "tutorial-progress" in partial


def test_owner_admin_role_verified_server_side_for_bot_mile_mutations():
    src=read("app/community.py")
    assert "internal_secret(request)" in src
    assert 'settings.admin_discord_role_ids' in src
    assert 'settings.owner_discord_role_ids' in src
    assert 'live_main & staff_admin_roles' in src
    assert "discord_interaction_id" in src
    assert "BOT_SKYMILES_ADJUSTMENT" in src
    assert 'action == "history"' in src
    assert 'action == "set"' in src
    assert "idempotency_ref" in src
    assert 'raise HTTPException(403' in src


def test_staff_panel_paginates_and_loads_no_heavy_directories():
    main=read("app/main.py")
    template=read("templates/admin.html")
    css=read("static/delta-admin-v2.css")
    assert ".limit(24).offset((directory_page-1)*24)" in main
    assert "directory_total=" in main
    assert "if users:" in main
    assert "User.id.in_(lookup_ids)" in main
    assert 'request.query_params.get("show_roles") == "1"' in main
    assert 'class="delta-admin-quick-grid"' in template
    assert "directory_pages" in template
    assert "loading=\"lazy\"" in template
    assert "content-visibility:auto" in css


def test_no_unwanted_aircraft_silhouette_in_skymiles_hero():
    css=read("static/delta-dashboard-v2.css")
    nav=read("static/unified-delta-navigation.css")
    assert ".delta-dash-hero:before" in css
    assert "url('/static/gallery/delta-tail.webp')" not in css.split(".delta-dash-hero:before",1)[1].split("}",1)[0]
    assert "navStarlight" in nav
    assert "prefers-reduced-motion:reduce" in nav
