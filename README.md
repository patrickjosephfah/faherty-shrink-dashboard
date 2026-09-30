# Faherty Inventory Leakage Dashboard

A self-contained Shrink dashboard covering fiscal years
2022 (partial/Legacy) through the current year, refreshed automatically every
day from a Google Sheet via GitHub Actions.

## How it works

- **`data/historical_seed.json`** — a frozen, one-time dataset covering
  Legacy/FY2023/FY2024/FY2025. This never changes automatically; it was built
  from historical NetSuite exports and only needs updating if you get a
  corrected historical export in the future (see "Updating the historical
  seed" below).
- **The Google Sheet** — holds the current fiscal year's transactions,
  refreshed daily by your Parabola flow. This repo doesn't touch Parabola at
  all; it just reads whatever the Sheet has.
- **`scripts/refresh_dashboard.py`** — the pipeline. Every day, it: pulls the
  Sheet, cleans it (dates, categories, reasons), classifies every location
  into a channel, tags each row with its fiscal year/quarter/month using
  Faherty's actual 4-4-5 retail calendar, combines it with the frozen
  historical seed, and writes a fresh `dashboard_v2.html`.
- **`.github/workflows/refresh.yml`** — runs that script once a day and
  commits the regenerated file back to the repo automatically.

Because the pipeline rebuilds the dashboard from scratch each day rather than
patching it, every day's version is also a full git commit — you get a
complete history of what the dashboard looked like on any past date, for
free, just by browsing this repo's commit log.

## One-time setup

### 1. Add the Apps Script to your Google Sheet

This exposes the Sheet's data as a small web endpoint the GitHub Action can
read — entirely inside Google Sheets' own interface, no Google Cloud project
or billing involved.

1. Open the Google Sheet → **Extensions → Apps Script**.
2. Delete whatever's in the default `Code.gs` file, and paste in the contents
   of this repo's `apps_script/Code.gs`.
3. Set the shared secret: click the gear icon (**Project Settings**) in the
   left sidebar → scroll to **Script Properties** → **Add script property** →
   name it `SECRET_TOKEN`, and set the value to any long random string you
   make up (this is what stands in for a login, since the GitHub Action runs
   unattended with nobody to sign in interactively).
4. Click **Deploy → New deployment** → gear icon → type **Web app**.
   - **Execute as**: Me
   - **Who has access**: Anyone
   - Click **Deploy**, authorize it when prompted (it'll warn that the app
     isn't verified — that's expected for a script you wrote yourself; click
     through "Advanced" → "Go to (project name)").
5. Copy the **Web app URL** it gives you (looks like
   `https://script.google.com/macros/s/AKfycb.../exec`) — you'll need this
   and the secret token in step 3 below.

**If you ever edit the script later**, you need to create a **new version**
under Deploy → Manage deployments → edit (pencil icon) → new version, or your
changes won't take effect — Apps Script keeps serving whichever version was
active at deploy time.

### 2. Create the GitHub repository

- Create a **private** repository (Settings → visibility → Private).
- Add this entire folder's contents to it.
- For now, control who can see the dashboard by adding specific people as
  **collaborators** (Settings → Collaborators) — they can then view or clone
  the repo, including opening `dashboard_v2.html` locally in a browser. This
  is the "start simple" access model; see "Upgrading access control" below
  for a more seamless option later.

### 3. Add GitHub Secrets

In the repo, go to **Settings → Secrets and variables → Actions → New
repository secret**, and add:

| Secret name | Value |
|---|---|
| `APPS_SCRIPT_URL` | The Web app URL from step 1.5 |
| `APPS_SCRIPT_TOKEN` | The same random string you set as `SECRET_TOKEN` in step 1.3 |
| `GOOGLE_SHEET_WORKSHEET` | The exact tab name in the Sheet (optional — omit to use the first tab) |

### 4. Test it

Before trusting the daily automation, run it manually once:

- Go to the **Actions** tab → **Refresh Dashboard** → **Run workflow**.
- Watch the log. If something's misconfigured (missing columns, wrong
  secret, wrong tab name), it'll show up here with a specific error rather
  than failing silently overnight.
