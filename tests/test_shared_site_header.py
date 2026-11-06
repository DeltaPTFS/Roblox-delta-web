"""Keep a single consistent shared header on Home, member, and staff pages."""
from pathlib import Path

def read(path):
    return Path(path).read_text(encoding="utf-8")

def test_all_pages_get_one_navigation_bar():
    head = read("website/templates/_unified_site_header.html")
    home = read("website/templates/homepage.html")
    public = read("website/templates/community_base.html")
    account = read("website/templates/base.html")
    assert head.count('class="standard-nav-row"') == 1
    assert head.count('class="community-primary-nav standard-nav-inner"') == 1
    assert 'class="partner-nav-row"' not in head
    assert 'class="premium-announcement"' not in head
    assert '{% include "_site_announcement.html" %}' in head
    assert 'class="air-book-tabs air-site-links"' not in home
    assert 'class="air-book-panel air-book-panel-default"' in home
    for layout in (public, account):
        assert '{% include "_unified_site_header.html" %}' in layout
    for page in ('/home','/flights','/forms','/news','/partnerships','/skymiles'):
        assert f'href="{page}"' in head

def test_owner_and_account_keep_header_separation():
    head = read("website/templates/_unified_site_header.html")
    css = read("website/static/header-layout.css")
    assert head.index('class="premium-header-actions"') < head.index('class="standard-nav-row"')
    assert 'class="site-theme-toggle"' in head
    assert 'class="community-account-slot"' in head
    assert 'class="sky-nav-dropdown unified-menu-dropdown"' in head
    assert "request.url.path in ['/owner','/admin','/staff']" in head
    assert 'aria-current="page"' in head
    assert ".standard-nav-row .community-primary-nav.standard-nav-inner" in css
    assert "max-width:850px" in css
    assert "max-width:500px" in css
