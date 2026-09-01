import os
os.environ.update(DATABASE_URL="sqlite://",COOKIE_SECURE="false",SESSION_SECRET="test-secret-at-least-thirty-two-characters")
from fastapi.testclient import TestClient
from website.app.main import app
from website.app.database import normalize_database_url


def test_render_postgres_url_uses_psycopg3():
    assert normalize_database_url("postgresql://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"
    assert normalize_database_url("postgres://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"
    assert normalize_database_url("postgresql+psycopg2://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"

def test_health():
    with TestClient(app) as client:
        response=client.get("/health")
        assert response.status_code==200 and response.json()=={"status":"ok"}

def test_login_has_safe_oauth_and_disclaimer():
    with TestClient(app) as client:
        response=client.get("/")
        assert "Verify with Roblox" in response.text
        assert "Roblox Password" not in response.text
        assert "Not affiliated with or operated by Delta Air Lines, Inc." in response.text

def test_admin_requires_session():
    with TestClient(app) as client:
        assert client.get("/admin").status_code==401