- If it succeeds, `dashboard_v2.html` will be updated and committed
  automatically — open it to confirm the numbers look right.

You can also sanity-check the Apps Script directly, without GitHub at all,
by pasting this into a browser (with your real URL and token):
`https://script.google.com/macros/s/.../exec?token=YOUR_TOKEN&numRows=5` — it
should return a small JSON blob with your sheet's headers and first 5 rows.

You can also test the full pipeline locally, without touching Google at all,
using any CSV with the right columns:

```bash
pip install -r scripts/requirements.txt
python scripts/refresh_dashboard.py --local-csv path/to/test.csv
```

## Required columns in the Google Sheet

The pipeline expects these column headers (exact names, case-sensitive):

`Transaction Date`, `Location`, `SKU`, `UPC`, `Variance Quantity`,
`Financial Impact ($)`, `Adjustment Reason`, `Failure Point Category`

These are optional but used when present: `Location Type`, `Region`, `Area`,
`Vibe`, `Memo`. If your Sheet doesn't have Location Type/Region/Area/Vibe,
locations still get classified via the manual override rules in
`scripts/location_classification.py`.

## Things that need occasional manual attention

**`scripts/fiscal_calendar.py`** hardcodes Faherty's confirmed fiscal
month-end dates (a real 4-4-5 retail calendar), currently confirmed through
FY2026 Q3. Beyond that, it auto-extrapolates using the repeating 4-4-5
pattern so the pipeline never breaks — but that extrapolation doesn't know
about future 53-week "leap" years the way FY2025 had one. When Faherty's
finance team publishes the next fiscal year's period-end dates, add them to
`CONFIRMED_PERIODS` in that file.

**`scripts/location_classification.py`** holds every manual location→channel
override we've built up (damage locations, sample-sale venues, a few
locations with no Location Type field at all). If a brand-new location shows
up that isn't covered by any rule, it silently falls back to
Wholesale/Specialty — check the dashboard's channel totals periodically for
anything that looks misclassified, and add an explicit rule here once you
know what the location actually is.

**File size will grow over time.** Every fiscal year is kept at full
transaction-level detail (no pre-aggregation) so that features like Matched
Recovery can work across all years — currently ~36MB. This will keep growing
as more of the current year accumulates and as future years get added. If it
ever becomes unwieldy, the option to pre-aggregate older years again is
available, at the cost of losing Matched Recovery / per-transaction drill-down
for those years.

## Updating the historical seed

The historical seed (`data/historical_seed.json`) is frozen by design — it
won't pick up corrections automatically. If you ever get a corrected or
extended historical export:

1. Re-run the same cleaning/classification/fiscal-tagging steps against the
   new export (the logic in `refresh_dashboard.py`'s `clean_current_year_data`,
   `classify_locations`, and `tag_fiscal_periods` functions can be reused directly).
2. Export the result in the same structure as the current seed file
   (`locations`, `skus`, `upcs`, `memos`, `categories`, `channels`, `reasons`,
   `fmonths`, `rows`, `baseDate`).
3. Replace `data/historical_seed.json` and commit.

## Upgrading access control later

Right now, viewing the dashboard means being a repo collaborator and opening
the file directly (via download or clone). For a real "visit a URL, see the
live dashboard" experience restricted to Faherty emails, the most realistic
path without a GitHub Enterprise plan is **Cloudflare Access** in front of a
static hosting deployment (e.g. Cloudflare Pages, synced to this repo) — it
can gate access by Google Workspace domain directly, so only
`@fahertybrand.com` Google logins get through, and it's free at reasonable
usage levels. Come back to this once the daily refresh has been running
reliably for a while.
