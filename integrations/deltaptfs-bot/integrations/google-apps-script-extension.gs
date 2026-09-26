/*
 * Merge these functions into deltaptfs-bot/integrations/google-apps-script.gs.
 * Call handleWebsiteAction_(action, payload, eventId) from the existing,
 * already-secret-validated doPost switch. Do not add a second doPost handler.
 */
function handleWebsiteAction_(action, payload, eventId) {
  if (['register_member', 'update_member', 'record_transaction'].indexOf(action) === -1) {
    throw new Error('Unsupported website action');
  }
  if (!eventId || !payload || !payload.skymiles_number) throw new Error('Missing website event fields');
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    if (action === 'register_member' || action === 'update_member') {
      return upsertWebsiteMember_(payload, eventId);
    }
    return upsertWebsiteTransaction_(payload, eventId);
  } finally {
    lock.releaseLock();
  }
}

function sheetWithHeaders_(name, headers) {
  var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = spreadsheet.getSheetByName(name) || spreadsheet.insertSheet(name);
  if (sheet.getLastRow() === 0) sheet.appendRow(headers);
  var existing = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  headers.forEach(function(header) {
    if (existing.indexOf(header) === -1) { sheet.getRange(1, sheet.getLastColumn() + 1).setValue(header); existing.push(header); }
  });
  return {sheet: sheet, headers: existing};
}

function rowObject_(headers, values) {
  var object = {};
  headers.forEach(function(header, index) { object[header] = values[index]; });
  return object;
}

function findRow_(sheet, headers, header, value) {
  var column = headers.indexOf(header) + 1;
  if (!column || sheet.getLastRow() < 2) return 0;
  var match = sheet.getRange(2, column, sheet.getLastRow() - 1, 1).createTextFinder(String(value)).matchEntireCell(true).findNext();
  return match ? match.getRow() : 0;
}

function writeObject_(sheet, headers, row, object) {
  var values = headers.map(function(header) { return Object.prototype.hasOwnProperty.call(object, header) ? object[header] : ''; });
  if (row) sheet.getRange(row, 1, 1, headers.length).setValues([values]);
  else sheet.appendRow(values);
}

function upsertWebsiteMember_(p, eventId) {
  var columns = ['Timestamp','SkyMiles Member ID / SkyMiles Number','Discord User ID','Discord Username','Roblox User ID','Roblox Username','RP Name','Membership Tier','Registration Status','Registered By Discord ID','Registered By Name','Source','Notes','Website Event ID'];
  var target = sheetWithHeaders_('Registration Logs', columns);
  var row = findRow_(target.sheet, target.headers, 'SkyMiles Member ID / SkyMiles Number', p.skymiles_number);
  var values = {
    'Timestamp': p.timestamp, 'SkyMiles Member ID / SkyMiles Number': p.skymiles_number,
    'Discord User ID': p.discord_user_id, 'Discord Username': p.discord_username,
    'Roblox User ID': p.roblox_user_id, 'Roblox Username': p.roblox_username,
    'RP Name': p.rp_name, 'Membership Tier': p.membership_tier,
    'Registration Status': p.registration_status, 'Registered By Discord ID': p.registered_by_discord_id,
    'Registered By Name': p.registered_by_name, 'Source': 'Website', 'Notes': p.notes || '',
    'Website Event ID': eventId
  };
  var duplicate = row && rowObject_(target.headers, target.sheet.getRange(row,1,1,target.headers.length).getValues()[0])['Website Event ID'] === eventId;
  writeObject_(target.sheet, target.headers, row, values);
  return {status: duplicate ? 'duplicate' : 'ok'};
}

function upsertWebsiteTransaction_(p, eventId) {
  var columns = ['Timestamp','SkyMiles Member ID','Discord User ID','Display Name','Miles Change','Balance After','Flight / Event ID','Reason','Awarded By Discord ID','Awarded By Name','Entry Type','Notes','Website Transaction ID','Website Event ID'];
  var target = sheetWithHeaders_('Mileage Ledger', columns);
  var row = findRow_(target.sheet, target.headers, 'Website Transaction ID', p.transaction_id);
  var values = {
    'Timestamp': p.timestamp, 'SkyMiles Member ID': p.skymiles_number,
    'Discord User ID': p.discord_user_id, 'Display Name': p.display_name,
    'Miles Change': p.miles_change, 'Balance After': p.balance_after,
    'Flight / Event ID': p.flight_or_event_id, 'Reason': p.reason,
    'Awarded By Discord ID': p.awarded_by_discord_id, 'Awarded By Name': p.awarded_by_name,
    'Entry Type': p.entry_type, 'Notes': p.notes || '',
    'Website Transaction ID': p.transaction_id, 'Website Event ID': eventId
  };
  var duplicate = row > 0;
  writeObject_(target.sheet, target.headers, row, values);
  return {status: duplicate ? 'duplicate' : 'ok'};
}
