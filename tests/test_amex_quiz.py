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

def test_amex_uses_clipped_official_artwork_in_all_card_surfaces():
    with TestClient(app) as client:
        html = client.get("/amex").text
        for tier in ("reserve", "platinum", "gold", "purple"):
            assert f'data-card-face="{tier}"' in html
            assert f'amex-{tier}-card.png' not in html
        assert "DELTA ROBLOX MEMBER" in html
        assert "Cardholder Since" in html
        css = client.get("/static/amex.css").text
        assert "delta-skymiles-reserve-american-express-personal-card-v1.webp" in css
        assert "148.333% 194.69%" in css
