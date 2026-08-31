from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_url: str = "http://localhost:8000"
    database_url: str = "sqlite:///./skymiles.db"
    session_secret: str = "development-only-change-this-secret"
    roblox_client_id: str = ""
    roblox_client_secret: str = ""
    roblox_redirect_uri: str = "http://localhost:8000/auth/roblox/callback"
    roblox_group_id: str = ""
    roblox_group_url: str = "https://www.roblox.com/communities/0"
    discord_client_id: str = ""
    discord_client_secret: str = ""
    discord_redirect_uri: str = "http://localhost:8000/auth/discord/callback"
    discord_guild_id: str = ""
    discord_invite_url: str = "https://discord.gg/"
    staff_roblox_min_rank: int = 100
    admin_roblox_min_rank: int = 200
    owner_roblox_user_ids: str = ""
    staff_discord_role_ids: str = ""
    admin_discord_role_ids: str = ""
    welcome_bonus_miles: int = 0
    local_password_login_enabled: bool = False
    cookie_secure: bool = True

    @staticmethod
    def ids(value: str) -> set[str]:
        return {item.strip() for item in value.split(",") if item.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
