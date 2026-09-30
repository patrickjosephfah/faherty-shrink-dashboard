#!/usr/bin/env python3
"""
Daily dashboard refresh pipeline.

Pulls the current fiscal year's transaction data from the Google Sheet (via
the Apps Script web endpoint — see apps_script/Code.gs and README.md for
setup), combines it with the frozen historical seed
(data/historical_seed.json, covering Legacy through FY2025), and regenerates
dashboard_v2.html.

Usage:
    python refresh_dashboard.py                        # pulls live via Apps Script
    python refresh_dashboard.py --local-csv PATH.csv    # for testing without
                                                           Google at all —
                                                           reads a local CSV
                                                           instead

Environment variables (only needed for the real Apps Script path):
    APPS_SCRIPT_URL          the deployed Web app URL (ends in /exec)
    APPS_SCRIPT_TOKEN        the shared secret set as SECRET_TOKEN in the
                              Sheet's Script Properties
    GOOGLE_SHEET_WORKSHEET   the exact tab name (optional — omit to use the
                              first tab)
"""

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent

sys.path.insert(0, str(SCRIPT_DIR))
import fiscal_calendar as fc
from location_classification import channel_for, CHANNELS

# ---------------------------------------------------------------------------
# Expected columns, matching the Google Sheet's structure (confirmed to match
# the historical CSV exports' schema). Adjust REQUIRED_COLUMNS if your sheet
# uses different header names.
# ---------------------------------------------------------------------------
REQUIRED_COLUMNS = [
    'Transaction Date', 'Location', 'SKU', 'UPC', 'Variance Quantity',
    'Financial Impact ($)', 'Adjustment Reason', 'Failure Point Category',
]
OPTIONAL_COLUMNS = ['Location Type', 'Region', 'Area', 'Vibe', 'Memo']

CATS = ["Physical Shrink (Loss)", "Found Inventory (Write-On)", "Stuck In-Transit",
        "Unreceived Return", "Inbound Shortage"]

# NetSuite has silently renamed this category before (dropped the "(Loss)"
# suffix partway through 2026) — normalize known variants defensively.
CATEGORY_ALIASES = {
    'Physical Shrink': 'Physical Shrink (Loss)',
}


def fetch_from_apps_script():
    """Pull the full current sheet into a DataFrame via the Apps Script web
    endpoint (see apps_script/Code.gs), paginating automatically since a very
    large sheet could otherwise risk hitting Apps Script's per-call limits."""
    import requests

    url = os.environ.get('APPS_SCRIPT_URL')
    token = os.environ.get('APPS_SCRIPT_TOKEN')
    worksheet_name = os.environ.get('GOOGLE_SHEET_WORKSHEET')  # tab name; omit to use the first tab
    if not url or not token:
        raise RuntimeError(
            "APPS_SCRIPT_URL and APPS_SCRIPT_TOKEN must be set. "
            "See README.md for setup, or use --local-csv for a test run."
        )

    all_rows = []
    headers = None
    start_row = 1
    page_size = 50000

    while True:
        params = {'token': token, 'startRow': start_row, 'numRows': page_size}
        if worksheet_name:
            params['sheet'] = worksheet_name
        resp = requests.get(url, params=params, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        if 'error' in data:
            raise RuntimeError(f"Apps Script error: {data['error']}")
        if headers is None:
            headers = data['headers']
        all_rows.extend(data['rows'])
        fetched_so_far = start_row + len(data['rows']) - 1 if data['rows'] else start_row - 1
        print(f"  Fetched rows {start_row}-{fetched_so_far} of {data['totalDataRows']}")
        if not data.get('nextStartRow'):
            break
        start_row = data['nextStartRow']

    df = pd.DataFrame(all_rows, columns=headers)
    print(f"Pulled {len(df)} rows total via Apps Script.")
    return df


def load_current_year_data(local_csv=None):
    if local_csv:
        print(f"Reading local CSV (test mode): {local_csv}")
        df = pd.read_csv(local_csv, low_memory=False)
    else:
        df = fetch_from_apps_script()

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise RuntimeError(f"Sheet/CSV is missing required columns: {missing}")
    for c in OPTIONAL_COLUMNS:
        if c not in df.columns:
            df[c] = None

    return df


def _to_clean_str(series, blank_value=''):
    """Force a column to uniform string values. Google Sheets (and therefore
    Apps Script) auto-converts number-looking text in a free-text cell (e.g.
    a Memo that's just '55105') into a real number — which later breaks any
    sorted()/set() operation that mixes those numbers with genuine text from
    other rows. This collapses everything to clean strings, and avoids
    turning whole numbers into '123.0'-style artifacts."""
    def conv(v):
        if pd.isna(v):
            return blank_value
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)
    return series.apply(conv)


