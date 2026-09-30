/**
 * Paste this into Extensions > Apps Script in the Google Sheet, replacing
 * whatever's in Code.gs. See README.md for full deployment instructions.
 *
 * This exposes the sheet's data as JSON over a plain HTTP GET request, so the
 * GitHub Action can pull it with a simple web request — no Google Cloud
 * project, no service account, no billing.
 *
 * Access control: since this runs unattended (no human logging in), it can't
 * use Google's normal sign-in. Instead it checks a shared secret token,
 * stored in this project's Script Properties (not in this code, so it's
 * never visible to anyone who can just view the script). Set it once via
 * Project Settings (gear icon) -> Script Properties -> Add property ->
 * name "SECRET_TOKEN", value: any long random string you make up.
 *
 * Supports pagination (startRow / numRows) since very large sheets could
 * otherwise risk hitting Apps Script's execution time or response size
 * limits in one call — the Python side already loops through pages
 * automatically, you don't need to think about this.
 */

function doGet(e) {
  var expectedToken = PropertiesService.getScriptProperties().getProperty('SECRET_TOKEN');
  if (!expectedToken) {
    return jsonOutput({ error: 'SECRET_TOKEN is not set in Script Properties. See setup instructions.' });
  }
  if (e.parameter.token !== expectedToken) {
    return jsonOutput({ error: 'Unauthorized' });
  }

  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = e.parameter.sheet ? ss.getSheetByName(e.parameter.sheet) : ss.getSheets()[0];
  if (!sheet) {
    return jsonOutput({ error: 'Sheet tab not found: ' + e.parameter.sheet });
  }

  var lastRow = sheet.getLastRow();
  var lastCol = sheet.getLastColumn();
  var totalDataRows = Math.max(0, lastRow - 1); // minus the header row

  var startDataRow = parseInt(e.parameter.startRow || '1', 10); // 1 = first data row (sheet row 2)
  var pageSize = parseInt(e.parameter.numRows || '50000', 10);

  var headers = lastCol > 0 ? sheet.getRange(1, 1, 1, lastCol).getValues()[0] : [];
  var rows = [];

  if (startDataRow <= totalDataRows) {
    var sheetStartRow = startDataRow + 1; // +1 to skip the header row
    var rowsToFetch = Math.min(pageSize, totalDataRows - startDataRow + 1);
    var values = sheet.getRange(sheetStartRow, 1, rowsToFetch, lastCol).getValues();
    for (var i = 0; i < values.length; i++) {
      var row = values[i].map(function (val) {
        if (val instanceof Date) {
          return Utilities.formatDate(val, Session.getScriptTimeZone(), "yyyy-MM-dd'T'HH:mm:ss");
        }
        return val;
      });
      rows.push(row);
    }
  }

  var nextStartRow = (startDataRow + rows.length <= totalDataRows) ? (startDataRow + rows.length) : null;

  return jsonOutput({
    headers: headers,
    rows: rows,
    totalDataRows: totalDataRows,
    nextStartRow: nextStartRow
  });
}

function jsonOutput(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
