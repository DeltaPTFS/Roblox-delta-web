import os
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
        assert "ROLEPLAY COMMUNITY</small>" not in response.text
        assert "Roblox Password" not in response.text
        assert "Not affiliated with or operated by Delta Air Lines, Inc." in response.text

def test_admin_requires_session():
    with TestClient(app) as client:
        assert client.get("/admin").status_code==401
