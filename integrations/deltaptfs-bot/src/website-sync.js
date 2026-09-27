/*
 * Portable Delta Main Bot website-sync handler.
 *
 * Copy this file into deltaptfs-bot/src after reviewing that repository's
 * server framework. It intentionally accepts the existing sheet bridge as a
 * dependency instead of creating a second Google Sheets implementation.
 */
const crypto = require('node:crypto');

const TYPES = new Set(['register_member', 'update_member', 'record_transaction']);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SKYMILES = /^SM-\d{8}$/;

function requireString(value, name, max = 255) {
  if (typeof value !== 'string' || !value.trim() || value.length > max) {
    throw new TypeError(`${name} must be a non-empty string of at most ${max} characters`);
  }
  return value;
}

function validateEvent(event) {
  if (!event || typeof event !== 'object' || !UUID.test(event.event_id || '')) throw new TypeError('Invalid event_id');
  if (!TYPES.has(event.event_type)) throw new TypeError('Invalid event_type');
  const payload = event.payload;
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw new TypeError('Invalid payload');
  requireString(payload.skymiles_number, 'skymiles_number', 16);
  if (!SKYMILES.test(payload.skymiles_number)) throw new TypeError('Invalid SkyMiles number');
  requireString(payload.discord_user_id, 'discord_user_id', 32);
  if (!/^\d{15,22}$/.test(payload.discord_user_id)) throw new TypeError('Invalid Discord user ID');
  if (event.event_type === 'record_transaction') {
    if (!Number.isSafeInteger(payload.transaction_id) || payload.transaction_id < 1) throw new TypeError('Invalid transaction ID');
    if (!Number.isSafeInteger(payload.miles_change) || Math.abs(payload.miles_change) > 1000000) throw new TypeError('Invalid miles change');
    if (!Number.isSafeInteger(payload.balance_after) || payload.balance_after < 0 || payload.balance_after > 1000000000000) throw new TypeError('Invalid balance');
    requireString(payload.entry_type, 'entry_type', 50);
    requireString(payload.reason, 'reason', 255);
  } else {
    requireString(payload.roblox_user_id, 'roblox_user_id', 32);
    if (!/^\d{1,32}$/.test(payload.roblox_user_id)) throw new TypeError('Invalid Roblox user ID');
    requireString(payload.discord_username, 'discord_username', 64);
    requireString(payload.roblox_username, 'roblox_username', 64);
    requireString(payload.registration_status, 'registration_status', 32);
    requireString(payload.membership_tier, 'membership_tier', 64);
  }
  return event;
}

function verifySignature(rawBody, headers, secret, nowSeconds = Math.floor(Date.now() / 1000)) {
  if (!secret || secret.length < 32) throw new Error('WEBSITE_SYNC_SECRET must contain at least 32 characters');
  const timestampText = headers['x-website-timestamp'];
  const supplied = (headers['x-website-signature'] || '').replace(/^sha256=/, '');
  const timestamp = Number(timestampText);
  if (!Number.isInteger(timestamp) || Math.abs(nowSeconds - timestamp) > 300) return false;
  if (!/^[0-9a-f]{64}$/i.test(supplied)) return false;
  const expected = crypto.createHmac('sha256', secret).update(`${timestampText}.`).update(rawBody).digest('hex');
  return crypto.timingSafeEqual(Buffer.from(expected, 'hex'), Buffer.from(supplied, 'hex'));
}

function createWebsiteSyncHandler({ syncWebsiteEvent, logger = console, secret = process.env.WEBSITE_SYNC_SECRET }) {
  if (typeof syncWebsiteEvent !== 'function') throw new TypeError('syncWebsiteEvent must use the existing src/sheets.js bridge');
  return async function websiteSyncHandler(req, res) {
    try {
      const rawBody = Buffer.isBuffer(req.body) ? req.body : Buffer.from(req.rawBody || JSON.stringify(req.body || {}));
      if (!verifySignature(rawBody, req.headers, secret)) {
        logger.warn('website sheet sync rejected: invalid signature');
        return res.status(401).json({ status: 'rejected' });
      }
      const event = validateEvent(JSON.parse(rawBody.toString('utf8')));
      const outcome = await syncWebsiteEvent(event); // extend existing src/sheets.js; do not mutate bot balances here
      const duplicate = outcome && outcome.status === 'duplicate';
      logger.info(`${duplicate ? 'duplicate website event ignored' : 'website sheet sync succeeded'} event_id=${event.event_id}`);
      return res.status(duplicate ? 409 : 200).json({ status: duplicate ? 'duplicate' : 'ok', event_id: event.event_id });
    } catch (error) {
      logger.error(`website sheet sync failed: ${error.message}`);
      return res.status(error instanceof TypeError || error instanceof SyntaxError ? 422 : 502).json({ status: 'failed' });
    }
  };
}

module.exports = { createWebsiteSyncHandler, validateEvent, verifySignature };
