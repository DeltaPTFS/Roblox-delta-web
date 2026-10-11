# Delta Air Lines · Unified Roblox Roleplay Website

This project is the **Delta Air Lines** public roleplay website. Technical repository names may still contain "ptfs" for compatibility. It uses only `DeltaPTFS/Roblox-delta-web` and `DeltaPTFS/deltaptfs-bot`; do **not** connect the separate `delta-bot` repository.

## Pages and access

| Path | Description | Login |
| --- | --- | --- |
| `/` | Public, vertically scrolling Delta Air Lines homepage and community gallery | Public |
| `/login` | Existing Roblox + Discord enrollment and login | Public |
| `/dashboard`, `/miles`, `/trips`, `/flights` | Unchanged SkyMiles features, rewards and flight bookings | Existing SkyMiles account |
| `/forms` | Published form directory; staff can see drafts/closed forms | Discord account in either approved server |
| `/forms/new` | Drag-free question editor, reorder, draft/publish/close, server-specific role visibility | Staff/leadership roles in either guild |
| `/forms/{slug}` | Fill out a published form; optional `?flight=ID` | Discord-only login is enough; no SkyMiles account |
| `/forms/{slug}/responses` | Responses and associated flight IDs | Staff/leadership roles |
| `/admin`, `/owner` | Existing protected SkyMiles admin panels | Existing SkyMiles admin accounts |

The default *Flight Crew Fillout* form is created when the first flight is hosted using the bot or the existing web admin flight creation tool. Staff can edit its questions and set eligible Discord roles. Each hosted flight receives a unique link of the form `/forms/flight-crew-fillout?flight=123`. Replies are kept in PostgreSQL and queued for Google Sheets.

Authentication uses Discord OAuth state + PKCE, and every form access checks current Discord server roles via the bot API. A Discord account **does not** get an automatic SkyMiles registration. Role-specific form restrictions apply to all listed and direct-link form access. A form with no selected roles is open to authenticated members in either configured server.

## Deployment variables (website / Render / Vercel)

Keep all secrets in host environment variables. Do not commit any token to git.

```env
APP_URL=https://YOUR-WEBSITE-HOST
DATABASE_URL=postgresql+psycopg://...
SESSION_SECRET=<32+ random characters>
DISCORD_CLIENT_ID=<application id>
DISCORD_CLIENT_SECRET=<OAuth secret>
DISCORD_REDIRECT_URI=https://YOUR-WEBSITE-HOST/auth/discord/callback
DISCORD_BOT_TOKEN=<Delta Air Lines bot token authorized in both Discord guilds>
DISCORD_GUILD_ID=<Delta Air Lines Discord server ID>
DISCORD_CREW_GUILD_ID=<Delta Crew Discord server ID>
DISCORD_INVITE_URL=https://discord.gg/YOUR-INVITE
OWNER_DISCORD_ROLE_IDS=<Air Lines owner role ID CSV>
ADMIN_DISCORD_ROLE_IDS=<Air Lines admin role ID CSV>
STAFF_DISCORD_ROLE_IDS=<Air Lines staff role ID CSV>
CREW_OWNER_ROLE_IDS=<Crew owner role ID CSV>
CREW_ADMIN_ROLE_IDS=<Crew admin role ID CSV>
CREW_STAFF_ROLE_IDS=<Crew staff role ID CSV>
DELTA_FLIGHT_API_SECRET=<another 32+ random character shared secret>
# Website outbox -> deltaptfs-bot -> Google Apps Script
DELTA_BOT_INTERNAL_URL=https://YOUR-BOT-HOST
DELTA_BOT_INTERNAL_SECRET=<same as bot WEBSITE_SYNC_SECRET>
```

Keep all **existing Roblox OAuth and SkyMiles** env variables as configured. The Discord OAuth redirect does not change. The Delta bot must be present in both Discord servers with permission to **View Members**, **Guild Members Intent**, **Read Server Roles** and other existing required permissions.

### Data migrations

The new Alembic migration is `0012_community_forms.py`. Run `alembic upgrade head` against the website's production PostgreSQL database as part of the release process **before** the newly deployed app starts serving. For Vercel, do not depend on transient in-process schema creation. Keep Vercel maintenance Cron configured for existing outbox delivery and flight reminders.

### Bot integration

Deploy the corresponding `feat/unified-community-forms-flights` branch from `DeltaPTFS/deltaptfs-bot` alongside the website:

- `DELTA_WEBSITE_URL`: exact website origin, HTTPS.
- `DELTA_FLIGHT_API_SECRET`: matches the website variable of the same name.
- `WEBSITE_SYNC_SECRET`: matches website `DELTA_BOT_INTERNAL_SECRET`.
- `DELTA_CREW_GUILD_ID`: the second Discord server ID.
- `GOOGLE_SHEETS_WEBHOOK_URL` / `GOOGLE_SHEETS_WEBHOOK_SECRET`: shared Apps Script deployment and secret.

