"""Staff workspace, navigation and dark/light contrast regression checks."""
from pathlib import Path

TEMPLATES = Path("website/templates")
STATIC = Path("website/static")


def source(path):
    return path.read_text(encoding="utf-8")


def test_staff_owner_admin_workspace_contains_focusable_sections_and_existing_forms():
    html = source(TEMPLATES / "admin.html")
    assert 'data-ops-workspace' in html
    assert 'class="delta-admin-sections ops-workspace-nav"' in html
    for group in ("overview", "members", "announcements"):
        assert f'data-ops-group="{group}"' in html
        assert f'data-ops-tab="{group}"' in html
    for group in ("flights", "system"):
        assert f'data-ops-group="{group}"' in html
        assert f'data-ops-tab="{group}"' in html
    assert 'id="site-announcement-editor"' in html
    assert 'id="member-actions"' in html
    assert 'id="member-directory"' in html
    assert 'id="flight-operations"' in html
    assert 'id="system-integrations"' in html
    # Underlying POST routes remain unchanged, preserving authorization.
    assert 'action="/admin/members/{{ member.id }}/miles"' in html
    assert 'action="/admin/flights/create"' in html
    assert 'action="/admin/flights/sync"' in html
    assert "panel_level == 'OWNER'" in html
    assert "panel_level in ('OWNER', 'ADMIN')" in html or "panel_level in ('OWNER','ADMIN')" in html
    # Without JavaScript the sections are all present and readable.
    assert ' hidden ' not in html


def test_ops_workspace_script_preserves_hash_and_search_and_progressive_disclosure():
    js = source(STATIC / "operations-workspace.js")
    for expected in (
        "location.hash", "query", "directory_page",
        "openNestedDetails", "data-ops-tab",
        "data-ops-group", "history.pushState",
        "ops-member-detail", "ops-hidden-tools", "aria-current",
    ):
        assert expected in js
    assert "preventDefault" in js
    css = source(STATIC / "operations-workspace.css")
    assert "[data-ops-group][hidden]" in css
    assert 'html[data-site-theme="dark"] .ops-workspace' in css
    assert "--ops-paper:#fff;" in css
    assert ".ops-quick-grid" in css
    assert "@media(max-width:720px)" in css


def test_primary_navigation_separated_from_profile_controls_at_all_page_widths():
    head = source(TEMPLATES / "_unified_site_header.html")
    css = source(STATIC / "header-layout.css")
    authenticated = source(TEMPLATES / "base.html")
    public = source(TEMPLATES / "community_base.html")
    assert 'class="premium-nav-shell"' in head
    assert 'class="premium-header-actions"' in head
    assert 'class="standard-nav-row"' in head
    assert 'class="community-primary-nav standard-nav-inner"' in head
    assert 'class="partner-nav-row"' in head
    assert "request.url.path not in ['/', '/home', '/partnerships', '/core-partnerships']" in head
    assert 'class="site-theme-toggle"' in head
    assert "body.ops-panel-page .unified-delta-header .premium-announcement" in css
    assert "html[data-site-theme=\"light\"] .unified-delta-header" in css
    assert "html[data-site-theme=\"dark\"] .unified-delta-header" in css
    assert "max-width:1190px" in css
    assert "max-width:500px" in css
    for page in (authenticated, public):
        assert "/static/header-layout.css" in page
        assert "/static/site-contrast-repairs.css" in page


def test_partner_rework_has_distinct_three_cards_and_accessible_targets():
    html = source(TEMPLATES / "core_partnerships.html")
    css = source(STATIC / "site-contrast-repairs.css")
    assert html.count('class="partner-next-card"') == 3
    for anchor in ('href="/flights"', 'href="/news"', 'href="#benefits"'):
        assert anchor in html
    assert 'id="partner-future-title"' in html
    assert 'class="partner-next-grid partner-future-grid"' in html
    assert ".partner-next-card" in css
    assert 'html[data-site-theme="dark"] body.delta-partner-page' in css
    assert 'html[data-site-theme="light"] body.delta-partner-page' in css
    assert "grid-template-columns:1fr" in css
