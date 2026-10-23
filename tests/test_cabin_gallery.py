"""Tests for accessible, fast cabin slides and the separate /experience page."""
from pathlib import Path
from hashlib import sha256

from fastapi.testclient import TestClient

from website.app.main import app

ROOT = Path("website")
CABIN_PHOTOS = {
    "cabin-entertainment-original.png": "f36da8ee0753c3c0511caca566f14129ec7d96fac06e8d5b20132c14537686cf",
    "cabin-service-original.jpg": "aae8630dce444b9677fef580c53f9d3dbcee713999f756539c3b35a7ae8f55e1",
    "cabin-blue-original.png": "2c1e928d8d2b92f6fbef18865b614d512aa12eaa0addcda5784fc8d3597effa5",
    "cabin-window-original.jpg": "a95b8ba4b177d98ea67e37fe34d3a9d7fb6f07b40cb694afe98367feea9f2f68",
}


def read(name):
    return (ROOT / name).read_text()


def test_served_cabin_photos_are_identical_to_the_original_uploads():
    # Guard against the 900px recompression that blurred the previous copies.
    with TestClient(app) as client:
        for name, digest in CABIN_PHOTOS.items():
            response = client.get("/static/gallery/" + name)
            assert response.status_code == 200
            assert sha256(response.content).hexdigest() == digest, name
            assert response.headers["content-type"] == (
                "image/png" if name.endswith(".png") else "image/jpeg"
            )


def test_homepage_gallery_is_one_native_swipe_carousel_not_a_tall_photo_wall():
    html = read("templates/homepage.html")
    css = read("static/cabin-experience.css")
    js = read("static/cabin-carousel.js")

    assert 'id="cabin-experience"' in html
    assert html.count('class="cabin-carousel-slide"') == 4
    assert 'class="cabin-mosaic"' not in html
    assert 'class="cabin-card ' not in html
    assert 'aria-roledescription="carousel"' in html
    assert 'href="/experience"' in html
    assert 'data-cabin-prev' in html and 'data-cabin-next' in html
    assert html.count("data-cabin-dot=") == 4
    assert html.count('loading="lazy"') >= 4
    for photo in CABIN_PHOTOS:
        assert html.count('src="/static/gallery/' + photo + '"') == 1

    assert "scroll-snap-type:x mandatory" in css
    assert "scroll-snap-align:start" in css
    assert "flex:0 0 100%" in css
    assert "object-fit:contain" in css
    assert ".cabin-carousel-slide img" in css
    assert "max-height:490px" in css

    # Manual controls only: no autoplay interval, timers or RAF scroll handlers.
    assert "setInterval(" not in js
    assert "setTimeout(" not in js
    assert "requestAnimationFrame(" not in js
    assert "IntersectionObserver" in js
    assert "window.addEventListener('scroll'" not in js
    assert "track.scrollTo" in js


def test_standalone_experience_gallery_has_full_images_and_public_route():
    html = read("templates/cabin_experience.html")
    css = read("static/cabin-experience.css")
    main = read("app/main.py")
    assert '@app.get("/experience", response_class=HTMLResponse)' in main
    assert 'class="experience-gallery-grid"' in html
    assert html.count('class="experience-gallery-card"') == 4
    assert 'href="/home#cabin-experience"' in html
    assert 'href="/flights"' in html
    assert "Independent Roblox aviation roleplay community" in html
    assert "max-height" not in css.split(".experience-gallery-card img",1)[1].split("}",1)[0]
    for photo in CABIN_PHOTOS:
        assert html.count('src="/static/gallery/' + photo + '"') == 1
        assert html.count('href="/static/gallery/' + photo + '"') == 1
    assert html.count('class="experience-original-link"') == 4
    assert 'object-fit:contain' in css
    assert 'grid-template-columns:1fr' in css


def test_gallery_text_contrast_and_navigation_sparkles_remain():
    home_css = read("static/homepage-cinematic.css")
    cabin_css = read("static/cabin-experience.css")
    header = read("templates/_unified_site_header.html")
    nav = read("static/unified-delta-navigation.css")
    assert ".showcase .gallery-card::before" in home_css
    assert "background:rgba(5,14,33,.82)" in home_css
    assert "background:#112544" in cabin_css
    assert "color:#fff" in cabin_css
    assert 'class="delta-nav-sparkles" aria-hidden="true"' in header
    assert "navStarDrift" in nav and "navStarBlink" in nav
    assert "backdrop-filter:none !important" in cabin_css
    assert "prefers-reduced-motion:reduce" in cabin_css


def test_home_and_experience_render_without_broken_navigation():
    with TestClient(app) as client:
        home = client.get("/home")
        experience = client.get("/experience")
    assert home.status_code == experience.status_code == 200
    assert home.text.count('id="site-header"') == 1
    assert 'id="cabin-experience"' in home.text
    assert 'data-cabin-carousel' in home.text
    assert 'href="/experience"' in home.text
    assert "Welcome aboard." in experience.text.replace("<em>", "").replace("</em>", "")
    assert 'rel="canonical" href="https://roblox-delta-web.vercel.app/experience"' in experience.text
