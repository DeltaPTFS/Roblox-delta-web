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

Python 3.13 is recommended and Render is pinned through `.python-version` to avoid silently adopting a new major Python runtime.

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

Create a PostgreSQL database and set `DATABASE_URL` to its Render or SQLAlchemy PostgreSQL URL. Both Render-style `postgres://` and `postgresql://` URLs are normalized to SQLAlchemy's `postgresql+psycopg://` dialect so the installed psycopg 3 driver is always used. Run `alembic upgrade head` during each deployment. The schema enforces unique permanent Roblox IDs, Discord IDs, and SkyMiles numbers. Miles, MQP, segment requirements, descriptions, and tier benefits live in `tier_config`, rather than being scattered through application code. Atomic row locks protect miles adjustments and redemptions.

Generate later migrations with `alembic revision --autogenerate -m "description"`; inspect generated SQL before applying it. The Discord bot may eventually read these same tables using a separate least-privilege database user.

## Environment variables

Copy `.env.example`; never commit `.env` or provider secrets.

- `APP_URL`, `DATABASE_URL`, and a cryptographically random 32+ character `SESSION_SECRET`.
- `ROBLOX_CLIENT_ID`, `ROBLOX_CLIENT_SECRET`, `ROBLOX_REDIRECT_URI`, `ROBLOX_GROUP_ID`, `ROBLOX_GROUP_URL`.
- `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_REDIRECT_URI`, `DISCORD_GUILD_ID`, `DISCORD_INVITE_URL`.
- Secret `DISCORD_BOT_TOKEN` enables scheduled-event flight synchronization, authoritative staff-role checks, server-side SkyMiles/Medallion role assignment, and booking announcements. The bot must be in the configured guild with **Manage Roles**, and its highest role must sit above every SkyMiles/Medallion role.
- `DISCORD_BOOKING_CHANNEL_ID` selects the staff channel where the bot posts confirmed flight bookings. Give the bot **View Channel**, **Send Messages**, and **Embed Links** in that channel.
- `DISCORD_SKYMILES_CHANNEL_URL` links members directly to the community SkyMiles information channel (`1541156846579089519`).
- `DISCORD_LOG_CHANNEL_ID=1539005101941850274` receives staff adjustments, qualification changes, flight updates, event synchronization, and ownership access actions through the bot.
- `DISCORD_UNVERIFIED_ROLE_ID` identifies the role assigned immediately when a person joins the server. If it is blank, the bot uses the exact guild role name `Unverified`. Enable **Server Members Intent** in the Discord Developer Portal and keep the bot role above Unverified. Successful SkyMiles verification removes Unverified; leaving the program restores it.
- `DISCORD_MEMBER_ROLE_ID` is retained for every member. Configure the Silver, Gold, Platinum, and Diamond role IDs separately; `DISCORD_SILVER_ROLE_ID` is intentionally blank until a Silver role ID is supplied.
- `STAFF_ROBLOX_MIN_RANK`, `ADMIN_ROBLOX_MIN_RANK`, comma-separated `OWNER_ROBLOX_USER_IDS`, `STAFF_DISCORD_ROLE_IDS`, and `ADMIN_DISCORD_ROLE_IDS`.
- Panel access is refreshed from Discord and defaults to Ownership role `1539005297417519205`, Staff Admin roles `1539005030189891684` and `1539005033020919828`, and Staff role `1539968936681148456`. Ownership includes all panels; Staff Admin includes SkyMiles and flights; Staff includes SkyMiles only.
- Optional `WELCOME_BONUS_MILES`; `COOKIE_SECURE=true` is required in production. Local password login remains disabled by default.

The checked-in public community defaults target Roblox group `6661826`, Discord guild `1538738611988467782`, staff rank `241`, admin rank `255`, and a 150-mile welcome bonus. Replace the `example.onrender.com` callback hostname in both Render and the provider dashboard with the service's real Render hostname before deployment. Provider client IDs, client secrets, session secrets, and database credentials must still be supplied only through Render's Environment page.

