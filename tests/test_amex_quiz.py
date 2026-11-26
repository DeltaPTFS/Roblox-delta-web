from pathlib import Path
import subprocess
from fastapi.testclient import TestClient
from website.app.main import app

def test_amex_quiz_and_navigation_render():
    with TestClient(app) as client:
        response = client.get("/amex")
        assert response.status_code == 200
        html = response.text
        for marker in ('id="welcome-offer"', 'id="card-quiz"', 'data-card-tab="personal"', 'data-card-tab="business"', 'id="amex-quiz-next"', 'amex-quiz.js', '1539651325615153233'):
            assert marker in html

def test_card_quiz_match_respects_business_and_budget():
    script = """
const assert = require('node:assert/strict');
const {match,questions} = require('./website/static/amex-quiz.js');
assert.equal(questions.length,4);
assert.equal(match(['business','high','first','2000']),'business');
assert.equal(match(['personal','high','first','none']),'none');
assert.equal(match(['personal','high','first','1000']),'platinum');
assert.equal(match(['personal','high','first','2000']),'reserve');
assert.equal(match(['personal','low','main','2000']),'platinum');
"""
    subprocess.run(["node", "-e", script], check=True)

def test_amex_uses_local_transparent_artwork_in_all_card_surfaces():
    with TestClient(app) as client:
        html = client.get("/amex").text
        for tier in ("reserve", "platinum", "gold", "purple"):
            assert f'data-card-face="{tier}"' in html
            url = f"/static/amex-{tier}-fast-v1.webp"
            assert url in html
            asset = client.get(url)
            assert asset.status_code == 200
            assert asset.headers["content-type"].startswith("image/webp")
            assert asset.content[:4] == b"RIFF" and asset.content[8:12] == b"WEBP"
            assert int.from_bytes(asset.content[4:8], "little") + 8 == len(asset.content)
            assert len(asset.content) < 250_000
        assert "DELTA ROBLOX MEMBER" not in html
        assert "Cardholder Since" not in html
        assert "Independent Roblox roleplay program only" in html
        css = client.get("/static/amex.css").text
        assert "www.delta.com/content/dam" not in css
        assert "thepointcalculator.com" not in css
        assert "background:transparent" in css


def test_amex_priority_and_home_feature():
    with TestClient(app) as client:
        html = client.get("/amex").text
        for tier in ("platinum", "reserve"):
            assert f'<link rel="preload" as="image" href="/static/amex-{tier}-fast-v1.webp" fetchpriority="high">' in html
        assert 'loading="eager" fetchpriority="high" decoding="sync"' in html
        assert 'loading="lazy"' not in html.split('data-card-face="platinum"', 1)[1].split('</div>', 1)[0]
        for path in ("/", "/home"):
            home = client.get(path).text
            assert 'id="amex-cards"' in home
            assert 'href="/amex#card-quiz"' in home
            assert '/static/amex-platinum-fast-v1.webp' in home
            assert '/static/amex-reserve-fast-v1.webp' in home


def test_amex_business_is_for_external_affairs_partnerships():
    with TestClient(app) as client:
        html = client.get("/amex").text
        assert "Business Cards are intended for External Affairs partnerships" in html
        assert "Contact External Affairs on Discord" in html
        assert "1539651325615153233" in html
        js = client.get("/static/amex-quiz.js").text
        assert "External Affairs Partnership" in js
        assert "Contact External Affairs on Discord" in js


def test_amex_social_preview_uses_uploaded_photo():
    with TestClient(app) as client:
        html = client.get("/amex", headers={"User-Agent": "Discordbot/2.0"}).text
        assert 'property="og:title" content="AMEX Cards | Delta Roblox SkyMiles"' in html
        assert 'property="og:image" content="https://roblox-delta-web.vercel.app/static/amex-social-preview.jpeg"' in html
        assert 'name="twitter:card" content="summary_large_image"' in html
        assert "External Affairs Business Card partnerships" in html
        image = client.get("/static/amex-social-preview.jpeg")
        assert image.status_code == 200
        assert image.headers["content-type"].startswith("image/jpeg")
        assert image.content.startswith(b"\xff\xd8")
        assert "amex-social-preview.jpeg" not in client.get("/").text
