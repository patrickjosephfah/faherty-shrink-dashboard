"""
Location -> Channel classification rules.

Channels: 0=Retail Stores, 1=Warehouse, 2=Wholesale/Specialty,
          3=Returns Network, 4=Hospitality, 5=Damages

Most locations classify automatically from their raw "Location Type" field.
A handful needed manual overrides based on how Faherty actually operates
them (confirmed with Patrick during the dashboard build):
  - Named damage-tracking locations always go to the Damages channel,
    regardless of what Location Type they're tagged with upstream.
  - A few specific locations are operationally Wholesale/Specialty even
    though their raw Location Type says otherwise (e.g. sample-sale venues,
    outsourced finishing).
  - A batch of locations that appeared for the first time in the historical
    backfill (Mar 2022 - Jan 2026) had no Location Type at all and were
    classified by hand, one time, based on their names.

*** If a brand-new location shows up that isn't covered by any rule below,
it silently falls back to Wholesale/Specialty (channel 2) as a safe
default. Check the dashboard's channel totals periodically for anything
that looks misclassified, and add an explicit rule here once you know
what it actually is. ***
"""

CHANNELS = ["Retail Stores", "Warehouse", "Wholesale/Specialty", "Returns Network", "Hospitality", "Damages"]

DAMAGE_LOCATIONS = {
    'Warehouse Damages',
    'Retail Damages',
    'Damages - Wholesale Not Returned',
    'Damages - Wholesale Not Returned : damages',
}

SPECIALTY_OVERRIDES = {
    'Embroidery- Modern Stitch',   # outsourced finishing, not a warehouse
}

# One-time manual classification for locations that only appeared in the
# historical backfill and had no Location Type field at all.
HISTORICAL_ONLY_OVERRIDES = {
    'Consignment Otrium LLC': 2,
    'Cons. 260 Sample Sale LA': 2,
    'Santana Row': 0,
    'Pacific Palisades': 0,
    'Las Olas Partner Store': 0,
    'Consignment For Now': 2,
    'Consignment Brika BrentonVille': 2,
    'OFFPRICE Rue Gilt Groupe, Inc': 2,
    'CONSIGNMENT Arizona State University': 2,
    'CONSIGNMENT FOUR SEASONS HUALALAI CLUB': 2,  # Wholesale/Specialty
    'Consignment Fred Segal LLC': 2,
    'Hold for QC - OP': 1,
    'Consignment The Landing Lab': 2,
    'Yang Kee HK': 2,
    'Hold- PFAS ADs': 1,
}

_TYPE_TO_CHANNEL = {
    'Retail Store': 0,
    'Warehouse': 1,
    'Wholesale': 2,
    'Corporate': 2,
    'Happy Returns Bar In Transit': 3,
    'Hospitality': 4,
}


def channel_for(location_name, location_type):
    """location_type may be None/NaN for rows with no enrichment data."""
    if location_name in DAMAGE_LOCATIONS:
        return 5
    if location_name in SPECIALTY_OVERRIDES:
        return 2
    if location_name in HISTORICAL_ONLY_OVERRIDES:
        return HISTORICAL_ONLY_OVERRIDES[location_name]
    if location_type in _TYPE_TO_CHANNEL:
        return _TYPE_TO_CHANNEL[location_type]
    return 2  # safe fallback: Wholesale/Specialty