def clean_current_year_data(df):
    df = df.copy()

    # dates: real-world exports have mixed formats within the same column
    # (ISO timestamps, plain MM/DD/YYYY, date-only strings, etc. have all shown
    # up across different pulls) — format='mixed' infers per-row rather than
    # committing to one format for the whole column, which is what a fixed
    # substring check (e.g. "contains T") can silently get wrong.
    dt = pd.to_datetime(df['Transaction Date'], format='mixed', errors='coerce', utc=True)
    dt = dt.dt.tz_localize(None)
    unparsed = dt.isna().sum()
    if unparsed:
        print(f"WARNING: {unparsed} rows had unparseable dates and will be dropped.")
    df['Transaction Date'] = dt
    df = df[df['Transaction Date'].notna()].copy()

    df['Failure Point Category'] = df['Failure Point Category'].replace(CATEGORY_ALIASES)
    bad_cats = set(df['Failure Point Category'].unique()) - set(CATS)
    if bad_cats:
        print(f"WARNING: unrecognized Failure Point Category values found: {bad_cats} "
              f"— these rows' category won't map correctly. Add them to CATEGORY_ALIASES "
              f"or CATS in this script.")

    # every column that later feeds a sorted()/set() dimension-building step
    # needs to be a uniform string type, or Python can't compare/sort it
    df['Location'] = _to_clean_str(df['Location'])
    df['SKU'] = _to_clean_str(df['SKU'])
    df['Adjustment Reason'] = _to_clean_str(df['Adjustment Reason'], blank_value='—')
    df['Memo'] = _to_clean_str(df['Memo'])

    df['Variance Quantity'] = pd.to_numeric(df['Variance Quantity'], errors='coerce').fillna(0).astype(int)
    df['Financial Impact ($)'] = pd.to_numeric(df['Financial Impact ($)'], errors='coerce').fillna(0).round(2)

    return df


def classify_locations(df):
    """Returns a dict: location name -> [channel, region, area, vibe]."""
    loc_dim = df.groupby('Location')[['Location Type', 'Region', 'Area', 'Vibe']].first()
    meta = {}
    for loc, row in loc_dim.iterrows():
        ltype = row['Location Type'] if pd.notna(row['Location Type']) else None
        ch = channel_for(loc, str(ltype) if ltype is not None else None)

        def clean_optional(v):
            # keep as None when missing, but force a consistent string type
            # when present — the dashboard's JS does strict string equality
            # against these values for the Region/Area/Vibe filter dropdowns,
            # so a stray number here would silently fail to filter correctly
            # rather than throw an error.
            if pd.isna(v):
                return None
            if isinstance(v, float) and v.is_integer():
                return str(int(v))
            return str(v)

        meta[loc] = [ch, clean_optional(row['Region']), clean_optional(row['Area']), clean_optional(row['Vibe'])]
    return meta


def tag_fiscal_periods(df):
    cal = fc.build_calendar(up_to_date=df['Transaction Date'].max().date())

    def classify(dt):
        period = fc.classify_date(dt.date(), cal)
        if period is None:
            return pd.Series([0, 'Legacy'])
        return pd.Series([period['fiscal_year'], period['fiscal_month']])

    result = df['Transaction Date'].apply(classify)
    df['fiscal_year'] = result[0]
    df['fiscal_month'] = result[1]
    return df


def fmonth_key(fiscal_year, fiscal_month):
    if fiscal_year == 0:
        return 'Legacy'
    return f"{int(fiscal_year)}-{fiscal_month}"


MONTH_ORDER = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def sort_fmonth_key(key):
    if key == 'Legacy':
        return (-1, -1)
    y, m = key.split('-')
    return (int(y), MONTH_ORDER.index(m))


