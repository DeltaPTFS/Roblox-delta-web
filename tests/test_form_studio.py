"""Regression tests for Google Forms-like editor and consent-based Discord joining."""
import asyncio
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader, select_autoescape

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SESSION_SECRET", "unit-test-secret-with-32-or-more-characters")
os.environ.setdefault("COOKIE_SECURE", "false")

from website.app import community, oauth
from website.app.config import Settings


def test_form_editor_has_real_google_forms_style_controls():
    html = Path("website/templates/forms/editor.html").read_text()
    for value in ["Preview", "Duplicate Form", "Save as Draft", "New Section", "Linear scale", "Email address",
                  "Website URL", "Time", "Required question", "Settings & Roles"]:
        if value == "New Section":
            assert "Section heading" in html
        else:
            assert value in html
    assert "state.allowed_roles" in html
    assert "document.createElement" in html
    assert "id=\"preview-form\"" in html


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is needed for JavaScript syntax validation")
def test_editor_script_passes_node_syntax_check():
    class FakeRequest:
        scope = {"session": {}}
        base_url = "https://roblox-delta-web.vercel.app/"
        query_params = {}
        url = type("FakeURL", (), {"path": "/forms/new"})()

    env = Environment(loader=FileSystemLoader("website/templates"),
                      autoescape=select_autoescape(["html"]))
    rendered = env.get_template("forms/editor.html").render(
        request=FakeRequest(), viewer={"name":"Tester"}, csrf="testing",
        settings=Settings(), form=None, catalog={"airlines":[], "crew":[]}, access="OWNER"
    )
    scripts = re.findall(r"<script>(.*?)</script>", rendered, re.S)
    assert scripts, "Form studio needs its interactive JavaScript"
    for script in scripts:
        result = subprocess.run(["node", "--check"], input=script, text=True,
                                capture_output=True, check=False)
        assert result.returncode == 0, result.stderr


def test_question_schema_supports_sections_and_more_types():
    for kind in ("section", "email", "time", "url", "scale", "text", "textarea",
                 "radio", "checkbox", "select", "number", "date"):
        assert kind in community.QUESTION_TYPES


def test_save_new_form_preserves_scale_and_restricts_roles(monkeypatch):
    class FakeDB:
        saved = None
        committed = False
        def add(self, item):
            self.saved = item
        def flush(self):
            self.saved.id = 42
        def commit(self):
            self.committed = True

    async def verified(*_):
        return {"id":"123456789012345678", "name":"Admin"}, {"airlines":["1539016506216812567"]}
    async def catalog():
        return {"airlines":[{"id":"1539016506216812567", "name":"Human Resources"}],
                "crew":[{"id":"1554666482988875788","name":"Human Resources"}]}

    monkeypatch.setattr(community, "verified_viewer", verified)
    monkeypatch.setattr(community, "role_catalog", catalog)
    monkeypatch.setattr(community, "check_csrf", lambda *_: None)
    monkeypatch.setattr(community, "enqueue_form", lambda *_: None)
    db = FakeDB()
    questions = [
        {"id":"heading", "type":"section","label":"Crew Availability","help_text":"Pick one", "required":True},
        {"id":"rating", "type":"scale","label":"Rate the flight","required":True,
         "scale_min":0,"scale_max":10,"min_label":"Poor","max_label":"Excellent"},
        {"id":"mail", "type":"email","label":"Email", "required":False}
    ]
    data = {"title":"Crew Survey","description":"Test","status":"PUBLISHED","questions":questions,
            "allowed_roles":{"airlines":["1539016506216812567"],"crew":["1554666482988875788"]}}
    result = asyncio.run(community.save_form(object(), csrf="csrf", payload=json.dumps(data), db=db))
    assert result.status_code == 303
    assert db.committed
    assert db.saved.questions[0]["required"] is False
    assert db.saved.questions[1]["scale_min"] == 0
    assert db.saved.questions[1]["scale_max"] == 10
    assert db.saved.allowed_roles["crew"] == ["1554666482988875788"]