## Flights and Discord roles

`BOOK A FLIGHT!` shows active Discord scheduled events. Opening the page synchronizes current events when `DISCORD_BOT_TOKEN` is configured; staff can also force a sync and publish scheduled, delayed, cancelled, or completed status from Staff Admin. Members book once per flight and may select only server-computed amenities allowed by their tier. Amenities apply to that booking only. After confirmation, the website uses the bot to post the member and flight information in `DISCORD_BOOKING_CHANNEL_ID`; Discord mention parsing is disabled for safety.

Staff can also create flights directly with a validated flight number, departure and destination airport codes, Eastern departure time, description, and SkyMiles completion reward. Flight completion never awards SkyMiles automatically. Authorized staff review attendance and apply any published reward through the audited Staff Panel. Members can manage, leave, and rebook before departure; leaving clears flight-only amenities and explains applicable refunds.

Staff Admin and Ownership may alternatively paste a Discord scheduled-event link in the flight form. The server verifies that the link belongs to the configured guild, retrieves the event through the bot, and imports its title, start time, description, and location. Ownership can kick sessions, ban or restore non-owner memberships, review member feedback, inspect the guild role connection, and review the latest 200 immutable staff audit records.

Clicking or tapping a Medallion card opens its dedicated details and enrollment page. The server independently checks the published MQP threshold and one-day membership wait before changing status. Successful registration always assigns the base SkyMiles Member role. Successful Medallion enrollment retains that base role, removes other configured Medallion roles, and assigns the selected tier role. Confirmed flight bookings are announced through the configured Discord booking channel.

On every authenticated page load, the server reads the member's authoritative Discord roles. If the permanent SkyMiles Member role or current Medallion role is missing—or a stale managed Medallion role remains—the bot repairs the exact role set and verifies the result with Discord. Temporary Discord outages retain the last verified authorization cache instead of incorrectly deleting panel access; the account menu displays the connection state.

The bot also exposes the guild-scoped `/skymiles-add` command. A linked Staff, Staff Admin, or Ownership member can select a verified Discord member, enter a positive amount and required reason, and update both available and lifetime SkyMiles. The command records the same transaction and immutable audit data as the Staff Panel and returns the confirmed balance privately. Install the application with the `bot` and `applications.commands` scopes so the command can be synchronized.

The guild-scoped `/create-button` command is available to every server member and publishes a safe HTTPS link button with a label, message, optional emoji, and embed color. Each member may publish at most three button messages every ten minutes. Button posts disable mention parsing and are recorded in the website log channel.

The account menu and Profile page display every current Discord server role returned for the authenticated member, using the role names, hierarchy order, and colors from the guild's authoritative role catalog. The catalog is cached for five minutes to limit Discord API traffic; member role IDs themselves are still refreshed for authorization checks.

New members are welcomed by a six-step guided tour with three Gre1 explanations and three Cookie explanations. Each step addresses the signed-in member by their Discord display name and highlights Home, My SkyMiles, Book a Flight, My Trips, Rewards, and Profile. Members who decline or finish can relaunch it at any time from **Start Tutorial** in the profile dropdown.

Member-facing names follow the configured Discord server profile: the server nickname is used first, with the Discord global display name and username only as fallbacks. The bot refreshes the server nickname and server-specific avatar during authenticated navigation, so a renamed server profile is reflected without allowing manual website edits.

The document title, iOS home-screen title, and mobile web-app name use `DAL-roblox.com`. Browsers still display the real secure Render URL in the address bar when it is opened; a page cannot and should not disguise its actual origin. A genuine `dal-roblox.com` address requires registering that domain and connecting it to Render.

## Performance

HTML and larger static responses are compressed with GZip. Static CSS/SVG assets use a one-hour browser cache with a one-day stale-while-revalidate window, normal member pages reuse a verified Discord role result for 30 seconds, and guild role metadata remains cached for five minutes. Administrative actions still force authoritative Discord authorization checks. Expensive full-page background-position and backdrop-filter animations were replaced with lightweight opacity-only fades and are disabled on mobile or when reduced motion is requested.

