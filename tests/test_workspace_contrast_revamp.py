"""Regression coverage for workspace navigation and contrast repairs."""
from pathlib import Path
from jinja2 import Environment
from fastapi.testclient import TestClient
from website.app.main import app

ROOT = Path("website")

def read(path):
    return (ROOT / path).read_text(encoding="utf-8")

def test_staff_panels_keep_every_permissioned_action_but_reduce_clutter():
    html = read("templates/admin.html")
    assert 'data-ops-workspace' in html
    assert 'data-ops-group="overview"' in html
    assert 'data-ops-group="members"' in html
    assert 'data-ops-group="announcements"' in html
    assert 'data-ops-group="flights"' in html
    assert 'data-ops-group="system"' in html
    assert 'href="#member-actions"' in html
    assert 'href="#flight-operations"' in html
    assert 'href="#site-announcement-editor"' in html
    assert 'href="#system-integrations"' in html
    assert 'action="/admin/members/{{ member.id }}/miles"' in html
    assert 'action="/admin/flights/create"' in html
    assert 'action="/admin/flights/sync"' in html
    assert "ops-workspace.js" in html
    assert html.rsplit('{% endblock %}', 1)[0].rstrip().endswith(
        '<script src="/static/operations-workspace.js?v=20261106" defer></script>'
    )

def test_existing_admin_template_compiles_with_jinja_and_all_nav_roles():
    html = read("templates/admin.html")
    Environment().parse(html)
    assert "if panel_level == 'OWNER'" in html
    assert "if panel_level in ('OWNER', 'ADMIN')" in html
    assert "if panel_level == 'OWNER'" in html
    script = read("static/operations-workspace.js")
    assert "groupForHash" in script
    assert "data-ops-workspace" in script
    assert "hashchange" in script
    assert "aria-current" in script
    assert "ops-member-detail" in script
    assert "No-JavaScript" not in script  # User-facing UI has no irrelevant technical wording.

def test_contrast_styles_are_loaded_last_and_consistent_in_light_dark():
    for layout in ("templates/base.html", "templates/community_base.html"):
        html = read(layout)
        assert "site-contrast-repairs.css" in html
        assert html.index("site-appearance.css") < html.index("site-contrast-repairs.css")
    base = read("templates/base.html")
    assert "operations-workspace.css" in base
    assert base.index("site-contrast-repairs.css") < base.index("operations-workspace.css")
    for stylesheet in ("static/operations-workspace.css", "static/site-contrast-repairs.css"):
        css = read(stylesheet)
        assert 'html[data-site-theme="dark"]' in css
        assert "prefers-reduced-motion" in css
    script = read("static/operations-workspace.js")
    assert "details" in script
    assert "params.has('q')" in script or "get('q')" in script

def test_partner_looking_ahead_is_accessible_and_informative():
    html = read("templates/core_partnerships.html")
    assert 'class="partner-future-grid partner-next-grid"' in html
    assert html.count('class="partner-next-card"') == 3
    assert 'href="/flights"' in html
    assert 'href="/news"' in html
    assert 'href="#benefits"' in html
    assert "A shared journey, with more ahead." not in html
    css = read("static/site-contrast-repairs.css")
    assert ".partner-next-card" in css
    assert "color:#f2f7ff!important" in css
    assert "color:#172c46!important" in css
    with TestClient(app) as client:
        response = client.get("/partnerships")
        assert response.status_code == 200
        assert "There's more to discover together." in response.text
        assert "Stay connected" in response.text
