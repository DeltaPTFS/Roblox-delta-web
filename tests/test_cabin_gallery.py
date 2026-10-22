"""Photo, animation and legibility regression checks for the Delta homepage."""
from pathlib import Path

from fastapi.testclient import TestClient
from website.app.main import app

ROOT=Path("website")
CABIN_PHOTOS=("cabin-entertainment","cabin-service","cabin-blue","cabin-window")


def read(name):
    return (ROOT/name).read_text()


def test_original_cabin_gallery_assets_are_local_and_compressed():
    html=read("templates/homepage.html")
    for name in CABIN_PHOTOS:
        path=ROOT/"static"/"gallery"/(name+".webp")
        assert path.exists(), f"Missing image: {path}"
        contents=path.read_bytes()
        assert len(contents)>3000, f"Missing or placeholder content for {name}"
        assert len(contents)<450000, f"Too large for responsive gallery: {name}"
        assert contents[:4]==b"RIFF" and contents[8:12]==b"WEBP"
        assert html.count('src="/static/gallery/'+name+'.webp"')==1
    assert '<section class="community-section cabin-experience"' in html
    assert 'id="cabin-experience"' in html
    assert "SCREENSHOTS FROM OUR DELTA ROBLOX AVIATION ROLEPLAY COMMUNITY" in html
    # Photos are part of the community experience, not misleading advertising.
    cabin=html.split('id="cabin-experience"',1)[1].split('</section>',1)[0]
    assert '/static/ads/' not in cabin
    assert cabin.count('loading="lazy"')==4
    assert cabin.count('decoding="async"')==4


def test_gallery_bright_caption_text_has_opaque_dark_surface_and_sheen_does_not_cover_it():
    css=read("static/homepage-cinematic.css")
    assert ".showcase .gallery-card::before" in css
    assert ".showcase .gallery-card::after{z-index:2}" in css
    assert ".showcase .gallery-card>div" in css
    assert "background:rgba(5,14,33,.82)" in css
    assert ".showcase .gallery-card>div>h3{color:#fff" in css
    assert ".cabin-card-copy" in css
    assert "background:rgba(5,12,28,.80)" in css


def test_nav_stars_automatically_drift_and_blink_without_javascript():
    header=read("templates/_unified_site_header.html")
    nav=read("static/unified-delta-navigation.css")
    assert 'class="delta-nav-sparkles" aria-hidden="true"' in header
    assert header.split('class="delta-nav-sparkles" aria-hidden="true"',1)[1].split("</div>",1)[0].count("<i>")==8
    assert "navStarDrift" in nav and "navStarBlink" in nav
    assert "animation:navStarDrift" in nav
    assert "navStarBlink var(--star-blink)" in nav
    assert "pointer-events:none" in nav
    assert "@media(prefers-reduced-motion:reduce)" in nav


def test_gallery_reveals_in_scroll_and_has_responsive_layout():
    js=read("static/homepage-cinematic.js")
    css=read("static/homepage-cinematic.css")
    assert "'.cabin-experience .cabin-card'" not in js
    assert "'.cabin-experience .section-head > *'" not in js
    assert "Cabin photographs remain static" in js
    assert "observer.unobserve(entry.target)" in js
    assert "window.addEventListener('scroll'" not in js
    assert ".cabin-experience .cabin-mosaic" in css
    assert ".cabin-experience .cabin-card img" in css
    assert "object-fit:contain" in css
    assert "height:auto" in css
    assert "animation:none !important" in css
    assert "content-visibility:visible !important" in css
    assert "backdrop-filter:none !important" in css
    assert "grid-template-columns:minmax(0,1.8fr) minmax(240px,.8fr)" in css
    assert "@media(max-width:740px)" in css
    assert "@media(max-width:480px)" in css
    assert "@media(prefers-reduced-motion:reduce)" in css


def test_homepage_still_renders_with_original_gallery_and_navigation():
    with TestClient(app) as client:
        response=client.get("/")
        assert response.status_code==200
        page=response.text
        assert page.count('id="site-header"')==1
        assert page.count('id="sky-nav-dropdown"')==1
        assert page.count('id="cabin-experience"')==1
        assert "Take to the skies" in page
        for name in CABIN_PHOTOS:
            assert "/static/gallery/"+name+".webp" in page
