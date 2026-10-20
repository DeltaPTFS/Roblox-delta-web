"""Discord sign-in celebration and remembered SkyMiles session regression tests."""
import os
from pathlib import Path
from types import SimpleNamespace
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("SESSION_SECRET", "test-secret-at-least-thirty-two-characters")

from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from starlette.requests import Request
from website.app.main import login, queue_signin_success, signin_success, finish_signin_celebration
from website.app.models import Status, User
from website.app.security import current_user, linked_user_from_session


USER_ID = "1539968936681148456"


class FakeDatabase:
    def __init__(self, user=None):
        self.user = user

    def get(self, model, pk):
        return self.user if self.user and pk == self.user.id else None

    def scalar(self, _statement):
        return self.user


def request_with_session(session=None, path="/login"):
    return Request({
        "type": "http", "method": "GET", "path": path, "query_string": b"",
        "headers": [], "scheme": "https",
        "server": ("roblox-delta-web.vercel.app", 443),
        "session": dict(session or {}),
    })


def linked_user():
    return User(
        id=17, roblox_user_id="543210", discord_user_id=USER_ID,
        discord_username="DeltaTester", discord_display_name="Captain Delta",
        discord_role_ids=[], roblox_display_name="Captain Delta",
        roblox_username="DeltaTester", account_status=Status.ACTIVE,
        skymiles_number="SM-00000017", permanent_ban=False,
    )


def test_existing_discord_form_session_upgrades_to_existing_skymiles_membership():
    member=linked_user()
    request=request_with_session({"forms_identity":{"id":USER_ID,"name":"Captain Delta"}})
    resolved=linked_user_from_session(request,FakeDatabase(member))
    assert resolved is member
    assert request.session["user_id"]==17
    assert "forms_identity" not in request.session
    assert current_user(request,FakeDatabase(member)) is member


def test_no_sky_miles_membership_is_created_from_discord_only_login():
    request=request_with_session({"forms_identity":{"id":USER_ID,"name":"Captain Delta"}})
    assert linked_user_from_session(request,FakeDatabase(None)) is None
    assert "user_id" not in request.session
    assert request.session["forms_identity"]["id"]==USER_ID


def test_expired_or_untrusted_discord_id_does_not_promote_membership():
    member=linked_user()
    for payload in [{"id":"NOT_A_DISCORD_ID"},{"id":"123"},{"id":"not "+USER_ID},{}]:
        request=request_with_session({"forms_identity":payload})
        assert linked_user_from_session(request,FakeDatabase(member)) is None
        assert "user_id" not in request.session


def test_suspended_members_do_not_get_an_automatic_skymiles_login():
    member=linked_user()
    member.account_status=Status.DISABLED
    request=request_with_session({"forms_identity":{"id":USER_ID,"name":"Captain Delta"}})
    assert linked_user_from_session(request,FakeDatabase(member)) is None


def test_existing_linked_member_skips_skymiles_login_screen():
    request=request_with_session({"forms_identity":{"id":USER_ID,"name":"Captain Delta"}})
    result=login(request,db=FakeDatabase(linked_user()))
    assert isinstance(result,RedirectResponse)
    assert result.status_code==303
    assert result.headers["location"]=="/dashboard?already_signed_in=1"


def test_logged_in_member_sees_explicit_already_signed_in_notice():
    request=request_with_session({"user_id":17},path="/login")
    result=login(request,mode="signup",db=FakeDatabase(linked_user()))
    assert result.status_code==303
    assert result.headers["location"]=="/dashboard?already_signed_in=1"
    login_markup=Path("website/templates/base.html").read_text()
    assert "You're already signed in!" in login_markup
    assert 'request.query_params.get(\'already_signed_in\')' in login_markup


def test_signin_success_stays_until_continue_to_original_destination_and_rotates_cookie_id():
    request=request_with_session({"user_id":17},path="/signin/success")
    redirect=queue_signin_success(request,display_name="Captain Delta",
                                  destination="/dashboard",kind="skymiles",
                                  join_status="already_member")
    assert redirect.headers["location"]=="/signin/success"
    assert request.scope["rotate_session"] is True
    assert request.session["signin_celebration"]["name"]=="Captain Delta"

    rendered=signin_success(request,db=FakeDatabase(linked_user()))
    assert rendered.status_code==200
    assert b"Captain Delta" in rendered.body
    assert b"signin-success.js" in rendered.body
    assert "signin_celebration" in request.session

    again=signin_success(request,db=FakeDatabase(linked_user()))
    assert again.status_code == 200
    assert b"Go to My Dashboard" in again.body

    finish=finish_signin_celebration(request)
    assert isinstance(finish,RedirectResponse)
    assert finish.headers["location"]=="/dashboard"
    assert "signin_celebration" not in request.session

    subsequent=signin_success(request,db=FakeDatabase(linked_user()))
    assert isinstance(subsequent,RedirectResponse)
    assert subsequent.headers["location"]=="/dashboard"


def test_discord_only_success_cannot_claim_skymiles_membership():
    request=request_with_session({"forms_identity":{"id":USER_ID,"name":"Guest Delta"},
                                  "signin_celebration":{"name":"Guest Delta","destination":"/forms",
                                      "kind":"forms","join_status":"already_member","event_id":"once"}},
                                 path="/signin/success")
    page=signin_success(request,db=FakeDatabase(None))
    assert page.status_code==200
    assert b"Your Discord identity is confirmed" in page.body
    assert b"Your Delta SkyMiles account is connected" not in page.body


def test_first_time_signup_gets_distinct_confirmation_page():
    request=request_with_session({"user_id":17},path="/signin/success")
    response=queue_signin_success(request,display_name="Captain Delta",
                                  destination="/dashboard?tutorial=1",
                                  kind="signup",join_status="joined")
    assert response.headers["location"]=="/signin/success"
    rendered=signin_success(request,db=FakeDatabase(linked_user()))
    assert rendered.status_code==200
    assert b"You've <em>signed up.</em>" in rendered.body
    assert b"Your new Delta Roblox SkyMiles account is ready!" in rendered.body


def test_sound_and_four_second_animation_are_bundled_as_real_assets():
    root=Path("website")
    sound=root/"static/audio/delta-signin.mp3"
    assert sound.exists()
    assert 15000<sound.stat().st_size<150000
    assert sound.read_bytes()[:3] in (b"ID3",b"\xff\xfb\x90")
    html=(root/"templates/signin_success.html").read_text()
    css=(root/"static/signin-success.css").read_text()
    js=(root/"static/signin-success.js").read_text()
    assert "You're <em>signed in.</em>" in html
    assert "success-check-svg" in html
    assert "/static/audio/delta-signin.mp3" in html
    assert "setTimeout(activate, 3900)" in js
    assert "audio.play()" in js
    assert "sound-button" not in html
    assert "autoplay-note" not in html
    assert 'href="/signin/finish"' in html
    assert "window.location.replace(destination)" not in js
    assert "@media(prefers-reduced-motion:reduce)" in css


def test_secure_month_long_cookie_and_discord_identity_match():
    main=(Path("website/app/main.py")).read_text()
    middleware=(Path("website/app/session.py")).read_text()
    assert "max_age=30*86400" in main
    assert "rotate_session" in middleware
    assert "HttpOnly; SameSite=Lax" in middleware
    assert 'select(User).where(User.discord_user_id==identity["id"])' in main
    assert 'account_linked=bool(sky_user' in main
    assert 'request.session["user_id"]=sky_user.id' in main
