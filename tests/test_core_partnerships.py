import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SESSION_SECRET", "test-secret-at-least-thirty-two-characters")
os.environ.setdefault("COOKIE_SECURE", "false")

from fastapi.testclient import TestClient
from website.app.main import app


def test_core_partnerships_is_a_public_page():
    with TestClient(app) as client:
        response = client.get("/partnerships")
    assert response.status_code == 200
    assert "Airline Partnerships" in response.text
    assert "Virgin Atlantic" in response.text
    assert "September 29, 2026" in response.text
    assert 'href="https://discord.gg/RbuYrETXAJ"' in response.text
    assert 'rel="canonical" href="https://roblox-delta-web.vercel.app/partnerships"' in response.text
    assert 'content="index, follow, max-image-preview:large"' in response.text
    assert "Not a real-world airline partnership" in response.text
    assert 'class="partner-hero"' in response.text

def test_partner_benefits_are_complete_and_mobile_styled():
    template = Path("website/templates/core_partnerships.html").read_text()
    for benefit in (
        "Priority Check-In", "Security Screening", "Priority Boarding", "Lounge Access",
        "First Class", "Delta Comfort", "Delta One", "Gold", "Platinum", "Diamond",
        "SkyMiles", "Upper Class", "SkyClub",
    ):
        assert benefit in template
    assert "https://discord.gg/RbuYrETXAJ" in template
    assert 'href="#benefits"' in template
    css = Path("website/static/partnership-editorial.css").read_text()
    assert "@media(max-width:760px)" in css
    assert "@media(max-width:500px)" in css
    assert "@media(prefers-reduced-motion:reduce)" in css
    assert ".partner-benefit-grid" in css

def test_partner_link_in_site_navigation_and_homepage():
    base = Path("website/templates/community_base.html").read_text()
    shared = Path("website/templates/_unified_site_header.html").read_text()
    home = Path("website/templates/homepage.html").read_text()
    assert '{% include "_unified_site_header.html" %}' in base
    assert 'href="/partnerships"' in shared
    assert 'href="/partnerships"' in home
    assert "/static/partnerships/delta-virgin-tails.jpg" in home
    assert 'class="air-partner-showcase"' in home

def test_premium_navigation_has_live_signup_and_mobile_access():
    public = Path("website/templates/community_base.html").read_text()
    member = Path("website/templates/base.html").read_text()
    shared = Path("website/templates/_unified_site_header.html").read_text()
    css = Path("website/static/unified-delta-navigation.css").read_text()
    js = Path("website/static/unified-delta-navigation.js").read_text()
    assert '{% include "_unified_site_header.html" %}' in public
    assert '{% include "_unified_site_header.html" %}' in member
    assert 'class="premium-announcement"' in shared
    assert 'class="premium-signup-message" href="/signup"' in shared
    assert 'class="premium-get-started" href="/signup"' in shared
    assert 'class="sky-nav-dropdown unified-menu-dropdown"' in shared
    assert 'class="sky-nav-panel"' in shared
    assert 'class="premium-nav-shell"' in shared
    assert 'href="/partnerships"' in shared
    assert '@media(max-width:540px)' in css
    assert '@media(prefers-reduced-motion:reduce)' in css
    assert "Escape" in js

def test_welcome_sound_replays_when_page_is_revisited():
    js = Path("website/static/signin-success.js").read_text()
    html = Path("website/templates/signin_success.html").read_text()
    assert "window.addEventListener('pageshow'" in js
    assert 'sound.currentTime = 0' in js
    assert 'sound.play()' in js
    assert "handleGesture" in js
    assert 'play-welcome-sound' not in html
    assert 'delta-signin.mp3' in html


def test_partnership_uses_accessible_editorial_layout_instead_of_cinematic_effects():
    template = Path("website/templates/core_partnerships.html").read_text()
    css = Path("website/static/partnership-editorial.css").read_text()
    home = Path("website/templates/homepage.html").read_text()
    base = Path("website/templates/community_base.html").read_text()

    assert "/static/partnership-editorial.css" in template
    assert "/static/partnership-cinematic.js" not in template
    assert "/static/partnership-cinematic.css" not in template
    assert 'class="core-hero-route"' not in template
    assert 'class="core-scroll-meter"' not in template
    assert 'aria-labelledby="partner-page-title"' in template
    assert 'class="partner-breadcrumb' in template
    assert '/static/partnerships/delta-virgin-tails.jpg' in template
    assert 'id="partner-benefits-title"' in template
    assert 'class="partner-disclaimer partner-wrap"' in template
    assert 'delta-partner-page' in base
    assert 'class="air-partner-showcase"' in home
    assert 'grid-template-columns:repeat(4,minmax(0,1fr))' in css
    assert "prefers-reduced-motion:reduce" in css