Medallion cards are full click/tap targets that open a dedicated status page. Status is based only on the centrally configured MQP thresholds: Silver 2,500, Gold 5,000, Platinum 7,500, and Diamond 10,000. Enrollment opens after the member's first complete day, does not deduct SkyMiles or MQP, records status history, and synchronizes the exact Discord role. Members can retain their current status or move upward during the year.

Medallion Status is valid only through the next January 1 at 12:00 AM Eastern Time. The application uses the IANA `America/New_York` timezone, so the instant is correctly treated as EST in January (for example, enrollment on March 3, 2026 expires at January 1, 2027 12:00 AM ET / 05:00 UTC). An hourly server task returns expired members to the base SkyMiles Member tier and removes configured Medallion Discord roles while retaining the base member role.

## Roblox OAuth and community verification

Create an OAuth 2.0 application in Roblox Creator Hub. Configure the exact callback `https://YOUR_HOST/auth/roblox/callback` and request only `openid profile`. Add its client ID/secret and the numeric community/group ID to Render. The application uses authorization code + PKCE, validates one-time server-session state, exchanges the code server-side at Roblox's OAuth endpoint, and obtains identity from `userinfo`. It then checks the OAuth-derived permanent user ID against Roblox's group roles API and records the server-returned group role/rank. A browser-provided user ID is never accepted.

