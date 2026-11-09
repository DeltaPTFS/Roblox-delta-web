"""Shared navy homepage navigation and airline-style authentication experience."""
from pathlib import Path

from fastapi.testclient import TestClient
from website.app.main import app


ROOT = Path("website")


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_login_inherits_same_public_nav_as_home_and_news():
    login = source("templates/login.html")
    layout = source("templates/community_base.html")
    css = source("static/login-airline.css")
    assert '{% extends "community_base.html" %}' in login
    assert "request.url.path in ['/login', '/signup']" in layout
    assert "delta-auth-page" in layout
    assert "public-navigation.css" in layout
    assert "auth-refresh.css" in layout
    assert "login-airline.css" in layout
    assert layout.index("public-navigation.css") < layout.index("login-airline.css")
    assert "body.delta-auth-page" in css
    assert "background:#06182e" in css
    assert "color:#334155" in css
    assert "background:#c8102e" in css
    assert "delta-centennial.webp" in css
    assert "radial-gradient" not in css
    assert "@media(max-width:600px)" in css


def test_signin_sign_up_and_discord_flows_unchanged():
    login = source("templates/login.html")
    for marker in (
        'data-auth-tab="login"', 'data-auth-tab="signup"',
        'id="auth-panel-login"', 'id="auth-panel-signup"',
        'href="{{ signup_href }}"',
        'href="{{ discord_forms_href if login_intent',
        'data-open-signup', 'data-open-login',
        'login_next != "/dashboard"',
        "community_join_unconfirmed", "discord_connected",
        'history.replaceState',
    ):
        assert marker in login


def test_public_login_responsive_header_and_authorization_actions():
    with TestClient(app) as client:
        login = client.get("/login")
        assert login.status_code == 200
        html = login.text
        assert 'delta-public-site' in html
        assert 'delta-auth-page' in html
        assert html.count('id="site-header"') == 1
        assert 'class="delta-home-signup" href="/signup"' in html
        assert 'class="delta-home-login" href="/login"' in html
        assert "public-navigation.css" in html
        assert "login-airline.css" in html
        assert "Secure authorization" in html
        assert "/auth/discord/login?next=" in html
        assert "Welcome back." in html
        signup = client.get("/signup", follow_redirects=False)
        assert signup.status_code == 303
        assert signup.headers["location"].startswith("/login?mode=signup")
        via_signup = client.get(signup.headers["location"])
        assert via_signup.status_code == 200
        assert 'id="auth-tab-signup"' in via_signup.text
        assert 'role="tab"' in via_signup.text


def test_auth_design_is_scoped_to_login():
    layout = source("templates/community_base.html")
    assert '{% if request.url.path in ["/login", "/signup"] %}' in layout
    assert 'request.url.path in [\'/\', \'/home\']' in layout
    css = source("static/login-airline.css")
    assert css.count("body.delta-auth-page") > 30