The bot's `/flight-host` posts the flight to the website and returns its crew fillout URL in the Discord announcement. `/sync-roster` imports the roster of both configured servers; member/role changes also sync live and the bot reconciles every six hours. SkyMiles commands call website PostgreSQL so Sheets cannot silently become a second, conflicting ledger.

### Google Sheets workbook

[Delta Air Lines — Members, Flights & Forms Tracker](https://docs.google.com/spreadsheets/d/1vQF-dzH9Pun-K02GgJ6dbCEuMC9PkyhKbAWavTu-PQg/edit)

The workbook is already created with: **Members**, **Discord Roles**, **Hosted Flights**, **Flight Fillouts**, **Forms**, **Form Responses**, **SkyMiles Ledger**, **Sync Events**.

1. Open the workbook as its owner; choose **Extensions → Apps Script**.
2. Replace the default Apps Script editor code with `deltaptfs-bot/integrations/google-apps-script.gs`.
3. Set **Project Settings → Script Properties → WEBHOOK_SECRET** to a long random string. Add **WEBSITE_URL** to create clickable fillout links in Sheets.
4. Deploy a **Web app** that executes as the sheet owner. Restrict source access as much as the integration supports; the script authenticates every request with `WEBHOOK_SECRET` and a script lock.
5. Copy the resulting **Web app URL** into the bot's `GOOGLE_SHEETS_WEBHOOK_URL` and the same secret into `GOOGLE_SHEETS_WEBHOOK_SECRET`. **Do not** put the secret into website HTML or Discord messages.
6. Set website `DELTA_BOT_INTERNAL_URL` to the bot service origin and ensure its `/internal/website-sync` route is reachable via HTTPS.
7. Deploy bot, then website; run `/sync-roster` in Discord to import existing members and use the existing owner's **Reconcile Google Sheets** tool to enqueue SkyMiles history.

**Important:** The workbook exists now, but its live web-app deployment and cloud environment variables require account authorization. A Google Sheets workbook link by itself does **not** enable programmatic synchronization.

## Photo gallery

Put the seven supplied roleplay screenshots under `website/static/gallery/`. The homepage is prepared for:
`delta-hangar.jpg`, `delta-centennial.jpg`, `delta-terminal.jpg`, `delta-lounge.jpg`, `delta-hq.jpg`, `delta-electric.jpg`, `delta-tail.jpg`.
The page uses a responsive visual fallback when an image has not yet been uploaded. Images should be optimized to modern web sizes before deployment; don't commit unnecessarily large screenshots. The provided asset package may be uploaded into this folder through the GitHub UI.

## Post-deployment checks

1. Anonymous visitor reaches scrolling Delta homepage without redirects.
2. Clicking **SkyMiles** requires existing Roblox/Discord linked registration. Existing accounts and balances remain unchanged.
3. Clicking **Forms** requests Discord login; a Discord-only person in Air Lines or Crew can complete a published public-role form without creating SkyMiles.
4. Someone in neither server sees an invitation to join and is denied form access.
5. Create a new form, add short answer / multiple-choice / checkbox fields, publish, and verify an authorized member sees it.
6. Select one Crew role, confirm someone without it cannot list or open the form; select Air Lines role and confirm either qualified member can open it.
7. Submit form twice with the same submission ID; only one response should be stored.
8. Run `/flight-host`; verify Discord embed includes route, time, aircraft, crew fillout, SkyMiles booking URL and new flight on website.
9. Create a flight from SkyMiles admin; verify the flight and associated form are queued for the same workbook.
10. Run `/sync-roster`; verify both Discord server IDs, names and role IDs in **Discord Roles**, and existing members in **Members**.
11. Run `/skymiles award`; verify website balance changes first, followed by a single immutable Sheets ledger transaction.
12. Re-deliver a completed sync event; **Sync Events** must prevent duplicate rows.
13. Temporarily disable Apps Script; site transactions must continue and the website's outbox should retry on restoration.

## Security notes

The form editor is staff-only on the server; UI-hidden controls alone never confer access. Role IDs are checked against live guild roles. The bot flight API requires an unguessable secret, and website→bot events require a five-minute HMAC signature. The Google Apps Script uses secret authentication, serialized writes and event deduplication. Keep spreadsheet editor permissions limited to trusted staff; it contains Discord identifiers and submitted application details. Never ask users for real names, passwords, or personal airline credentials in roleplay forms.

**Official disclaimer:** This is an independent Roblox roleplay fan community, not Delta Air Lines' corporate website or product.



## October 2026 unified Crew bot release (PR #37)

This release adds the **third** repository `DeltaPTFS/Delta-crew-bot` while preserving the existing `deltaptfs-bot`. There is no integration with `delta-bot`.

### Roles (two independent guilds)

| Main Air Lines server | Role ID | Crew server | Role ID |
| --- | --- | --- | --- |
| Founders | 1539005297417519205 | BOD | 1554665018690248714 |
| Leadership | 1539005030189891684 | Leadership | 1554666461644197988 |
| Human Resources | 1539016506216812567 | Human Resources | 1554666482988875788 |
| Delta Crew | 1539968936681148456 | Crew | 1554669633573888010 |
| SkyMiles | 1539005061609422849 | Authentication needed | 1554671178893885480 |
| Customers | 1539005068916031518 | — | — |

The crew server ID is still required for live role reads. Website forms can be restricted to any combination of actual roles from either guild in the form editor. Founder/BOD, Leadership and HR can manage forms. Customers and normal Crew can see only published forms whose role restrictions they satisfy.

### Gallery photo fix

The main homepage now uses permanent paths like `/gallery/media/delta-hangar` rather than linking to nonexistent JPGs in the repository. Staff can visit **`/gallery/manage`** from the website menu to upload all seven photos using the supplied `Delta_Air_Lines_PNG_Website_Gallery.zip` in a single action: **Import All Photos**. Images are validated (PNG/JPEG/WebP, max 3 MB each), then stored in PostgreSQL; no direct GitHub manipulation is required. Optionally upload the "Skipping Class" image separately into the **Flight format announcement image** slot, `flight-promo`. It then appears below main bot `/format` announcements as a Discord attachment.

The gallery images are **not physically uploaded to the hosted website** until an authorized staff member imports the provided ZIP. Do not advertise the pictures as installed before doing so.

### Discord OAuth auto-join

Discord login requests `guilds.join` together with `identify` and `guilds.members.read`. A user who grants that permission can be added to the **main** Delta Air Lines Discord guild via Discord's official Add Guild Member endpoint. This feature requires `DISCORD_BOT_TOKEN`, the main guild ID and the bot's presence in the guild. Discord can reject joins (e.g. bans or screening) and those users see the invitation instructions. The separate Crew guild is **never joined silently**, and no privileged roles are auto-granted.

### Crew bot service variables

Set the following **website** environment variables, in addition to the existing SkyMiles ones:

```env
DISCORD_INVITE_URL=https://discord.gg/u8GJF2br2M
DISCORD_GUILD_ID=1538738611988467782
DISCORD_CREW_GUILD_ID=<need Crew server ID>
DISCORD_CREW_BOT_TOKEN=<Crew bot's own Discord token>
CREW_OWNER_ROLE_IDS=1554665018690248714
CREW_ADMIN_ROLE_IDS=1554666461644197988
CREW_STAFF_ROLE_IDS=1554666482988875788
FORMS_STAFF_DISCORD_ROLE_IDS=1539016506216812567
DELTA_CREW_API_SECRET=<random 32+ chars; same as Crew RavenHost service>
DELTA_FLIGHT_API_SECRET=<different random 32+ chars; same as Main bot>
```

**Crew RavenHost** app should run the `Delta-crew-bot` repo via `npm install`, `npm run build`, `npm start`. Set `DISCORD_TOKEN`, `DELTA_CREW_GUILD_ID`, `DELTA_WEBSITE_URL`, `DELTA_CREW_API_SECRET` and Crew announcement/channel IDs. Use a separate app/token from main bot. The Crew bot polls for pending form/flight events every 30 seconds and only ACKs after posting; notifications for restricted forms/responses go to HR-only channels.

**Main RavenHost** app continues with `deltaptfs-bot`. `/format` now offers 8 original Delta flight notices, using Discord native timestamp markup and a Publish/Cancel preview. `/flight-host` responds with the numeric website flight ID to use with `/format`. The two services share the same flight database; they do not share Discord tokens.

### Release order

1. Run `alembic upgrade head` to apply migrations **0013 Crew notifications** and **0014 Site gallery** (plus any previously pending 0012 Forms migration). Existing SkyMiles tables must be preserved.
2. Configure both bot tokens, Crew server ID, channel IDs, and random API secrets as environment variables.
3. Deploy web, then main bot, then new Crew bot. Verify `/health`, `/crew action:status`, `/format` preview.
4. Import seven website screenshots through **`/gallery/manage`**; import the flight promo separately.
5. Validate form visibility for a user in both servers and one who has only a Customer/Crew role; confirm private HR-only responses and Google Sheets retry behavior.

Never paste Discord bot tokens or API shared secrets into chats or GitHub.