For development register `http://localhost:8000/auth/roblox/callback` as a separate allowed redirect. Redirect URIs must match exactly. Confirm current provider behavior against the [official Roblox OAuth documentation](https://create.roblox.com/docs/cloud/auth/oauth2-reference) before launch or when upgrading.

## Discord OAuth and server verification

Create an application in Discord Developer Portal. Add `https://YOUR_HOST/auth/discord/callback`, then configure client credentials and the guild ID. The flow requests `identify guilds.members.read`, exchanges authorization codes on the server, and calls the current-user and current-user-guild-member endpoints. Discord's authenticated permanent ID is linked only after Roblox verification and guild membership succeed. The global display name becomes the visible SkyMiles name. See the [official Discord OAuth documentation](https://discord.com/developers/docs/topics/oauth2) and [Get Current User Guild Member documentation](https://discord.com/developers/docs/resources/user#get-current-user-guild-member).

## Admin configuration and security

Permissions are recomputed server-side from stored, provider-verified Roblox rank and Discord role IDs on every admin request. `MEMBER`, `STAFF`, `ADMIN`, and `OWNER` form an increasing hierarchy. Never grant permissions based on frontend flags. Staff miles changes require CSRF, a reason, rate limiting, a database transaction, a transaction row, and immutable audit row with security metadata. Admin/owner expansion points are represented in the model and authorization system; production operators should add UI workflows only with matching server-side checks and audit writes.

Sessions use opaque random IDs with state stored in PostgreSQL. Cookies are `HttpOnly`, `SameSite=Lax`, secure in production, expire after one day, and are deleted from the database at logout. OAuth state/verifiers stay server-side and tokens are never put in local storage. Put the service behind Render TLS, rotate provider secrets, restrict database access, and configure log retention/alerting.

Returning members may authenticate with either their linked Roblox or linked Discord account. New memberships remain Roblox-first so the permanent Roblox identity and configured group membership are verified before Discord linking. Display theme is saved on the member record and restored on either login method. Staff navigation is based on verified authorization, and every admin endpoint refreshes Discord guild roles with the bot before enforcing access (falling closed for Discord-role authorization if refresh fails).

The site occasionally shows a two-rating feedback dialog once per session. Ratings and written suggestions are validated server-side and stored for authorized staff review in Staff Admin; they are never posted publicly.

## Render deployment

The Blueprint creates two public services:

- `delta-skymiles-static` is an optional Render Static Site containing a fast, responsive public entry page. It has no secrets and sends login actions to the secure application service.
- `delta-skymiles-roblox` is the required FastAPI web service. OAuth callbacks, sessions, Discord synchronization, PostgreSQL, bookings, balances, and every authenticated feature must run here; a static host cannot execute Python or securely perform these operations.

Set `SKYMILES_BACKEND_URL` on the static service to the public HTTPS address of the FastAPI service. The default is `https://roblox-delta-web.onrender.com`. The static build validates HTTPS, copies its assets into `dist`, and replaces all backend placeholders. OAuth callback URLs must continue pointing to the FastAPI service, not the static site.

1. Create a Blueprint from `render.yaml`, or create both the optional Static Site and the required Python web service plus PostgreSQL.
2. Build command: `pip install -r requirements.txt && alembic upgrade head`.
3. Start command: `uvicorn website.app.main:app --host 0.0.0.0 --port $PORT`.
4. Health path: `/health`.
5. Add every secret/config value listed above. Never use localhost callback URLs in production.
6. Register exact production callbacks with both providers and set `COOKIE_SECURE=true`.

For a manually created Render Static Site, use build command `sh scripts/build-static-site.sh` and publish directory `dist`.

## Vercel Deployment

Vercel discovers the root-level `app.py` through its native, zero-configuration
FastAPI support. That file only imports `website.app.main:app`; it does not
create another application. There is deliberately no catch-all rewrite and no
`api/index.py`, so FastAPI receives the original request path for `/`, OAuth
callbacks, profiles, SkyMiles pages, `/static/*`, and `/health`. The existing
`StaticFiles` mount and Jinja template paths therefore behave exactly as they do
outside Vercel. Keep the project **Root Directory** at the repository root.

### Required Vercel environment variables

Add these for **Production** and for any Preview environment that should boot:

- `APP_URL=https://YOUR-PRODUCTION-DOMAIN`
- `DATABASE_URL` — a PostgreSQL connection string. SQLite is deliberately
  rejected whenever `VERCEL=1`.
- `SESSION_SECRET` — a new random value of at least 32 characters.
- `COOKIE_SECURE=true`
- `ROBLOX_CLIENT_ID`, `ROBLOX_CLIENT_SECRET`, `ROBLOX_GROUP_ID`, and
  `ROBLOX_GROUP_URL`
- `ROBLOX_REDIRECT_URI=https://YOUR-PRODUCTION-DOMAIN/auth/roblox/callback`
- `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_GUILD_ID`, and
  `DISCORD_INVITE_URL`
- `DISCORD_REDIRECT_URI=https://YOUR-PRODUCTION-DOMAIN/auth/discord/callback`
- `DISCORD_BOT_TOKEN` for request-scoped role checks, role updates, scheduled
  event reads, announcements, and DMs. It no longer starts a gateway on Vercel.
- `DISCORD_MEMBER_ROLE_ID`, `DISCORD_SILVER_ROLE_ID`,
  `DISCORD_GOLD_ROLE_ID`, `DISCORD_PLATINUM_ROLE_ID`, and
  `DISCORD_DIAMOND_ROLE_ID`
- `OWNER_DISCORD_ROLE_IDS`, `ADMIN_DISCORD_ROLE_IDS`, and
  `STAFF_DISCORD_ROLE_IDS`
- `STAFF_ROBLOX_MIN_RANK`, `ADMIN_ROBLOX_MIN_RANK`, and
  `OWNER_ROBLOX_USER_IDS`
- `CRON_SECRET` — a separate random 32+ character value used by the maintenance
  endpoint.

Add these when the related feature is enabled:

- `DISCORD_BOOKING_CHANNEL_ID`, `DISCORD_LOG_CHANNEL_ID`,
  `DISCORD_UNVERIFIED_ROLE_ID`, and `DISCORD_SKYMILES_CHANNEL_URL`
- `WELCOME_BONUS_MILES` and `LOCAL_PASSWORD_LOGIN_ENABLED`
- `DELTA_BOT_INTERNAL_URL` and `DELTA_BOT_INTERNAL_SECRET` for the Google Sheets
  outbox bridge. `SHEET_SYNC_INTERVAL_SECONDS` is used only by always-on hosts;
  Vercel processes a bounded outbox batch through scheduled maintenance.

Vercel supplies `VERCEL=1`; do not add or override it. `SERVERLESS_MODE=true`
is only needed when testing serverless behavior outside Vercel. Store all
secrets in **Project Settings → Environment Variables**, never in GitHub.

### Lifespan and background responsibilities

Vercel functions cannot provide a permanent process. In serverless mode the
FastAPI lifespan therefore does **not** run `Base.metadata.create_all`, the
hourly Medallion loop, the 15-minute reminder loop, the Sheets outbox loop, or
the Discord Gateway connection. Normal request-based Discord OAuth, Roblox
OAuth, role synchronization, bookings, panels, templates, and static files are
unchanged.

The always-running Delta Main Bot should own Discord gateway listeners and slash
commands. It should call `GET /api/cron/maintenance` every 15 minutes with:

```text
Authorization: Bearer <CRON_SECRET>
```

That authenticated endpoint performs one bounded, idempotent batch of Medallion
expiration, flight reminders, and Sheets outbox delivery. It is also compatible
with a Vercel Cron invocation because Vercel sends the configured `CRON_SECRET`
as a Bearer authorization value. Notification event keys and outbox IDs prevent
duplicate work when an invocation is retried.

### Safe Alembic migration process

Do **not** put `alembic upgrade head` in a Vercel function or run it during every
request. Do not make it the Vercel Build Command either: concurrent Preview and
Production builds can race. Before promoting a deployment:

1. Back up PostgreSQL and use its direct/non-pooled migration URL if the provider
   supplies separate pooled and direct URLs.
2. From a trusted local machine or a single serialized CI release job, export
   the production `DATABASE_URL` without committing it.
3. Run `alembic current`, review the pending revisions, then run
   `alembic upgrade head` exactly once.
4. Run `alembic current` again and confirm it reports `0011`.
5. Only then promote or redeploy the Vercel Production deployment.

Revision `0011` seeds required tiers and rewards idempotently so a fresh Vercel
database does not depend on application startup side effects.

### Vercel dashboard steps after merge

1. Open Vercel → **Roblox-delta-web** → **Settings → General**.
2. Set **Framework Preset** to **Other** and **Root Directory** to `./`.
3. Leave Build Command and Output Directory overrides disabled. Vercel detects
   the root `app.py` FastAPI application and installs `requirements.txt`; there
   is no Uvicorn Start Command and no catch-all rewrite on Vercel.
4. Open **Settings → Environment Variables**, add the variables above, and make
   sure `DATABASE_URL` is available to Production. Add the OAuth/provider
   secrets to Preview only if Preview deployments are intended to support OAuth.
5. Run the one-time Alembic procedure above against production PostgreSQL.
6. Open **Deployments**, select the deployment created from the merged commit,
   choose **Redeploy**, leave **Use existing Build Cache** off for the first
   migration, and confirm.
7. Visit `https://YOUR-PRODUCTION-DOMAIN/health` and confirm `{"status":"ok"}`.
8. Add the exact Vercel callback URLs to Roblox Creator Hub and Discord Developer
   Portal, then test both login flows. Callback strings must match the Vercel
   variables exactly.
9. Configure the Delta Main Bot scheduler to call the secured maintenance URL,
   then verify reminders and the Sheets outbox from logs.
10. Keep `render.yaml` and the Render service untouched until login, booking,
    role synchronization, maintenance, and PostgreSQL writes are verified on
    Vercel.

## Troubleshooting

- **OAuth state validation failed:** use one hostname throughout, enable HTTPS, do not open callbacks directly, and check cookie/proxy configuration. Restart the flow rather than reusing a callback URL.
- **Redirect mismatch:** compare scheme, hostname, path, and trailing slash character-for-character in provider settings and `.env`.
- **Roblox group rejection:** confirm `ROBLOX_GROUP_ID`, confirm the authorized account is a current member, and verify Roblox group/thumbnail API availability. No account is created before this succeeds.
- **Discord guild rejection:** confirm `DISCORD_GUILD_ID`, membership, and the `guilds.members.read` scope. Reauthorize after changing scopes.
- **403 on staff tools:** refresh provider information/re-authenticate, check thresholds and comma-separated IDs, and verify that ranks/roles come from the configured group/guild.
- **Database errors:** verify the PostgreSQL URL, connectivity, and that `alembic current` reports `0011`.
- **Provider changes:** consult current official documentation, update endpoints/scopes deliberately, and rerun OAuth integration tests in a staging application before production.

## Pre-launch acceptance checks

Use separate test accounts to verify: new-member enrollment and welcome bonus; returning Roblox ID recognition; non-group denial without user creation; wrong-guild denial; duplicate Discord/Roblox prevention; staff adjustment transaction plus audit; direct member request to `/admin` returning 403; reward balance failure and atomic successful redemption; suspension denial; logout/session expiry; responsive mobile/desktop rendering; and branded 404/500 behavior.

## My Trips, refunds, moderation, and Discord DMs

Every reservation receives a unique confirmation number and remains in **My Trips** after completion or cancellation. Flight details use the member's local browser timezone and display **To Be Assigned** rather than raw null values. Cancellations within 24 hours of the exact booking timestamp refund eligible applied SkyMiles; later pre-departure cancellations clearly disclose and forfeit the applied amount.

The bot resolves the guild's installed custom emoji catalog before sending event-driven DMs. Booking, member cancellation/refund, staff flight cancellation, delay, gate, aircraft, schedule, completion, verified no-show, warning, suspension, and ban deliveries are recorded in `notification_logs`, including failed DMs. Unique event keys prevent duplicate notices. A Discord delivery failure never rolls back the website action.

Staff moderation records the member, moderator, required reason, time, and optional related flight. No-shows are never inferred automatically: staff must select a real reservation and confirm the action. Ownership can remove, temporarily restrict, permanently ban, restore, and reverse warnings. Temporary restrictions expire automatically on the member's next authenticated request.

## Qualification persistence and terminal-flight grace period

Staff MQP and segment adjustments use a row lock and an explicit database update. The new totals are flushed, read back, committed with the audit record, displayed in the success notice, and shown beside the member in Staff Admin. This prevents a success message from being shown for an update that did not affect exactly one account.

Cancelled and completed flights remain visible in Flight Operations and the member flight panel for ten minutes after the terminal status update. They are not bookable during this grace period. After ten minutes they leave the active panel and appear in the Staff Admin **Flight Logs** archive; member reservations remain permanently available in **My Trips**.

## Roblox boarding-pass QR codes

Staff Admin must provide an HTTPS `roblox.com` game or share link when creating a flight. The value is validated server-side, saved with the flight, and encoded into a unique booking's boarding-pass QR display. The QR endpoint requires the logged-in member to own the confirmation number, and the generated code contains only the staff-approved Roblox URL. Missing operational assignments are displayed as **To Be Assigned**.

## Delta Main Bot and Google Sheets mirror

### Architecture

The data path is strictly one way:

```text
Roblox-delta-web / PostgreSQL (source of truth)
  -> durable sheet_sync_events outbox
  -> authenticated Delta Main Bot endpoint
  -> existing src/sheets.js bridge
  -> existing Google Apps Script
  -> Registration Logs / Mileage Ledger (mirror)
```

Registration, mileage transactions, tier changes, qualification updates, and
membership-status changes enqueue an immutable event in the same PostgreSQL
transaction as the authoritative change. A background worker sends due events
only after that transaction commits. Google Sheets or bot failures therefore
cannot reject, reverse, or alter a successful website registration or balance
change. Failed events use bounded exponential backoff and retain attempts and
the last error for operational review.

Event IDs are deterministic. Member registration is keyed by internal website
user ID, ledger entries by the permanent PostgreSQL transaction ID, and member
snapshots by their relevant state. The bot verifies an HMAC-SHA256 signature,
timestamp freshness, event type, IDs, SkyMiles number, and numeric bounds before
forwarding an event. The Apps Script upserts `Registration Logs` by SkyMiles
number and `Mileage Ledger` by website transaction ID, so restarts, retries, and
reconciliation do not duplicate rows.

Ownership can use **Reconcile Google Sheets** in the Ownership Panel. It replays
canonical member and ledger snapshots after committing an audit log. Replaying
is intentionally safe and backfills a row removed from a Sheet without using
Sheet values to update PostgreSQL.

### Environment variables

Website service:

- `DELTA_BOT_INTERNAL_URL`: HTTPS base URL of the Delta Main Bot service. The
  website posts to `/internal/website-sync` below this URL.
- `DELTA_BOT_INTERNAL_SECRET`: random shared secret of at least 32 characters.
- `SHEET_SYNC_INTERVAL_SECONDS`: outbox polling interval; defaults to 15.

Delta Main Bot service:

- `WEBSITE_SYNC_SECRET`: exact same value as `DELTA_BOT_INTERNAL_SECRET`.
- Existing `GOOGLE_SHEETS_WEBHOOK_URL` and `GOOGLE_SHEETS_WEBHOOK_SECRET` remain
  the only credentials used between the bot and Apps Script.

Generate the shared secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
Store it only in the two Render services. Never place it in GitHub or Apps
Script source. The bot-side review package is under
`integrations/deltaptfs-bot/`; because this workspace cannot access the private
bot repository, apply and review it there before deployment.

No Raven/Sentry setting is required by this integration. If the bot already
uses Raven or Sentry, keep its existing DSN and configure request scrubbing so
`X-Website-Signature`, `WEBSITE_SYNC_SECRET`, Google webhook secrets, and full
member payloads are never captured. On Render, add the variables above to the
respective **Environment** pages; they are not shared automatically between two
services.

### Exact deployment order

1. Back up PostgreSQL and the Google spreadsheet.
2. Merge the supplied Apps Script extension into the existing
   `integrations/google-apps-script.gs`, preserving the current authenticated
   `doPost`, `balance`, `leaderboard`, and `award` behavior. Deploy a new Apps
   Script web-app version.
3. Extend the bot's existing `src/sheets.js` and mount the authenticated handler
   as described in `integrations/deltaptfs-bot/README.md`. Set
   `WEBSITE_SYNC_SECRET`; retain its current Google webhook variables. Deploy
   the Delta Main Bot and verify a signed staging event.
4. Deploy the website migration with `alembic upgrade head`. This creates only
   the durable `sheet_sync_events` table and does not rewrite members or
   transactions.
5. Set the website's `DELTA_BOT_INTERNAL_URL`,
   `DELTA_BOT_INTERNAL_SECRET`, and optional polling interval, then redeploy.
6. Make one test adjustment, verify PostgreSQL first, then verify the bot log and
   `Mileage Ledger`. Finally run Ownership reconciliation and verify no duplicate
   registration or ledger rows appear.

### Rollback

Unset `DELTA_BOT_INTERNAL_URL` and `DELTA_BOT_INTERNAL_SECRET` (or roll back the
website release) to stop deliveries immediately. Website registration and miles
continue normally because sync is optional. Roll back the bot route and Apps
Script deployment independently; do not delete PostgreSQL transactions. The
`0010` downgrade intentionally retains the outbox for audit and safe later
replay. After repairing the integration, redeploy in the order above and use
Ownership reconciliation. Never import Sheet balances into the website as a
rollback mechanism.
