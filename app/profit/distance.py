"""Approximate UK distance lookup from a postcode district / town name to the base location.

Uses postcode-AREA centroids (the letters, e.g. 'SK' for SK4) and a small town table.
Good enough for a fuel/time estimate; the real route is the user's call. Values are approximate.
"""
from __future__ import annotations

import math
import re
from typing import Optional

POSTCODE_AREAS: dict[str, tuple[float, float]] = {
    "AB": (57.15, -2.11), "AL": (51.75, -0.33), "B": (52.48, -1.90), "BA": (51.38, -2.36), "BB": (53.75, -2.48),
    "BD": (53.79, -1.75), "BH": (50.72, -1.88), "BL": (53.58, -2.43), "BN": (50.83, -0.14), "BR": (51.40, 0.02),
    "BS": (51.45, -2.59), "BT": (54.60, -5.93), "CA": (54.89, -2.94), "CB": (52.21, 0.12), "CF": (51.48, -3.18),
    "CH": (53.19, -2.89), "CM": (51.73, 0.47), "CO": (51.89, 0.90), "CR": (51.37, -0.10), "CT": (51.28, 1.08),
    "CV": (52.41, -1.51), "CW": (53.10, -2.44), "DA": (51.44, 0.22), "DD": (56.46, -2.97), "DE": (52.92, -1.48),
    "DG": (55.07, -3.60), "DH": (54.78, -1.58), "DL": (54.52, -1.55), "DN": (53.52, -1.13), "DT": (50.71, -2.44),
    "DY": (52.51, -2.08), "E": (51.53, -0.05), "EC": (51.52, -0.09), "EH": (55.95, -3.19), "EN": (51.65, -0.08),
    "EX": (50.72, -3.53), "FK": (56.00, -3.78), "FY": (53.82, -3.05), "G": (55.86, -4.25), "GL": (51.86, -2.24),
    "GU": (51.24, -0.57), "HA": (51.58, -0.34), "HD": (53.65, -1.78), "HG": (54.00, -1.54), "HP": (51.75, -0.47),
    "HR": (52.06, -2.72), "HS": (57.76, -7.02), "HU": (53.75, -0.34), "HX": (53.72, -1.86), "IG": (51.56, 0.08),
    "IP": (52.06, 1.16), "IV": (57.48, -4.22), "KA": (55.61, -4.50), "KT": (51.41, -0.30), "KW": (58.98, -2.96),
    "KY": (56.11, -3.16), "L": (53.41, -2.98), "LA": (54.05, -2.80), "LD": (52.24, -3.38), "LE": (52.63, -1.13),
    "LL": (53.32, -3.83), "LN": (53.23, -0.54), "LS": (53.80, -1.55), "LU": (51.88, -0.42), "M": (53.48, -2.24),
    "ME": (51.39, 0.53), "MK": (52.04, -0.76), "ML": (55.79, -3.99), "N": (51.57, -0.11), "NE": (54.98, -1.61),
    "NG": (52.95, -1.15), "NN": (52.24, -0.90), "NP": (51.59, -3.00), "NR": (52.63, 1.30), "NW": (51.55, -0.17),
    "OL": (53.54, -2.11), "OX": (51.75, -1.26), "PA": (55.85, -4.42), "PE": (52.57, -0.24), "PH": (56.40, -3.43),
    "PL": (50.38, -4.14), "PO": (50.80, -1.09), "PR": (53.76, -2.70), "RG": (51.45, -0.97), "RH": (51.24, -0.17),
    "RM": (51.58, 0.18), "S": (53.38, -1.47), "SA": (51.62, -3.94), "SE": (51.47, -0.06), "SG": (51.90, -0.20),
    "SK": (53.41, -2.16), "SL": (51.51, -0.59), "SM": (51.36, -0.19), "SN": (51.56, -1.78), "SO": (50.91, -1.40),
    "SP": (51.07, -1.79), "SR": (54.91, -1.38), "SS": (51.54, 0.71), "ST": (53.00, -2.18), "SW": (51.46, -0.17),
    "SY": (52.71, -2.75), "TA": (51.02, -3.10), "TD": (55.62, -2.81), "TF": (52.68, -2.45), "TN": (51.19, 0.27),
    "TQ": (50.46, -3.53), "TR": (50.26, -5.05), "TS": (54.57, -1.23), "TW": (51.45, -0.33), "UB": (51.55, -0.48),
    "W": (51.51, -0.19), "WA": (53.39, -2.59), "WC": (51.52, -0.12), "WD": (51.66, -0.40), "WF": (53.68, -1.50),
    "WN": (53.55, -2.63), "WR": (52.19, -2.22), "WS": (52.59, -1.98), "WV": (52.59, -2.13), "YO": (53.96, -1.08),
    "ZE": (60.15, -1.15),
}

