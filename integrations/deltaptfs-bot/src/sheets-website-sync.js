/* Extension adapter for the bot's existing src/sheets.js transport.
 *
 * Export createSheetWebsiteSync from src/sheets.js after passing its current
 * authenticated Google Apps Script POST helper as postToSheets. This preserves
 * every existing balance/leaderboard/award code path.
 */
function createSheetWebsiteSync(postToSheets) {
  if (typeof postToSheets !== 'function') throw new TypeError('postToSheets is required');
  return async function syncWebsiteEvent(event) {
    const response = await postToSheets({
      action: event.event_type,
      eventId: event.event_id,
      payload: event.payload,
    });
    if (!response || !['ok', 'duplicate'].includes(response.status)) {
      throw new Error('Google Sheets rejected the website sync event');
    }
    return response;
  };
}

module.exports = { createSheetWebsiteSync };