def build_payload(seed, live_df):
    """Combine the frozen historical seed with freshly-pulled current-year data
    into one unified payload, rebuilding shared dimension indices from scratch
    each run so new locations/SKUs/reasons/memos in the live feed are picked
    up automatically."""

    live_loc_meta = classify_locations(live_df)
    live_df = tag_fiscal_periods(live_df)
    live_df['fmonth_key'] = live_df.apply(lambda r: fmonth_key(r['fiscal_year'], r['fiscal_month']), axis=1)

    # ---- unified location dimension ----
    seed_locs = {l[0]: l for l in seed['locations']}
    all_loc_names = sorted(set(seed_locs.keys()) | set(live_loc_meta.keys()))
    loc_index = {name: i for i, name in enumerate(all_loc_names)}
    loc_meta_list = []
    for name in all_loc_names:
        if name in live_loc_meta:
            ch, region, area, vibe = live_loc_meta[name]
        else:
            _, ch, region, area, vibe = seed_locs[name]
        loc_meta_list.append([name, ch, region, area, vibe])

    # ---- unified SKU + UPC dimension ----
    seed_skus = seed['skus']
    seed_upcs = {s: seed['upcs'][i] for i, s in enumerate(seed_skus)}
    live_upc = live_df.groupby('SKU')['UPC'].agg(lambda s: s.mode().iloc[0] if s.notna().any() else None)
    all_skus = sorted(set(seed_skus) | set(live_df['SKU'].unique()))
    sku_index = {s: i for i, s in enumerate(all_skus)}
    upcs = []
    for s in all_skus:
        v = live_upc.get(s)
        if pd.isna(v) or v is None:
            v = seed_upcs.get(s)
        upcs.append(None if pd.isna(v) else str(v))

    # ---- unified reasons ----
    all_reasons = sorted(set(seed['reasons']) | set(live_df['Adjustment Reason'].unique()))
    reason_index = {r: i for i, r in enumerate(all_reasons)}

    # ---- unified memos ----
    all_memos = sorted(set(seed['memos']) | set(live_df['Memo'].unique()))
    memo_index = {m: i for i, m in enumerate(all_memos)}

    # ---- unified fiscal months ----
    seed_fmonths = set(seed['fmonths'])
    live_fmonths = set(live_df['fmonth_key'].unique())
    all_fmonths_raw = seed_fmonths | live_fmonths
    fmonths = sorted([m for m in all_fmonths_raw if m != 'Legacy'], key=sort_fmonth_key)
    if 'Legacy' in all_fmonths_raw:
        fmonths = ['Legacy'] + fmonths
    fmonth_index = {m: i for i, m in enumerate(fmonths)}

    # ---- remap the frozen historical rows onto the new unified indices ----
    old_loc_by_idx = [l[0] for l in seed['locations']]
    old_sku_by_idx = seed['skus']
    old_reason_by_idx = seed['reasons']
    old_memo_by_idx = seed['memos']
    old_fmonth_by_idx = seed['fmonths']

    loc_remap = [loc_index[name] for name in old_loc_by_idx]
    sku_remap = [sku_index[s] for s in old_sku_by_idx]
    reason_remap = [reason_index[r] for r in old_reason_by_idx]
    memo_remap = [memo_index[m] for m in old_memo_by_idx]
    fmonth_remap = [fmonth_index[m] for m in old_fmonth_by_idx]

    hist_rows = [
        [r[0], loc_remap[r[1]], sku_remap[r[2]], r[3], r[4], r[5],
         reason_remap[r[6]], memo_remap[r[7]], fmonth_remap[r[8]]]
        for r in seed['rows']
    ]

    # ---- build live rows against the same unified indices ----
    base_date = pd.Timestamp(seed['baseDate'])
    live_df['dayOffset'] = (live_df['Transaction Date'] - base_date).dt.days.astype(int)
    live_loc_idx = live_df['Location'].map(loc_index)
    live_sku_idx = live_df['SKU'].map(sku_index)
    live_cat_idx = live_df['Failure Point Category'].map({c: i for i, c in enumerate(CATS)})
    live_reason_idx = live_df['Adjustment Reason'].map(reason_index)
    live_memo_idx = live_df['Memo'].map(memo_index)
    live_fmonth_idx = live_df['fmonth_key'].map(fmonth_index)

    live_rows = list(zip(
        live_df['dayOffset'].tolist(), live_loc_idx.tolist(), live_sku_idx.tolist(),
        live_cat_idx.tolist(), live_df['Variance Quantity'].tolist(),
        live_df['Financial Impact ($)'].tolist(), live_reason_idx.tolist(),
        live_memo_idx.tolist(), live_fmonth_idx.tolist()
    ))

    all_rows = hist_rows + live_rows

    payload = {
        "baseDate": seed['baseDate'],
        "locations": loc_meta_list,
        "skus": all_skus,
        "upcs": upcs,
        "memos": all_memos,
        "categories": CATS,
        "channels": CHANNELS,
        "reasons": all_reasons,
        "fmonths": fmonths,
        "rows": all_rows,
    }
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--local-csv', help='Read current-year data from a local CSV instead of Google Sheets (for testing)')
    parser.add_argument('--seed', default=str(REPO_ROOT / 'data' / 'historical_seed.json'))
    parser.add_argument('--template', default=str(REPO_ROOT / 'templates' / 'dashboard_template.html'))
    parser.add_argument('--out', default=str(REPO_ROOT / 'dashboard_v2.html'))
    args = parser.parse_args()

    print("Loading historical seed...")
    with open(args.seed) as f:
        seed = json.load(f)
    print(f"  {len(seed['rows'])} historical rows loaded.")

    print("Loading current-year data...")
    raw_df = load_current_year_data(local_csv=args.local_csv)
    df = clean_current_year_data(raw_df)
    print(f"  {len(df)} current-year rows after cleaning.")

    print("Building unified payload...")
    payload = build_payload(seed, df)
    print(f"  {len(payload['rows'])} total rows, {len(payload['locations'])} locations, "
          f"{len(payload['skus'])} SKUs, {len(payload['reasons'])} reasons, {len(payload['memos'])} memos.")

    payload_json = json.dumps(payload, separators=(',', ':'))
    print(f"  Payload size: {len(payload_json)/1e6:.1f} MB")

    print("Merging with template...")
    with open(args.template) as f:
        template = f.read()
    final_html = template.replace('__DATA_PAYLOAD__', payload_json)

    with open(args.out, 'w') as f:
        f.write(final_html)
    print(f"Wrote {args.out} ({os.path.getsize(args.out)/1e6:.1f} MB)")


if __name__ == '__main__':
    main()
