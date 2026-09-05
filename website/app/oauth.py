import httpx
from time import monotonic
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
DISCORD_GUILD_EVENTS = "https://discord.com/api/v10/guilds/{guild_id}/scheduled-events"
DISCORD_GUILD_ROLE = "https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}/roles/{role_id}"
DISCORD_CHANNEL_MESSAGES = "https://discord.com/api/v10/channels/{channel_id}/messages"
_guild_role_cache: dict[str, tuple[float, list[dict]]] = {}
_emoji_cache: tuple[float, dict[str,str]] | None = None


async def discord_unverified_role_id(settings: Settings) -> str:
    """Resolve the configured role, or the guild role named Unverified."""
    if settings.discord_unverified_role_id:
        return settings.discord_unverified_role_id
    roles = await discord_guild_roles(settings)
    role = next((item for item in roles if str(item.get("name", "")).casefold() == "unverified"), None)
    return str(role["id"]) if role else ""


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


async def discord_set_medallion_roles(settings: Settings, user_id: str, tier_name: str | None = None) -> bool:
    """Verify a member by removing Unverified and applying exact SkyMiles roles."""
    if not settings.discord_bot_token:
        return False
    headers = {"Authorization": f"Bot {settings.discord_bot_token}"}
    desired = settings.medallion_role_ids.get(tier_name or "", "")
    if tier_name and not desired: raise ValueError(f"No Discord role ID is configured for {tier_name}")
    async with httpx.AsyncClient(timeout=15) as client:
        member_url = DISCORD_GUILD_ROLE.format(guild_id=settings.discord_guild_id, user_id=user_id, role_id=settings.discord_member_role_id)
        (await client.put(member_url, headers=headers)).raise_for_status()
        unverified_role_id = await discord_unverified_role_id(settings)
        if unverified_role_id:
            unverified_url = DISCORD_GUILD_ROLE.format(guild_id=settings.discord_guild_id, user_id=user_id, role_id=unverified_role_id)
            response = await client.delete(unverified_url, headers=headers)
            if response.status_code not in {204, 404}:
                response.raise_for_status()
        for role_id in {role for role in settings.medallion_role_ids.values() if role}:
            url = DISCORD_GUILD_ROLE.format(guild_id=settings.discord_guild_id, user_id=user_id, role_id=role_id)
            response = await (client.put(url, headers=headers) if role_id == desired else client.delete(url, headers=headers))
            if response.status_code not in {204, 404}:
                response.raise_for_status()
    return True


def expected_skymiles_role_ids(settings: Settings, tier_name: str | None = None) -> set[str]:
    """Return the exact managed Discord roles expected for a membership tier."""
    expected={settings.discord_member_role_id} if settings.discord_member_role_id else set()
    desired=settings.medallion_role_ids.get(tier_name or "", "")
    if tier_name and not desired:
        raise ValueError(f"No Discord role ID is configured for {tier_name}")
    if desired: expected.add(desired)
    return expected


async def discord_sync_skymiles_roles(settings: Settings, user_id: str, tier_name: str | None = None) -> list[str]:
    """Apply and verify the member's exact managed roles against Discord."""
    if not await discord_set_medallion_roles(settings,user_id,tier_name):
        raise RuntimeError("Discord bot role synchronization is not configured")
    roles=await discord_member_roles(settings,user_id)
    if roles is None: raise RuntimeError("Discord roles could not be verified")
    actual=set(roles); expected=expected_skymiles_role_ids(settings,tier_name)
    managed={settings.discord_member_role_id,*settings.medallion_role_ids.values()}-{""}
    if not expected.issubset(actual) or actual & (managed-expected):
        raise RuntimeError("Discord returned an unexpected managed role state")
    return roles


async def discord_remove_skymiles_roles(settings: Settings, user_id: str) -> bool:
    """Remove SkyMiles roles and restore Unverified when membership ends."""
    if not settings.discord_bot_token:
        return False
    headers = {"Authorization": f"Bot {settings.discord_bot_token}"}
    role_ids = {settings.discord_member_role_id, *settings.medallion_role_ids.values()} - {""}
    async with httpx.AsyncClient(timeout=15) as client:
        for role_id in role_ids:
            url = DISCORD_GUILD_ROLE.format(guild_id=settings.discord_guild_id, user_id=user_id, role_id=role_id)
            response = await client.delete(url, headers=headers)
            if response.status_code not in {204, 404}:
                response.raise_for_status()
        unverified_role_id = await discord_unverified_role_id(settings)
        if unverified_role_id:
            url = DISCORD_GUILD_ROLE.format(guild_id=settings.discord_guild_id, user_id=user_id, role_id=unverified_role_id)
            response = await client.put(url, headers=headers)
            if response.status_code != 204:
                response.raise_for_status()
    return True


