"""
Faherty's actual fiscal calendar: a 4-4-5 retail calendar, fiscal year = Jan-Dec.

CONFIRMED_PERIODS below is transcribed directly from Faherty's own fiscal
month-end folder listing (as of Sep 2026, confirmed through FY2026 Q3/Aug).
Each quarter is 4 weeks - 4 weeks - 5 weeks. FY2025 had a 53rd "leap" week
inserted into its December period to re-sync with the calendar.

*** THIS TABLE NEEDS TO BE UPDATED PERIODICALLY. ***
When Faherty's finance team publishes the next fiscal year's period-end
dates, add them to CONFIRMED_PERIODS below (same format). Until that
happens, any transaction dated after the last confirmed period_end falls
back to AUTO-EXTRAPOLATED periods (see extrapolate_forward()), which just
continues the repeating 4-4-5 pattern indefinitely. That fallback keeps the
pipeline from breaking, but it does NOT know about future leap weeks or any
other calendar change Faherty's finance team might make, so it will
silently drift out of sync with the real calendar over time. Treat any
period flagged is_extrapolated=True in dashboard output as provisional.
"""

import datetime

# (period_start, period_end, fiscal_year, fiscal_quarter, fiscal_month)
CONFIRMED_PERIODS = [
    ('2023-01-01', '2023-01-28', 2023, 1, 'Jan'),
    ('2023-01-29', '2023-02-25', 2023, 1, 'Feb'),
    ('2023-02-26', '2023-04-01', 2023, 1, 'Mar'),
    ('2023-04-02', '2023-04-29', 2023, 2, 'Apr'),
    ('2023-04-30', '2023-05-27', 2023, 2, 'May'),
    ('2023-05-28', '2023-07-01', 2023, 2, 'Jun'),
    ('2023-07-02', '2023-07-29', 2023, 3, 'Jul'),
    ('2023-07-30', '2023-08-26', 2023, 3, 'Aug'),
    ('2023-08-27', '2023-09-30', 2023, 3, 'Sep'),
    ('2023-10-01', '2023-10-28', 2023, 4, 'Oct'),
    ('2023-10-29', '2023-11-25', 2023, 4, 'Nov'),
    ('2023-11-26', '2023-12-30', 2023, 4, 'Dec'),
    ('2023-12-31', '2024-01-27', 2024, 1, 'Jan'),
    ('2024-01-28', '2024-02-24', 2024, 1, 'Feb'),
    ('2024-02-25', '2024-03-30', 2024, 1, 'Mar'),
    ('2024-03-31', '2024-04-27', 2024, 2, 'Apr'),
    ('2024-04-28', '2024-05-25', 2024, 2, 'May'),
    ('2024-05-26', '2024-06-29', 2024, 2, 'Jun'),
    ('2024-06-30', '2024-07-27', 2024, 3, 'Jul'),
    ('2024-07-28', '2024-08-24', 2024, 3, 'Aug'),
    ('2024-08-25', '2024-09-28', 2024, 3, 'Sep'),
    ('2024-09-29', '2024-10-26', 2024, 4, 'Oct'),
    ('2024-10-27', '2024-11-23', 2024, 4, 'Nov'),
    ('2024-11-24', '2024-12-28', 2024, 4, 'Dec'),
    ('2024-12-29', '2025-01-25', 2025, 1, 'Jan'),
    ('2025-01-26', '2025-02-22', 2025, 1, 'Feb'),
    ('2025-02-23', '2025-03-29', 2025, 1, 'Mar'),
    ('2025-03-30', '2025-04-26', 2025, 2, 'Apr'),
    ('2025-04-27', '2025-05-24', 2025, 2, 'May'),
    ('2025-05-25', '2025-06-28', 2025, 2, 'Jun'),
    ('2025-06-29', '2025-07-26', 2025, 3, 'Jul'),
    ('2025-07-27', '2025-08-23', 2025, 3, 'Aug'),
    ('2025-08-24', '2025-09-27', 2025, 3, 'Sep'),
    ('2025-09-28', '2025-10-25', 2025, 4, 'Oct'),
    ('2025-10-26', '2025-11-22', 2025, 4, 'Nov'),
    ('2025-11-23', '2026-01-03', 2025, 4, 'Dec'),   # 53-week leap month
    ('2026-01-04', '2026-01-31', 2026, 1, 'Jan'),
    ('2026-02-01', '2026-02-28', 2026, 1, 'Feb'),
    ('2026-03-01', '2026-04-04', 2026, 1, 'Mar'),
    ('2026-04-05', '2026-05-02', 2026, 2, 'Apr'),
    ('2026-05-03', '2026-05-30', 2026, 2, 'May'),
    ('2026-05-31', '2026-07-04', 2026, 2, 'Jun'),
    ('2026-07-05', '2026-08-01', 2026, 3, 'Jul'),
    ('2026-08-02', '2026-08-29', 2026, 3, 'Aug'),
]

FIRST_CONFIRMED_START = datetime.date(2023, 1, 1)
MONTH_CYCLE = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
QUARTER_CYCLE = [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4]
WEEKS_CYCLE = [4, 4, 5, 4, 4, 5, 4, 4, 5, 4, 4, 5]  # weeks per fiscal month, repeating each FY


def _parse(d):
    return datetime.date.fromisoformat(d)


def _build_table():
    table = []
    for start, end, fy, fq, fm in CONFIRMED_PERIODS:
        table.append({
            'start': _parse(start), 'end': _parse(end),
            'fiscal_year': fy, 'fiscal_quarter': fq, 'fiscal_month': fm,
            'is_extrapolated': False,
        })
    return table


def extrapolate_forward(table, up_to_date):
    """Extend the table past its last confirmed period using the recurring
    4-4-5 pattern, until it covers up_to_date. Marks each added period
    is_extrapolated=True. Does NOT know about future leap weeks."""
    last = table[-1]
    # figure out where we are in the Jan-Dec / 4-4-5 cycle
    month_idx = MONTH_CYCLE.index(last['fiscal_month'])
    fy = last['fiscal_year']
    cursor_start = last['end'] + datetime.timedelta(days=1)

    while table[-1]['end'] < up_to_date:
        month_idx += 1
        if month_idx > 11:
            month_idx = 0
            fy += 1
        weeks = WEEKS_CYCLE[month_idx]
        end = cursor_start + datetime.timedelta(weeks=weeks) - datetime.timedelta(days=1)
        table.append({
            'start': cursor_start, 'end': end,
            'fiscal_year': fy, 'fiscal_quarter': QUARTER_CYCLE[month_idx],
            'fiscal_month': MONTH_CYCLE[month_idx],
            'is_extrapolated': True,
        })
        cursor_start = end + datetime.timedelta(days=1)
    return table


def build_calendar(up_to_date=None):
    """Returns the full period table, confirmed periods plus any
    extrapolated periods needed to cover up_to_date (defaults to today)."""
    table = _build_table()
    if up_to_date is None:
        up_to_date = datetime.date.today()
    if table[-1]['end'] < up_to_date:
        table = extrapolate_forward(table, up_to_date)
    return table


def classify_date(d, table):
    """Given a date (datetime.date) and a calendar table, return the
    matching period dict, or None if d is before the first confirmed period
    (i.e. pre-2023, no confirmed calendar -> caller should bucket as Legacy)."""
    if d < FIRST_CONFIRMED_START:
        return None
    for period in table:
        if period['start'] <= d <= period['end']:
            return period
    # Shouldn't happen if build_calendar() was called with a late-enough
    # up_to_date, but fall back to the last period defensively.
    return table[-1]
