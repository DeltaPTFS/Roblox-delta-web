import httpx
from urllib.parse import urlencode
from .config import Settings

ROBLOX_AUTHORIZE = "https://apis.roblox.com/oauth/v1/authorize"
ROBLOX_TOKEN = "https://apis.roblox.com/oauth/v1/token"
ROBLOX_USERINFO = "https://apis.roblox.com/oauth/v1/userinfo"
ROBLOX_GROUPS = "https://groups.roblox.com/v1/users/{user_id}/groups/roles"
ROBLOX_AVATAR = "https://thumbnails.roblox.com/v1/users/avatar-headshot"
DISCORD_AUTHORIZE = "https://discord.com/oauth2/authorize"
DISCORD_TOKEN = "https://discord.com/api/v10/oauth2/token"
DISCORD_ME = "https://discord.com/api/v10/users/@me"
DISCORD_MEMBER = "https://discord.com/api/v10/users/@me/guilds/{guild_id}/member"


def roblox_authorize(settings: Settings, state: str, challenge: str) -> str:
    return ROBLOX_AUTHORIZE + "?" + urlencode({"client_id": settings.roblox_client_id, "redirect_uri": settings.roblox_redirect_uri, "response_type": "code", "scope": "openid profile", "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})


def discord_authorize(settings: Settings, state: str, challenge: str) -> str:
    return DISCORD_AUTHORIZE + "?" + urlencode({"client_id": settings.discord_client_id, "redirect_uri": settings.discord_redirect_uri, "response_type": "code", "scope": "identify guilds.members.read", "state": state, "code_challenge": challenge, "code_challenge_method": "S256", "prompt": "consent"})


async def roblox_identity(settings: Settings, code: str, verifier: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        token = (await client.post(ROBLOX_TOKEN, data={"grant_type":"authorization_code","code":code,"client_id":settings.roblox_client_id,"client_secret":settings.roblox_client_secret,"redirect_uri":settings.roblox_redirect_uri,"code_verifier":verifier})).raise_for_status().json()
        headers = {"Authorization": f"Bearer {token['access_token']}"}
        identity = (await client.get(ROBLOX_USERINFO, headers=headers)).raise_for_status().json()
        user_id = str(identity["sub"])
        groups = (await client.get(ROBLOX_GROUPS.format(user_id=user_id))).raise_for_status().json().get("data", [])
        membership = next((x for x in groups if str(x["group"]["id"]) == settings.roblox_group_id), None)
        avatar_data = (await client.get(ROBLOX_AVATAR, params={"userIds":user_id,"size":"150x150","format":"Png","isCircular":"true"})).raise_for_status().json().get("data", [])
        return {"id":user_id,"username":identity.get("preferred_username") or identity.get("nickname"),"display_name":identity.get("name") or identity.get("preferred_username"),"avatar":avatar_data[0].get("imageUrl") if avatar_data else identity.get("picture"),"membership":membership}


async def discord_identity(settings: Settings, code: str, verifier: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        token = (await client.post(DISCORD_TOKEN, data={"grant_type":"authorization_code","code":code,"client_id":settings.discord_client_id,"client_secret":settings.discord_client_secret,"redirect_uri":settings.discord_redirect_uri,"code_verifier":verifier})).raise_for_status().json()
        headers = {"Authorization": f"Bearer {token['access_token']}"}
        user = (await client.get(DISCORD_ME, headers=headers)).raise_for_status().json()
        member_response = await client.get(DISCORD_MEMBER.format(guild_id=settings.discord_guild_id), headers=headers)
        member = member_response.json() if member_response.status_code == 200 else None
        avatar = f"https://cdn.discordapp.com/avatars/{user['id']}/{user['avatar']}.png" if user.get("avatar") else None
        return {"id":str(user["id"]),"username":user["username"],"display_name":user.get("global_name") or user["username"],"avatar":avatar,"member":member}