async def discord_member_roles(settings: Settings, user_id: str) -> list[str] | None:
    """Fetch authoritative guild roles for server-side authorization."""
    if not settings.discord_bot_token:
        return None
    url = f"https://discord.com/api/v10/guilds/{settings.discord_guild_id}/members/{user_id}"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url, headers={"Authorization": f"Bot {settings.discord_bot_token}"})
        if response.status_code == 404:
            return []
        response.raise_for_status()
        return [str(role_id) for role_id in response.json().get("roles", [])]


async def discord_guild_roles(settings: Settings) -> list[dict]:
    """Return the guild role catalog for the secured Staff Admin integration view."""
    if not settings.discord_bot_token:
        return []
    cached=_guild_role_cache.get(settings.discord_guild_id)
    if cached and cached[0]>monotonic(): return cached[1]
    url = f"https://discord.com/api/v10/guilds/{settings.discord_guild_id}/roles"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url, headers={"Authorization": f"Bot {settings.discord_bot_token}"})
        response.raise_for_status()
        roles=sorted(response.json(), key=lambda role: int(role.get("position", 0)), reverse=True)
        _guild_role_cache[settings.discord_guild_id]=(monotonic()+300,roles)
        return roles


async def discord_scheduled_events(settings: Settings) -> list[dict]:
    if not settings.discord_bot_token:
        return []
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            DISCORD_GUILD_EVENTS.format(guild_id=settings.discord_guild_id),
            headers={"Authorization": f"Bot {settings.discord_bot_token}"},
            params={"with_user_count": "true"},
        )
        response.raise_for_status()
        return response.json()


async def discord_announce_booking(settings: Settings, *, discord_user_id: str, display_name: str, flight_number: str, route: str) -> bool:
    """Post a booking notice through the configured bot without exposing its token."""
    if not settings.discord_bot_token or not settings.discord_booking_channel_id:
        return False
    payload = {
        "allowed_mentions": {"parse": []},
        "embeds": [{
            "title": "New SkyMiles Flight Booking",
            "description": f"**{display_name}** (`{discord_user_id}`) is attending **{flight_number}**.",
            "color": 14096703,
            "fields": [{"name": "Route", "value": route, "inline": True}],
        }],
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            DISCORD_CHANNEL_MESSAGES.format(channel_id=settings.discord_booking_channel_id),
            headers={"Authorization": f"Bot {settings.discord_bot_token}"},
            json=payload,
        )
        response.raise_for_status()
    return True


async def discord_announce_update(settings: Settings, *, title: str, description: str, fields: list[dict] | None = None) -> bool:
    """Send a non-mentioning operational/audit update to the configured log channel."""
    if not settings.discord_bot_token or not settings.discord_log_channel_id:
        return False
    payload={"allowed_mentions":{"parse":[]},"embeds":[{"title":title,"description":description,"color":14096703,"fields":fields or []}]}
    async with httpx.AsyncClient(timeout=15) as client:
        response=await client.post(DISCORD_CHANNEL_MESSAGES.format(channel_id=settings.discord_log_channel_id),headers={"Authorization":f"Bot {settings.discord_bot_token}"},json=payload)
        response.raise_for_status()
    return True


async def discord_custom_emojis(settings: Settings) -> dict[str,str]:
    """Resolve the installed guild emoji set so DMs use real Delta emoji IDs."""
    global _emoji_cache
    if not settings.discord_bot_token: return {}
    if _emoji_cache and _emoji_cache[0]>monotonic(): return _emoji_cache[1]
    async with httpx.AsyncClient(timeout=15) as client:
        response=await client.get(f"https://discord.com/api/v10/guilds/{settings.discord_guild_id}/emojis",headers={"Authorization":f"Bot {settings.discord_bot_token}"})
        response.raise_for_status()
        emojis={item["name"].lower():f"<{'a' if item.get('animated') else ''}:{item['name']}:{item['id']}>" for item in response.json()}
        _emoji_cache=(monotonic()+300,emojis)
        return emojis


async def discord_dm(settings: Settings, user_id: str, content: str) -> None:
    """Open a bot DM channel and deliver one event-driven member notification."""
    if not settings.discord_bot_token: raise RuntimeError("Discord bot token is not configured")
    headers={"Authorization":f"Bot {settings.discord_bot_token}"}
    async with httpx.AsyncClient(timeout=15) as client:
        channel=(await client.post("https://discord.com/api/v10/users/@me/channels",headers=headers,json={"recipient_id":user_id})).raise_for_status().json()
        (await client.post(DISCORD_CHANNEL_MESSAGES.format(channel_id=channel["id"]),headers=headers,json={"content":content[:2000],"allowed_mentions":{"parse":[]}})).raise_for_status()

async def discord_custom_emoji_assets(settings: Settings) -> dict[str,str]:
    """Return browser-safe CDN URLs for the installed custom emojis."""
    emojis=await discord_custom_emojis(settings); assets={}
    for name,markup in emojis.items():
        parts=markup.rstrip(">").split(":")
        if len(parts)>=3: assets[name]=f"https://cdn.discordapp.com/emojis/{parts[-1]}.{'gif' if markup.startswith('<a:') else 'png'}?size=48&quality=lossless"
    return assets
