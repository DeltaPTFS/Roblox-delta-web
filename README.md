# Delta SkyMiles | Roblox

An **unofficial** loyalty portal for a private Roblox aviation roleplay community. It is not affiliated with or operated by Delta Air Lines, Inc. Members authenticate only on Roblox and Discord's official pages; this application never accepts Roblox, Discord, or real-world Delta credentials.

## Structure

- `website/app`: FastAPI routes, security, OAuth clients, SQLAlchemy models and business logic.
- `website/templates` / `website/static`: responsive Jinja interface and assets.
- `migrations`: Alembic database schema.
- `tests`: smoke and access-control tests.
- `render.yaml`: Render web service and PostgreSQL blueprint.

The website is isolated under `website/` so an existing or future Discord bot can share PostgreSQL without coupling its runtime to the web process.

## Install and run locally

Python 3.12 is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# Configure .env, then:
alembic upgrade head
uvicorn website.app.main:app --reload
```

Visit `http://localhost:8000`. The health check is `GET /health`. Run tests with `pytest`.

## Database and migrations

Create a PostgreSQL database and set `DATABASE_URL` to its SQLAlchemy psycopg URL (a Render `postgres://` URL is normalized automatically). Run `alembic upgrade head` during each deployment. The schema enforces unique permanent Roblox IDs, Discord IDs, and SkyMiles numbers. Miles, MQP, segment requirements, descriptions, and tier benefits live in `tier_config`, rather than being scattered through application code. Atomic row locks protect miles adjustments and redemptions.

Generate later migrations with `alembic revision --autogenerate -m "description"`; inspect generated SQL before applying it. The Discord bot may eventually read these same tables using a separate least-privilege database user.

## Environment variables

Copy `.env.example`; never commit `.env` or provider secrets.

- `APP_URL`, `DATABASE_URL`, and a cryptographically random 32+ character `SESSION_SECRET`.
- `ROBLOX_CLIENT_ID`, `ROBLOX_CLIENT_SECRET`, `ROBLOX_REDIRECT_URI`, `ROBLOX_GROUP_ID`, `ROBLOX_GROUP_URL`.
- `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_REDIRECT_URI`, `DISCORD_GUILD_ID`, `DISCORD_INVITE_URL`.
- `STAFF_ROBLOX_MIN_RANK`, `ADMIN_ROBLOX_MIN_RANK`, comma-separated `OWNER_ROBLOX_USER_IDS`, `STAFF_DISCORD_ROLE_IDS`, and `ADMIN_DISCORD_ROLE_IDS`.
- Optional `WELCOME_BONUS_MILES`; `COOKIE_SECURE=true` is required in production. Local password login remains disabled by default.

The checked-in public community defaults target Roblox group `6661826`, Discord guild `1538738611988467782`, staff rank `241`, admin rank `255`, and a 150-mile welcome bonus. Replace the `example.onrender.com` callback hostname in both Render and the provider dashboard with the service's real Render hostname before deployment. Provider client IDs, client secrets, session secrets, and database credentials must still be supplied only through Render's Environment page.

## Roblox OAuth and community verification

Create an OAuth 2.0 application in Roblox Creator Hub. Configure the exact callback `https://YOUR_HOST/auth/roblox/callback` and request only `openid profile`. Add its client ID/secret and the numeric community/group ID to Render. The application uses authorization code + PKCE, validates one-time server-session state, exchanges the code server-side at Roblox's OAuth endpoint, and obtains identity from `userinfo`. It then checks the OAuth-derived permanent user ID against Roblox's group roles API and records the server-returned group role/rank. A browser-provided user ID is never accepted.

For development register `http://localhost:8000/auth/roblox/callback` as a separate allowed redirect. Redirect URIs must match exactly. Confirm current provider behavior against the [official Roblox OAuth documentation](https://create.roblox.com/docs/cloud/auth/oauth2-reference) before launch or when upgrading.

## Discord OAuth and server verification

Create an application in Discord Developer Portal. Add `https://YOUR_HOST/auth/discord/callback`, then configure client credentials and the guild ID. The flow requests `identify guilds.members.read`, exchanges authorization codes on the server, and calls the current-user and current-user-guild-member endpoints. Discord's authenticated permanent ID is linked only after Roblox verification and guild membership succeed. The global display name becomes the visible SkyMiles name. See the [official Discord OAuth documentation](https://discord.com/developers/docs/topics/oauth2) and [Get Current User Guild Member documentation](https://discord.com/developers/docs/resources/user#get-current-user-guild-member).

## Admin configuration and security

Permissions are recomputed server-side from stored, provider-verified Roblox rank and Discord role IDs on every admin request. `MEMBER`, `STAFF`, `ADMIN`, and `OWNER` form an increasing hierarchy. Never grant permissions based on frontend flags. Staff miles changes require CSRF, a reason, rate limiting, a database transaction, a transaction row, and immutable audit row with security metadata. Admin/owner expansion points are represented in the model and authorization system; production operators should add UI workflows only with matching server-side checks and audit writes.

Sessions use opaque random IDs with state stored in PostgreSQL. Cookies are `HttpOnly`, `SameSite=Lax`, secure in production, expire after one day, and are deleted from the database at logout. OAuth state/verifiers stay server-side and tokens are never put in local storage. Put the service behind Render TLS, rotate provider secrets, restrict database access, and configure log retention/alerting.

## Render deployment

1. Create a Blueprint from `render.yaml`, or a Python web service plus PostgreSQL.
2. Build command: `pip install -r requirements.txt && alembic upgrade head`.
3. Start command: `uvicorn website.app.main:app --host 0.0.0.0 --port $PORT`.
4. Health path: `/health`.
5. Add every secret/config value listed above. Never use localhost callback URLs in production.
6. Register exact production callbacks with both providers and set `COOKIE_SECURE=true`.

## Troubleshooting

- **OAuth state validation failed:** use one hostname throughout, enable HTTPS, do not open callbacks directly, and check cookie/proxy configuration. Restart the flow rather than reusing a callback URL.
- **Redirect mismatch:** compare scheme, hostname, path, and trailing slash character-for-character in provider settings and `.env`.
- **Roblox group rejection:** confirm `ROBLOX_GROUP_ID`, confirm the authorized account is a current member, and verify Roblox group/thumbnail API availability. No account is created before this succeeds.
- **Discord guild rejection:** confirm `DISCORD_GUILD_ID`, membership, and the `guilds.members.read` scope. Reauthorize after changing scopes.
- **403 on staff tools:** refresh provider information/re-authenticate, check thresholds and comma-separated IDs, and verify that ranks/roles come from the configured group/guild.
- **Database errors:** verify the PostgreSQL URL, connectivity, and that `alembic current` reports `0001`.
- **Provider changes:** consult current official documentation, update endpoints/scopes deliberately, and rerun OAuth integration tests in a staging application before production.

## Pre-launch acceptance checks

Use separate test accounts to verify: new-member enrollment and welcome bonus; returning Roblox ID recognition; non-group denial without user creation; wrong-guild denial; duplicate Discord/Roblox prevention; staff adjustment transaction plus audit; direct member request to `/admin` returning 403; reward balance failure and atomic successful redemption; suspension denial; logout/session expiry; responsive mobile/desktop rendering; and branded 404/500 behavior.
