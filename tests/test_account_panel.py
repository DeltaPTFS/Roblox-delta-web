"""Account refresh must resolve the authenticated member and tolerate Discord outages."""
import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from website.app import main
from website.app.models import Tier
from test_signin_success import FakeDatabase, linked_user, request_with_session, USER_ID


def mocks(monkeypatch, member=None, crew=None):
    fetch = AsyncMock(return_value=member)
    monkeypatch.setattr(main, 'discord_guild_member', fetch)
    monkeypatch.setattr(main, 'discord_guild_roles', AsyncMock(return_value=[
        {'id': '42', 'name': 'Frequent Flyer', 'color': 123, 'position': 1},
    ]))
    monkeypatch.setattr(main, 'crew_roles_for_display', AsyncMock(return_value=crew or {
        'roles': [], 'member': False, 'status': 'unavailable',
    }))
    return fetch


def test_guest_refresh_verifies_roles_without_creating_a_skymiles_account(monkeypatch):
    fetch = mocks(monkeypatch, {'roles': ['42'], 'user': {'id': USER_ID, 'username': 'Tester', 'global_name': 'Test Member', 'avatar': 'abc'}})
    request = request_with_session({'forms_identity': {'id': USER_ID, 'name': 'Tester'}})
    response = asyncio.run(main.account_panel(request, FakeDatabase()))
    assert response.status_code == 200
    assert b'Frequent Flyer' in response.body
    assert b'Link Roblox &amp; Activate SkyMiles' in response.body
    assert b'SkyMiles Dashboard' not in response.body
    assert b'avatars/' in response.body
    assert 'user_id' not in request.session
    fetch.assert_awaited_once_with(main.settings, USER_ID)
    assert response.headers['cache-control'] == 'private, no-store'


def test_refresh_reconnects_existing_profile_balance_and_asset_links(monkeypatch):
    mocks(monkeypatch, {'roles': []}, {'roles': [{'id': 'crew', 'name': 'Delta Crew'}], 'member': True, 'status': 'verified'})
    user = linked_user()
    user.tier = Tier.MEMBER
    user.miles_balance = 12345
    request = request_with_session({'forms_identity': {'id': USER_ID, 'name': 'Tester'}})
    response = asyncio.run(main.account_panel(request, FakeDatabase(user)))
    for text in (b'12,345', b'SM-00000017', b'SkyMiles Dashboard', b'My Trips', b'My Benefits &amp; Rewards', b'Delta Crew'):
        assert text in response.body
    assert request.session['user_id'] == user.id
    assert 'forms_identity' not in request.session
    assert b'Link Roblox' not in response.body


def test_discord_outage_keeps_existing_assets_accessible(monkeypatch):
    fetch = mocks(monkeypatch)
    fetch.side_effect = httpx.ConnectError('Offline')
    user = linked_user()
    user.tier = Tier.MEMBER
    response = asyncio.run(main.account_panel(request_with_session({'user_id': 17}), FakeDatabase(user)))
    assert response.status_code == 200
    assert b'Your account is still signed in' in response.body
    assert b'My Trips' in response.body


def test_refresh_requires_authenticated_session(monkeypatch):
    fetch = mocks(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.account_panel(request_with_session(), FakeDatabase()))
    assert exc.value.status_code == 401
    fetch.assert_not_awaited()


def test_missing_membership_does_not_claim_verified_member(monkeypatch):
    mocks(monkeypatch, {})
    response = asyncio.run(main.account_panel(request_with_session({'forms_identity': {'id': USER_ID, 'name': 'Tester'}}), FakeDatabase()))
    assert b'No Delta Air Lines membership found' in response.body
    assert b'Server membership confirmed' not in response.body
