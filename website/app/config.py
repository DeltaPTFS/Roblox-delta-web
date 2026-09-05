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
    discord_skymiles_channel_url: str = "https://discord.com/channels/1538738611988467782/1541156846579089519"
    discord_bot_token: str = ""
    discord_booking_channel_id: str = ""
    discord_log_channel_id: str = "1539005101941850274"
    discord_unverified_role_id: str = ""
    discord_member_role_id: str = "1539005061609422849"
    discord_silver_role_id: str = ""
    discord_gold_role_id: str = "1539005058686001275"
    discord_platinum_role_id: str = "1539005057062805594"
    discord_diamond_role_id: str = "1539005055322292335"
    staff_roblox_min_rank: int = 100
    admin_roblox_min_rank: int = 200
    owner_roblox_user_ids: str = ""
    owner_discord_role_ids: str = "1539005297417519205"
    button_command_role_ids: str = "1539005297417519205"
    staff_discord_role_ids: str = "1539968936681148456"
    admin_discord_role_ids: str = "1539005030189891684,1539005033020919828"
    welcome_bonus_miles: int = 0
    local_password_login_enabled: bool = False
    cookie_secure: bool = True

    @property
    def medallion_role_ids(self) -> dict[str, str]:
        return {
            "SILVER": self.discord_silver_role_id,
            "GOLD": self.discord_gold_role_id,
            "PLATINUM": self.discord_platinum_role_id,
            "DIAMOND": self.discord_diamond_role_id,
        }

    @staticmethod
    def ids(value: str) -> set[str]:
        return {item.strip() for item in value.split(",") if item.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
