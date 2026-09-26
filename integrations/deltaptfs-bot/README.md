# Delta Main Bot integration package

This directory is a reviewable integration package for the separate private
`DeltaPTFS/deltaptfs-bot` repository. The execution environment could not clone
that repository (GitHub returned HTTP 403), so these files are deliberately not
presented as already installed in the bot.

## Bot wiring

1. Copy `src/website-sync.js` into the bot's `src/` directory.
2. Copy the small `src/sheets-website-sync.js` adapter and use
   `createSheetWebsiteSync(existingPostHelper)` from the existing `src/sheets.js`.
   The helper must continue using the existing `GOOGLE_SHEETS_WEBHOOK_URL` and
   `GOOGLE_SHEETS_WEBHOOK_SECRET`, posting:

   ```json
   {"action":"record_transaction","eventId":"stable UUID","payload":{}}
   ```

   The action is `event.event_type`. Do not update a website member's balance
   inside the bot; this path only mirrors an already-committed website event.
3. Mount `createWebsiteSyncHandler({ syncWebsiteEvent })` at
   `POST /internal/website-sync`. Configure the framework to preserve the exact
   raw request bytes for HMAC verification. Apply the bot's normal request-size
   limit and HTTPS proxy configuration.
4. Set `WEBSITE_SYNC_SECRET` to the same random 32+ character secret used for
   the website's `DELTA_BOT_INTERNAL_SECRET`.
5. Merge `integrations/google-apps-script-extension.gs` into the existing Apps
   Script and add these cases to its existing authenticated `doPost` switch:

   ```javascript
   case 'register_member':
   case 'update_member':
   case 'record_transaction':
     result = handleWebsiteAction_(body.action, body.payload, body.eventId);
     break;
   ```

The supplied Apps Script upserts Registration Logs by SkyMiles number and the
Mileage Ledger by website transaction ID. Replays therefore backfill missing
rows without duplicating them. Existing `balance`, `leaderboard`, and `award`
branches should remain untouched.

## Authentication contract

The website sends a canonical JSON body with `X-Website-Timestamp` and
`X-Website-Signature: sha256=<hex>`. The signature is HMAC-SHA256 over
`<timestamp>.<exact raw body>`. The handler rejects timestamps older than five
minutes, invalid signatures, unsupported actions, malformed identity values,
unsafe mile values, and negative resulting balances.

The bot should expose this endpoint only through HTTPS. It must not log either
shared secret or full authenticated request headers.

## Vercel scheduler and Discord Gateway ownership

The Vercel web function intentionally does not open a Discord Gateway or run
infinite asyncio loops. Keep the existing always-on Delta Main Bot responsible
for guild member joins, `/skymiles-add`, `/create-button`, and other gateway
listeners. Every 15 minutes, have the bot call the website's bounded maintenance
endpoint:

```http
GET https://YOUR-VERCEL-DOMAIN/api/cron/maintenance
Authorization: Bearer YOUR_CRON_SECRET
```

Use the same `CRON_SECRET` in the Vercel website environment and the bot's
private environment. A failed maintenance call must be logged and retried, but
must never modify bot-side or Sheet balances independently; PostgreSQL remains
authoritative.
