"""Regressions for white-first site appearance and connected Discord identity."""
from pathlib import Path

ROOT = Path("website")

def source(path):
    return (ROOT / path).read_text(encoding="utf-8")

def test_theme_controls_exist_in_both_layouts():
    header = source("templates/_unified_site_header.html")
    public = source("templates/community_base.html")
    member = source("templates/base.html")
    newsroom = source("templates/news.html")
    success = source("templates/signin_success.html")
    for layout in (public, member, success):
        assert "site-theme-init.js" in layout
        assert "site-theme.js" in layout
        assert "site-appearance.css" in layout
    assert '{% extends "community_base.html" %}' in newsroom
    assert 'news-editorial.css' in newsroom
    assert 'news-longform.css' in newsroom
    assert 'data-site-theme-toggle' in header
    assert 'aria-pressed="false"' in header
    assert 'data-site-theme-toggle' in newsroom

def test_appearance_is_white_by_default_and_blue_is_optional():
    init = source("static/site-theme-init.js")
    toggle = source("static/site-theme.js")
    css = source("static/site-appearance.css")
    assert "delta-site-appearance" in init
    assert "delta-site-appearance" in toggle
    assert "themeChoice" in init
    assert "root.dataset.siteTheme" in toggle
    assert "site-theme-toggle" in toggle
    assert 'html[data-site-theme="light"] body{background:#fff!important' in css
    assert 'html[data-site-theme="dark"] body{' in css
    assert "background:#0c1930!important" in css
    assert "community-footer" in css

def test_account_photo_updates_and_missing_avatar_uses_initials():
    template = source("templates/_account_panel.html")
    script = source("static/account-hub.js")
    css = source("static/site-appearance.css")
    assert "panel_initials" in template
    assert "panel_has_photo" in template
    assert template.count("data-account-avatar-frame") == 2
    assert "data-account-avatar-image" in template
    assert "sourceSummary" in script
    assert "oldFrame.replaceWith(replacement)" in script
    assert "oldLabel.replaceWith(label.cloneNode(true))" in script
    assert "img.complete && img.naturalWidth > 0" in script
    assert "img.remove()" in script
    assert ".delta-avatar-initials" in css
    assert ".delta-avatar-frame.has-photo" in css

def test_font_sizes_are_larger_on_public_dashboard_and_news_pages():
    css = source("static/site-appearance.css")
    assert "body{font-size:17px!important" in css
    assert ".air-home .air-book-field strong" in css
    assert ".partner-page .partner-benefit h3" in css
    assert ".delta-dashboard-v2 .delta-dash-hero" in css
    assert ".delta-admin-v2 .card.page-card" in css
    assert "body .news-site-header nav a{font-size:14px!important}" in css
    assert "@media(max-width:620px)" in css