TOWNS: dict[str, tuple[float, float]] = {
    "manchester": (53.48, -2.24), "salford": (53.49, -2.29), "stockport": (53.41, -2.16), "bolton": (53.58, -2.43),
    "oldham": (53.54, -2.11), "rochdale": (53.61, -2.16), "bury": (53.59, -2.30), "wigan": (53.55, -2.63),
    "warrington": (53.39, -2.59), "liverpool": (53.41, -2.98), "chester": (53.19, -2.89), "preston": (53.76, -2.70),
    "blackburn": (53.75, -2.48), "blackpool": (53.82, -3.05), "leeds": (53.80, -1.55), "bradford": (53.79, -1.75),
    "sheffield": (53.38, -1.47), "huddersfield": (53.65, -1.78), "york": (53.96, -1.08), "hull": (53.75, -0.34),
    "macclesfield": (53.26, -2.13), "crewe": (53.10, -2.44), "stoke": (53.00, -2.18), "stoke-on-trent": (53.00, -2.18),
    "derby": (52.92, -1.48), "nottingham": (52.95, -1.15), "leicester": (52.63, -1.13), "birmingham": (52.48, -1.90),
    "coventry": (52.41, -1.51), "wolverhampton": (52.59, -2.13), "shrewsbury": (52.71, -2.75), "telford": (52.68, -2.45),
    "london": (51.51, -0.12), "croydon": (51.37, -0.10), "reading": (51.45, -0.97), "oxford": (51.75, -1.26),
    "cambridge": (52.21, 0.12), "norwich": (52.63, 1.30), "ipswich": (52.06, 1.16), "milton keynes": (52.04, -0.76),
    "bristol": (51.45, -2.59), "bath": (51.38, -2.36), "cardiff": (51.48, -3.18), "swansea": (51.62, -3.94),
    "newport": (51.59, -3.00), "exeter": (50.72, -3.53), "plymouth": (50.38, -4.14), "torquay": (50.46, -3.53),
    "southampton": (50.91, -1.40), "portsmouth": (50.80, -1.09), "brighton": (50.83, -0.14), "bournemouth": (50.72, -1.88),
    "newcastle": (54.98, -1.61), "sunderland": (54.91, -1.38), "durham": (54.78, -1.58), "middlesbrough": (54.57, -1.23),
    "carlisle": (54.89, -2.94), "lancaster": (54.05, -2.80), "glasgow": (55.86, -4.25), "edinburgh": (55.95, -3.19),
    "dundee": (56.46, -2.97), "aberdeen": (57.15, -2.11), "inverness": (57.48, -4.22), "belfast": (54.60, -5.93),
    "doncaster": (53.52, -1.13), "wakefield": (53.68, -1.50), "halifax": (53.72, -1.86), "barnsley": (53.55, -1.48),
    "rotherham": (53.43, -1.36), "lincoln": (53.23, -0.54), "peterborough": (52.57, -0.24), "northampton": (52.24, -0.90),
    "luton": (51.88, -0.42), "watford": (51.66, -0.40), "slough": (51.51, -0.59), "guildford": (51.24, -0.57),
    "swindon": (51.56, -1.78), "gloucester": (51.86, -2.24), "cheltenham": (51.90, -2.07), "worcester": (52.19, -2.22),
    "altrincham": (53.39, -2.35), "sale": (53.42, -2.32), "ashton": (53.49, -2.10), "tameside": (53.49, -2.10),
}

ROAD_FACTOR = 1.25  # straight-line to road distance


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def geocode(postcode_district: str = "", location_text: str = "") -> Optional[tuple[float, float]]:
    """Resolve a postcode district (e.g. 'SK4') or town text to approx lat/lon."""
    pc = (postcode_district or "").strip().upper()
    if pc:
        m = re.match(r"^([A-Z]{1,2})\d", pc)
        if m and m.group(1) in POSTCODE_AREAS:
            return POSTCODE_AREAS[m.group(1)]
    text = (location_text or "").lower()
    if text:
        m = re.search(r"\b([a-z]{1,2})\d{1,2}[a-z]?\b", text)
        if m and m.group(1).upper() in POSTCODE_AREAS:
            return POSTCODE_AREAS[m.group(1).upper()]
        # earliest-mentioned town wins ("Stockport, Greater Manchester" -> Stockport); ties go to the longer name
        best: Optional[tuple[int, int, str]] = None
        for town in TOWNS:
            m = re.search(r"\b" + re.escape(town) + r"\b", text)
            if m and (best is None or (m.start(), -len(town)) < (best[0], -best[1])):
                best = (m.start(), len(town), town)
        if best:
            return TOWNS[best[2]]
    return None


def road_miles(base: dict, postcode_district: str = "", location_text: str = "") -> Optional[float]:
    """One-way road miles from base {'lat','lon'} (or {'postcode'}) to the listing location."""
    if base.get("lat") is None or base.get("lon") is None:
        b = geocode(base.get("postcode", ""), base.get("label", ""))
        if not b:
            return None
        blat, blon = b
    else:
        blat, blon = float(base["lat"]), float(base["lon"])
    dest = geocode(postcode_district, location_text)
    if not dest:
        return None
    return round(haversine_miles(blat, blon, dest[0], dest[1]) * ROAD_FACTOR, 1)


def collection_cost(one_way_miles: float, pence_per_mile: float, hourly_rate: float, avg_mph: float, handling_minutes: float) -> float:
    """Round-trip vehicle cost + time cost."""
    rt = one_way_miles * 2
    fuel = rt * pence_per_mile / 100
    hours = rt / max(avg_mph, 5) + handling_minutes / 60
    return round(fuel + hours * hourly_rate, 2)
