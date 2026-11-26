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
            url = f"/static/amex-{tier}-transparent.png"
            assert url in html
            asset = client.get(url)
            assert asset.status_code == 200
            assert asset.headers["content-type"].startswith("image/png")
            assert asset.content.startswith(b"\x89PNG\r\n\x1a\n")
            assert int.from_bytes(asset.content[16:20], "big") == 1573
            assert int.from_bytes(asset.content[20:24], "big") == 1000
            assert asset.content[25] == 6  # RGBA
        assert "DELTA ROBLOX MEMBER" not in html
        assert "Cardholder Since" not in html
        assert "Independent Roblox roleplay program only" in html
        css = client.get("/static/amex.css").text
        assert "www.delta.com/content/dam" not in css
        assert "thepointcalculator.com" not in css
        assert "background:transparent" in css
