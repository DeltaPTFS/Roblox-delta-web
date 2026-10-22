"""Homepage campaign rotation, image quality and accessibility checks."""
from pathlib import Path


ROOT = Path("website")
ADS = (
    "delta-lax",
    "delta-new-york",
    "delta-centennial-ad",
    "delta-tech-ops",
    "delta-engine",
    "delta-skipping",
)


def test_google_drive_advertisements_are_locally_optimized():
    for asset in ADS:
        path = ROOT / "static" / "ads" / (asset + ".webp")
        assert path.exists(), f"Missing Delta advertisement: {path}"
        data = path.read_bytes()
        assert len(data) > 25000, f"Image too small/thumbnail: {asset}"
        assert len(data) < 900000, f"Image too large for responsive web: {asset}"
        assert data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def test_six_advertisements_present_and_two_contextual_placements():
    html = (ROOT / "templates" / "homepage.html").read_text()
    assert html.count('data-ad-slide="') == len(ADS)
    assert "data-ad-dot" in (ROOT / "static" / "delta-ads.js").read_text() or "delta-ad-dots" in html
    for asset in ADS:
        assert '/static/ads/' + asset + '.webp' in html
    assert 'data-ad-carousel' in html
    assert 'data-ad-previous' in html
    assert 'data-ad-next' in html
    assert 'data-ad-toggle' in html
    assert 'aria-label="Featured Delta campaigns' in html
    assert 'delta-ad-secondary-grid' in html
    assert 'alt="New York, the world is yours' in html
    assert 'alt="Delta Technical Operations' in html
    assert "community-hero" in html  # Existing welcome section preserved.


def test_rotation_every_five_seconds_with_manual_and_accessible_controls():
    js = (ROOT / "static" / "delta-ads.js").read_text()
    css = (ROOT / "static" / "delta-ads.css").read_text()
    base = (ROOT / "templates" / "community_base.html").read_text()
    assert "const intervalMs = 5000" in js
    assert "setTimeout(() => go(index + 1), intervalMs)" in js
    for feature in ("visibilitychange","prefers-reduced-motion: reduce",
                    "touchstart","touchend","mouseenter","mouseleave",
                    "keydown","aria-current","aria-hidden"):
        assert feature in js
    assert "document.hidden" in js
    assert "isPaused = media.matches || narrowScreen.matches" in js
    assert "narrowScreen.addEventListener" in js
    assert "delta-ads.css" in base
    assert 'src="/static/delta-ads.js?v={{ asset_version }}"' in base
    home = (ROOT / "templates" / "homepage.html").read_text()
    assert "<script" not in home.split("{% block content %}", 1)[0]
    assert "object-fit:contain" in css
    assert "@media(prefers-reduced-motion:reduce)" in css
    assert "delta-ad-duration" in css
