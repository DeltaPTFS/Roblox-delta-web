"""Regression coverage for the new shared account hub and Delta control center."""
from pathlib import Path

from website.app.main import CREW_DISPLAY_NAMES, main_role_labels


def read(path):
    return Path("website", path).read_text()


def test_confirmation_no_longer_redirects_and_has_no_sound_button():
    html=read("templates/signin_success.html")
    js=read("static/signin-success.js")
    main=read("app/main.py")
    assert 'href="/signin/finish"' in html
    assert "Return to Homepage" in html
    assert "success-check-svg" in html
    assert "sound-button" not in html
    assert "progress-seconds" not in html
    assert "audio.play()" in js
    assert "window.location.replace" not in js
    assert "setTimeout(activate, 3900)" in js
    assert 'request.session.get("signin_celebration")' in main
    assert '@app.get("/signin/finish")' in main


def test_homepage_membership_changes_join_to_go_to_discord():
    html=read("templates/homepage.html")
    base=read("templates/community_base.html")
    header=read("templates/_unified_site_header.html")
    main=read("app/main.py")
    assert '"Go to Discord" if main_discord_member' in html
    assert "main_discord_member=member_main" in main
    assert "discord_href=" in main
    assert "Go to Discord" in header
    assert "'/join'" in header
    assert '{% include "_unified_site_header.html" %}' in base
    assert '<a class="community-account" href="/forms">' not in header

def test_account_panel_shared_and_expanded_with_real_crew_roles():
    partial=read("templates/_account_panel.html")
    base=read("templates/base.html")
    homepage_base=read("templates/community_base.html")
    header=read("templates/_unified_site_header.html")
    styles=read("static/account-hub.css")
    assert '{% include "_unified_site_header.html" %}' in base
    assert '{% include "_unified_site_header.html" %}' in homepage_base
    assert '{% include "_account_panel.html" %}' in header
    assert 'class="delta-account-menu account-menu"' in partial
    assert 'class="delta-account-caret"' in partial
    assert "Delta Crew" in partial
    assert "panel_crew" in partial
    assert "crew_roles_status" in partial
    assert "SkyMiles Dashboard" in partial
    assert "Staff Workspace" in partial
    assert 'width:min(440px,calc(100vw - 28px))' in styles

def test_crew_role_labels_match_supplied_roles():
    assert CREW_DISPLAY_NAMES["1554665018690248714"]=="Board of Directors"
    assert CREW_DISPLAY_NAMES["1554666461644197988"]=="Leadership"
    assert CREW_DISPLAY_NAMES["1554666482988875788"]=="Human Resources"
    assert CREW_DISPLAY_NAMES["1554669633573888010"]=="Delta Crew"
    assert CREW_DISPLAY_NAMES["1554671178893885480"]=="Awaiting Verification"
    assert main_role_labels(["1539005297417519205"])==[
        {"name":"Founders","id":"1539005297417519205","color":0}]


def test_crew_membership_uses_dedicated_crew_bot_and_is_display_only():
    source=read("app/main.py")
    assert "settings.discord_crew_bot_token" in source
    assert "settings.discord_crew_guild_id" in source
    assert 'member_main=bool(' in source
    assert "cache" in source
    assert "CREW_DISPLAY_NAMES" in source
    assert "Decorative role labels only" in source


def test_skymiles_and_admin_new_interface_exists_without_removing_core_actions():
    dashboard=read("templates/dashboard.html")
    admin=read("templates/admin.html")
    css=read("static/delta-dashboard-v2.css")
    admin_css=read("static/delta-admin-v2.css")
    for label in ("Welcome aboard", "AVAILABLE MILES", "MEDALLION QUALIFYING POINTS",
                  "VERIFIED COMMUNITY MEMBER", "Latest SkyMiles activity", "Book a Flight"):
        assert label in dashboard
    assert "delta-dash-hero" in dashboard
    assert "dashboard-v2-grid" in dashboard
    assert "delta-dashboard-v2" in css
    for section in ("delta-admin-hero", "delta-admin-overview",
                    "delta-admin-sections", "member-actions", "create-flight",
                    "flight-operations", "system-integrations", "audit-trail"):
        assert section in admin
    for action in ('action="/admin/members/{{ member.id }}/miles"',
                   'action="/admin/flights/create"', 'action="/admin/flights/sync"'):
        assert action in admin
    assert "grid-template-columns:repeat(4,minmax(0,1fr))" in admin_css


def test_server_errors_offer_homepage_not_login():
    html=read("templates/error.html")
    assert "Return to Homepage" in html
    assert 'href="/"' in html
    assert "Return to Login" not in html