def test_invalid_scale_cannot_be_saved(monkeypatch):
    class FakeDB: pass
    async def verified(*_):
        return {"id":"123456789012345678", "name":"Admin"}, {"airlines":["1539016506216812567"]}
    async def catalog(): return {"airlines":[], "crew":[]}
    monkeypatch.setattr(community, "verified_viewer", verified)
    monkeypatch.setattr(community, "role_catalog", catalog)
    monkeypatch.setattr(community, "check_csrf", lambda *_: None)
    payload=json.dumps({"title":"Survey","status":"DRAFT",
                        "questions":[{"id":"scale1","label":"Scale","type":"scale",
                                      "scale_min":1,"scale_max":15}]})
    with pytest.raises(HTTPException) as caught:
        asyncio.run(community.save_form(object(), csrf="x", payload=payload, db=FakeDB()))
    assert caught.value.status_code == 422


def test_sky_miles_menu_has_futuristic_panel_and_protected_form_link():
    html=Path("website/templates/base.html").read_text()
    shared=Path("website/templates/_unified_site_header.html").read_text()
    css=Path("website/static/sky-nav-future.css").read_text()
    behavior=Path("website/static/unified-delta-navigation.js").read_text()
    assert '{% include "_unified_site_header.html" %}' in html
    assert 'href="/forms/new"' in shared
    assert '{% if nav_level in ("OWNER","ADMIN","STAFF") %}' in shared
    assert 'sky-menu-grid' in shared
    assert 'deltaMenuReveal' in css
    assert 'prefers-reduced-motion' in css
    assert "Escape" in behavior

def test_discord_oauth_explicitly_requests_join_permission():
    assert "guilds.join" in oauth.discord_authorize(Settings(discord_client_id="123",
            discord_redirect_uri="https://example.com/auth/discord/callback"),"state","challenge")


def test_discord_login_adds_member_with_bot_after_user_consents():
    guild = "1538738611988467782"
    user = "1539005297417519205"
    calls=[]
    class Resp:
        def __init__(self,status,body):
            self.status_code=status
            self.body=body
        def json(self):return self.body
        def raise_for_status(self):
            if self.status_code>=400:raise RuntimeError("HTTP "+str(self.status_code))
            return self
    class StubClient:
        async def __aenter__(self):return self
        async def __aexit__(self,*_):return False
        async def post(self,url,**_):return Resp(200,{"access_token":"test-access"})
        async def put(self,url,headers=None,json=None):
            calls.append((url,headers,json))
            return Resp(201,{"user":{"id":user},"roles":[]})
        async def get(self,url,headers=None):
            if url.endswith("/users/@me"):return Resp(200,{"id":user,"username":"Pilot","avatar":None})
            if "/users/@me/guilds/" in url:return Resp(404,{})
            if "/guilds/" in url and "/members/" in url:return Resp(200,{"user":{"id":user},"nick":"Pilot", "roles":[]})
            raise AssertionError("Unexpected URL "+url)
    with patch("website.app.oauth.httpx.AsyncClient", lambda **_: StubClient()):
        result=asyncio.run(oauth.discord_identity(
            Settings(discord_bot_token="bot-token",discord_guild_id=guild,
                     discord_client_id="client-id",discord_client_secret="secret"),
            "code","verifier"))
    assert result["join_status"] == "joined"
    assert result["member"]["nick"] == "Pilot"
    assert calls and calls[0][0].endswith("/guilds/"+guild+"/members/"+user)
    assert calls[0][2] == {"access_token":"test-access"}


def test_discord_join_failure_is_not_reported_as_success():
    class Resp:
        def __init__(self,status,body):
            self.status_code=status
            self.body=body
        def json(self):return self.body
        def raise_for_status(self):return self
    class StubClient:
        async def __aenter__(self):return self
        async def __aexit__(self,*_):return False
        async def post(self,*_args,**_kw):return Resp(200,{"access_token":"token"})
        async def get(self,url,**_):
            return Resp(200,{"id":"1539005297417519205","username":"Test","avatar":None}) if url.endswith("/users/@me") else Resp(404,{})
        async def put(self,*_args,**_kw):return Resp(403,{})
    with patch("website.app.oauth.httpx.AsyncClient", lambda **_: StubClient()):
        result=asyncio.run(oauth.discord_identity(
            Settings(discord_guild_id="1538738611988467782",discord_bot_token="bot-token"),"code","verifier"))
    assert result["join_status"] == "join_failed"
    assert result["member"] is None
