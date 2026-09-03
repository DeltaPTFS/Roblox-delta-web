import os
from pathlib import Path
from datetime import datetime, timezone
os.environ.update(DATABASE_URL="sqlite://",COOKIE_SECURE="false",SESSION_SECRET="test-secret-at-least-thirty-two-characters")
from fastapi.testclient import TestClient
from website.app.main import app, display_discord_roles, is_tier_upgrade, next_medallion_expiration, qualifies_for_tier
from website.app.database import normalize_database_url
from website.app.models import Tier, TierConfig, User
from website.app.config import Settings
from website.app.security import permission
from website.app.oauth import expected_skymiles_role_ids


def test_render_postgres_url_uses_psycopg3():
    assert normalize_database_url("postgresql://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"
    assert normalize_database_url("postgres://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"
    assert normalize_database_url("postgresql+psycopg2://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"


def test_medallion_expires_next_new_year_at_midnight_eastern():
    joined = datetime(2026, 3, 3, 18, 30, tzinfo=timezone.utc)
    assert next_medallion_expiration(joined) == datetime(2027, 1, 1, 5, 0, tzinfo=timezone.utc)

def test_medallion_qualification_requires_all_three_metrics():
    member = User(lifetime_miles=100_000, medallion_qualifying_points=0, segments_flown=0)
    diamond = TierConfig(tier=Tier.DIAMOND, miles_threshold=50_000, mqp_threshold=28_000, segments_threshold=15)
    assert not qualifies_for_tier(member, diamond)
    member.medallion_qualifying_points=28_000; member.segments_flown=15
    assert qualifies_for_tier(member, diamond)


def test_medallion_changes_must_be_upgrades():
    assert is_tier_upgrade(Tier.SILVER, Tier.GOLD)
    assert not is_tier_upgrade(Tier.GOLD, Tier.GOLD)
    assert not is_tier_upgrade(Tier.PLATINUM, Tier.SILVER)


def test_discord_roles_map_to_three_staff_panels():
    settings=Settings()
    member=User(roblox_user_id="1",discord_role_ids=["1539968936681148456"])
    assert permission(member,settings)=="STAFF"
    member.discord_role_ids=["1539005030189891684"]
    assert permission(member,settings)=="ADMIN"
    member.discord_role_ids=["1539005297417519205"]
    assert permission(member,settings)=="OWNER"


def test_expected_discord_roles_keep_member_and_exact_medallion():
    settings=Settings()
    assert expected_skymiles_role_ids(settings)=={"1539005061609422849"}
    assert expected_skymiles_role_ids(settings,"GOLD")=={"1539005061609422849","1539005058686001275"}


def test_member_discord_roles_display_real_guild_names_and_colors():
    catalog=[{"id":"everyone","name":"@everyone","color":0},{"id":"staff","name":"Flight Operations","color":0xD7193F},{"id":"gold","name":"Gold Medallion","color":0xC7962D}]
    assert display_discord_roles(["staff","gold"],catalog)==[{"id":"staff","name":"Flight Operations","color":0xD7193F},{"id":"gold","name":"Gold Medallion","color":0xC7962D}]

def test_health():
    with TestClient(app) as client:
        response=client.get("/health")
        assert response.status_code==200 and response.json()=={"status":"ok"}


def test_static_assets_are_cached_and_compressed():
    with TestClient(app) as client:
        response=client.get("/static/style.css",headers={"Accept-Encoding":"gzip"})
        assert response.status_code==200
        assert "max-age=3600" in response.headers["cache-control"]
        assert response.headers.get("content-encoding")=="gzip"

def test_login_has_safe_oauth_and_disclaimer():
    with TestClient(app) as client:
        response=client.get("/")
        assert "Verify with Roblox" in response.text
        assert "Continue with Discord" in response.text
        assert "COMMUNITY OPERATIONS" in response.text
        assert '<html lang="en" class="theme-light">' in response.text
        assert "/static/style.css?v=" in response.text
        assert "ROLEPLAY COMMUNITY</small>" not in response.text
        assert "Roblox Password" not in response.text
        assert "Not affiliated with or operated by Delta Air Lines, Inc." in response.text

def test_admin_requires_session():
    with TestClient(app) as client:
        assert client.get("/admin").status_code==401


def test_flight_management_is_manual_and_local_time_enabled():
    main_source = Path("website/app/main.py").read_text()
    flight_template = Path("website/templates/flights.html").read_text()
    assert 'if new_status == FlightStatus.COMPLETED' not in main_source
    assert 'data-local-time' in flight_template
    assert 'Leave Flight &amp; Request Refund' in flight_template
    assert 'Rebook This Flight' in flight_template


def test_invalid_flight_form_preserves_submitted_values():
    main_source = Path("website/app/main.py").read_text()
    admin_template = Path("website/templates/admin.html").read_text()
    assert 'request.session["flight_form"]=submitted' in main_source
    assert "flight_form.get('flight_number','')" in admin_template
    assert 'flight_form_error' in admin_template


def test_release_update_notice_and_uncached_health():
    base_template = Path("website/templates/base.html").read_text()
    assert "Website update in progress" in base_template
    assert "skymiles-release-{{ asset_version }}" in base_template
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.headers["cache-control"] == "no-store"


def test_my_trips_refunds_moderation_and_notification_logging_present():
    models = Path("website/app/models.py").read_text()
    main = Path("website/app/main.py").read_text()
    trip = Path("website/templates/trip_detail.html").read_text()
    assert "class ModerationAction" in models and "class NotificationLog" in models
    assert "booking.created_at+timedelta(hours=24)" in main
    assert 'delivery_status="PENDING"' in main
    assert 'log.delivery_status="DELIVERED"' in main
    assert "Refund Eligible Until" in trip
    assert "To Be Assigned" in trip
    assert "View My Trips" in trip and "Cancel Flight" in trip


def test_discord_dm_uses_installed_custom_emoji_catalog():
    oauth = Path("website/app/oauth.py").read_text()
    assert "/emojis" in oauth
    assert "async def discord_dm" in oauth
    assert '"recipient_id":user_id' in oauth


def test_confirmation_numbers_are_unique_and_title_cased_messages_exist():
    from website.app.main import confirmation_number
    values={confirmation_number() for _ in range(250)}
    assert len(values)==250
    assert all(value.startswith("DL") and len(value)==12 for value in values)
    source=Path("website/app/main.py").read_text()
    assert "Delta Air Lines | Booking Confirmed" in source
    assert "Delta Air Lines | Flight Cancelled" in source
    assert "Delta Air Lines | Flight Reminder" in source
    assert "To Be Assigned" in source


def test_mqp_and_segments_are_committed_to_member_account():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from website.app.database import Base
    from website.app.main import persist_qualification_adjustment
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        member=User(roblox_user_id="qual-rbx",roblox_username="qual",roblox_display_name="Qual",discord_user_id="qual-discord",discord_username="qual",discord_display_name="Qual",skymiles_number="SM-99000001",medallion_qualifying_points=100,segments_flown=2)
        db.add(member); db.commit(); member_id=member.id
        _,before,after=persist_qualification_adjustment(db,member_id,900,3)
        assert before=={"mqp":100,"segments":2}
        assert after=={"mqp":1000,"segments":5}
        db.commit()
    with Session(engine) as db:
        persisted=db.get(User,member_id)
        assert persisted.medallion_qualifying_points==1000
        assert persisted.segments_flown==5


def test_terminal_flights_have_ten_minute_panel_grace_and_archive():
    source=Path("website/app/main.py").read_text()
    admin=Path("website/templates/admin.html").read_text()
    assert "FLIGHT_TERMINAL_GRACE = timedelta(minutes=10)" in source
    assert "Flight.updated_at>terminal_cutoff" in source
    assert "Flight.updated_at<=terminal_cutoff" in source
    assert "Terminal flights move here ten minutes" in admin


def test_roblox_game_links_are_validated_for_boarding_qr():
    from website.app.main import validated_roblox_game_url
    assert validated_roblox_game_url("https://www.roblox.com/games/12345/Delta") == "https://www.roblox.com/games/12345/Delta"
    import pytest
    for invalid in ("http://roblox.com/games/1","https://evil.example/game","javascript:alert(1)","https://roblox.com@evil.example/games/1"):
        with pytest.raises(ValueError): validated_roblox_game_url(invalid)


def test_boarding_pass_has_private_qr_and_assignment_fallbacks():
    main=Path("website/app/main.py").read_text()
    template=Path("website/templates/trip_detail.html").read_text()
    admin=Path("website/templates/admin.html").read_text()
    assert '@app.get("/trips/{confirmation}/qr.svg")' in main
    assert 'Booking.user_id==user.id' in main
    assert "Scan to join the Roblox game" in template
    assert "To Be Assigned" in template
    assert 'name="roblox_game_url"' in admin
