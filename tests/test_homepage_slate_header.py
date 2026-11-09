"""Delta-inspired header and login actions remain functional and uncluttered."""
from pathlib import Path

ROOT = Path("website")

def source(path):
    return (ROOT / path).read_text(encoding="utf-8")

def test_guest_header_has_explicit_signup_and_login_links():
    head = source("templates/_unified_site_header.html")
    assert 'class="delta-home-auth"' in head
    assert 'class="delta-home-signup" href="/signup"' in head
    assert 'class="delta-home-login" href="/login"' in head
    assert 'if header_viewer' in head
    assert 'if request.url.path in [\' /\', \'/home\']' not in head
    assert "request.url.path in ['/', '/home']" in head
    assert 'class="delta-home-notifications" href="/news"' in head
    assert 'class="delta-home-flight-search" href="/flights"' in head
    assert 'Community announcements' in head
    assert 'Search available flights' in head

def test_mobile_header_uses_real_menu_and_hides_duplicate_nav():
    css = source("static/homepage-slate-header.css")
    head = source("templates/_unified_site_header.html")
    base = source("templates/community_base.html")
    assert 'class="sky-nav-dropdown unified-menu-dropdown"' in head
    assert 'class="standard-nav-row"' in head
    assert "@media(max-width:700px)" in css
    assert ".standard-nav-row{display:none!important}" in css
    assert ".sky-nav" in css
    assert ".delta-home-auth" in css
    assert ".delta-home-login" in css
    assert "background:#c8102e!important" in css
    assert 'href="/static/homepage-slate-header.css?v={{ asset_version }}-slate-20261108"' in base
    assert base.index('header-layout.css') < base.index('homepage-slate-header.css')

def test_slate_copy_and_accessible_footer_mode_switch():
    css = source("static/homepage-slate-header.css")
    footer = source("templates/_homepage_airline_footer.html")
    assert "#334155" in css and "#475569" in css and "#64748b" in css
    assert "text-shadow:none!important" in css
    assert ".delta-footer-appearance" in css
    assert 'data-site-theme-toggle' in footer
    assert 'data-site-theme-label' in footer
    assert "data-home-footer-language" in footer
    assert "Not affiliated with" in footer
