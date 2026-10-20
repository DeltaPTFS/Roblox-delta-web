import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SESSION_SECRET", "test-secret-at-least-thirty-two-characters")
os.environ.setdefault("COOKIE_SECURE", "false")

from fastapi.testclient import TestClient
from website.app.main import app


def test_core_partnerships_is_a_public_page():
    with TestClient(app) as client:
        response = client.get("/core-partnerships")
    assert response.status_code == 200
    assert "Two airlines." in response.text
    assert "Virgin Atlantic" in response.text
    assert "September 29, 2026" in response.text
    assert 'href="https://discord.gg/RbuYrETXAJ"' in response.text
    assert 'rel="canonical" href="https://roblox-delta-web.vercel.app/core-partnerships"' in response.text
    assert 'content="index, follow, max-image-preview:large"' in response.text
    assert "Not an official announcement by" in response.text


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
    css = Path("website/static/core-partnerships.css").read_text()
    assert "@media(max-width:700px)" in css
    assert "@media(prefers-reduced-motion:reduce)" in css


def test_partner_link_in_site_navigation_and_homepage():
    base = Path("website/templates/community_base.html").read_text()
    shared = Path("website/templates/_unified_site_header.html").read_text()
    home = Path("website/templates/homepage.html").read_text()
    assert '{% include "_unified_site_header.html" %}' in base
    assert 'href="/core-partnerships"' in shared
    assert 'href="/core-partnerships"' in home
    assert "/static/partnerships/virgin-flag.svg" in home

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
    assert 'href="/core-partnerships"' in shared
    assert '@media(max-width:540px)' in css
    assert '@media(prefers-reduced-motion:reduce)' in css
    assert "Escape" in js

def test_welcome_sound_replays_when_page_is_revisited():
    js = Path("website/static/signin-success.js").read_text()
    html = Path("website/templates/signin_success.html").read_text()
    assert 'addEventListener(\'pageshow\', startWelcomeSound)' in js
    assert 'audio.currentTime = 0' in js
    assert 'audio.play()' in js
    assert 'resumeOnGesture' in js
    assert 'delta-signin.mp3' in html


def test_partnership_has_its_own_scroll_cinematic_director():
    template = Path("website/templates/core_partnerships.html").read_text()
    script = Path("website/static/partnership-cinematic.js").read_text()
    css = Path("website/static/partnership-cinematic.css").read_text()
    generic = Path("website/static/community-motion.js").read_text()

    assert "/static/partnership-cinematic.js" in template
    assert "/static/partnership-cinematic.css" in template
    assert 'class="core-hero-route"' in template
    assert 'class="core-scroll-meter"' in template
    assert 'data-core-progress' not in template or 'core-scroll-meter-fill' in template
    assert "IntersectionObserver" in script
    assert "window.addEventListener('scroll', schedule, { passive: true })" in script
    assert "node.classList.add('core-visible')" in script
    assert "node.classList.remove('core-visible')" in script
    assert ".core-benefit" in script and ".core-eligibility" in script
    assert ".core-sky-visual-overlay > *" in script
    assert "core-motion-ready" in css
    assert "coreBrandFloat" in css
    assert "coreFlightStreak" in css
    assert "coreTierArrive" in css
    assert "url('/static/gallery/delta-lounge.webp')" in css
    assert "url('/static/ads/" not in css
    assert "prefers-reduced-motion:reduce" in css
    assert "if (document.querySelector('.home-cinematic-hero, .core-page')) return;" in generic
