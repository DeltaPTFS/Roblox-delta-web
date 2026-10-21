"""Regression tests for cinematic landing, shared onboarding, flight board and staff links."""
from pathlib import Path

from fastapi.testclient import TestClient

from website.app.main import app


def source(name):
    return Path("website", name).read_text()


def test_join_now_reuses_existing_polished_signin_layout():
    with TestClient(app) as client:
        redirect = client.get("/signup", follow_redirects=False)
        assert redirect.status_code == 303
        assert redirect.headers["location"] == "/login?mode=signup&intent=community&next=%2Fwelcome"
        page = client.get(redirect.headers["location"])
        assert page.status_code == 200
        assert "delta-auth-v3" in page.text
        assert "Join Delta Roblox." in page.text
        assert "Continue with Discord" in page.text
        assert 'href="/join"' in page.text
        assert "No SkyMiles membership or Forms application required" in page.text


def test_home_motion_does_not_hide_content_without_javascript_or_reduced_motion():
    homepage = source("templates/homepage.html")
    css = source("static/homepage-cinematic.css")
    js = source("static/homepage-cinematic.js")
    assert "home-cinematic-hero" in homepage
    assert "home-flight-trails" in homepage
    assert "home-flight-ticker" in homepage
    assert "homepage-cinematic.css" in homepage
    assert "homepage-cinematic.js" in homepage
    assert "IntersectionObserver" in js
    assert "home-visible" in js
    assert "@media(prefers-reduced-motion:reduce)" in css
    assert "body.home-cinematic-ready .home-reveal" in css
    assert "animation:home-flight-path" in css
    assert 'href="/signup">Get Started</a>' in homepage


def test_flights_link_is_a_real_schedule_with_genuine_empty_state():
    main = source("app/main.py")
    flights = source("templates/flights.html")
    assert '@app.get("/flights", response_class=HTMLResponse)' in main
    assert 'Flight.status.in_([FlightStatus.SCHEDULED, FlightStatus.DELAYED])' in main
    assert 'Flight.starts_at >= terminal_cutoff' in main
    assert 'select(Flight)' in main
    assert 'discord_member' in main
    assert 'can_book=bool(user)' in main
    assert "No flights scheduled right now." in flights
    assert "CURRENT" not in flights.upper() or "Current flights" in flights
    assert "{% for flight in flights %}" in flights
    assert "data-local-time" in flights
    assert "data-live-clock" in flights
    assert 'class="flight-terminal-book open-booking"' in flights
    assert "Activate SkyMiles to book" in flights
    assert "flight-terminal.css" in source("templates/base.html")


def test_homepage_reveals_on_scroll_and_replays_on_return():
    homepage = source("templates/homepage.html")
    js = source("static/homepage-cinematic.js")
    css = source("static/homepage-cinematic.css")
    community_motion = source("static/community-motion.js")
    assert 'class="home-scroll-meter"' in homepage
    assert "IntersectionObserver" in js
    assert "window.addEventListener('scroll', requestDraw, { passive: true })" in js
    assert "node.classList.remove('home-visible')" in js
    assert "node.classList.add('home-visible')" in js
    assert "node.getBoundingClientRect()" in js
    assert "home-visible" in css
    assert ".home-scroll-meter-fill" in css
    assert "--home-parallax" in js and "--home-parallax" in css
    assert "if (document.querySelector('.home-cinematic-hero, .core-page')) return;" in community_motion
    assert "prefers-reduced-motion:reduce" in css
    assert "observer.unobserve(entry.target)" not in js


def test_homepage_animated_scenes_activate_during_scrolling():
    homepage = source("templates/homepage.html")
    css = source("static/homepage-cinematic.css")
    script = source("static/homepage-cinematic.js")
    assert "home-cinematic-hero" in homepage
    assert "home-scene-active" in script
    assert "new IntersectionObserver" in script
    assert ".discover, .showcase, .cabin-experience, .core-home-spotlight, .future, .small-cta" in script
    assert "homePartnerLevitate" in css
    assert "homeGallerySweep" in css
    assert "homeRunwayLight" in css
    assert "prefers-reduced-motion:reduce" in css
    assert "url('/static/ads/" not in css


def test_discord_login_preserves_flights_destination():
    source_main = source("app/main.py")
    assert 'request.session["community_login_return"] = next if next in ("/welcome", "/flights") else "/welcome"' in source_main
    assert 'community_return = request.session.pop("community_login_return", "/welcome")' in source_main
    assert 'destination=community_return, kind="community"' in source_main
    login_markup = source("templates/login.html")
    assert "community_join_unconfirmed" in login_markup
    assert "couldn't confirm your community membership" in login_markup


def test_staff_permissions_and_panels_remain_intact():
    base = source("templates/community_base.html")
    private = source("templates/base.html")
    header = source("templates/_unified_site_header.html")
    main = source("app/main.py")
    panel = source("templates/admin.html")
    assert '{% include "_unified_site_header.html" %}' in base
    assert '{% include "_unified_site_header.html" %}' in private
    assert 'set nav_level = auth if auth is defined' in header
    assert "'/owner' if nav_level == 'OWNER'" in header
    assert "'/admin' if nav_level == 'ADMIN'" in header
    assert "'/staff'" in header
    assert "require_staff" in main and "require_owner" in main
    assert '@app.get("/staff",response_class=HTMLResponse)' in main
    assert '@app.get("/admin",response_class=HTMLResponse)' in main
    assert '@app.get("/owner",response_class=HTMLResponse)' in main
    assert "render_staff_panel(request,q,db" in main
    assert "Panel</div>" not in panel.split("{% block content %}")[0]

def test_page_backgrounds_use_community_gallery_not_advertisements():
    home = source("templates/homepage.html")
    core_css = source("static/core-partnerships.css")
    flights_css = source("static/flight-terminal.css")
    old_signup_css = source("static/premium-header.css")
    public_base = source("templates/community_base.html")

    # Campaigns remain confined to the featured advertising showcase.
    assert 'class="delta-advertising"' in home
    assert 'src="/static/ads/delta-lax.webp"' in home

    # Hero / page backgrounds are always from our Delta Roblox gallery.
    assert "url('/static/gallery/delta-terminal.webp')" in core_css
    assert "url('/static/gallery/delta-centennial.webp')" in flights_css
    assert "url('/static/gallery/delta-hq.webp')" in old_signup_css
    for style in (core_css, flights_css, old_signup_css):
        assert "url('/static/ads/" not in style

    # Sharing the homepage or partner page must not use campaign art either.
    assert "/static/gallery/delta-centennial.webp" in public_base
    assert "/static/ads/delta-centennial-ad.webp" not in public_base
