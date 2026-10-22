"""Amounts, units, durations and temperatures.

Everything here is pure functions with no I/O so the parser, the scheduler,
the shopping list and the tests can share it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --------------------------------------------------------------------------
# Units
# --------------------------------------------------------------------------

VOLUME = "volume"
WEIGHT = "weight"
COUNT = "count"

# canonical unit -> (kind, size in base units). Base is ml for volume, g for weight.
UNITS: dict[str, tuple[str, float]] = {
    "tsp": (VOLUME, 4.928922),
    "tbsp": (VOLUME, 14.786765),
    "fl oz": (VOLUME, 29.57353),
    "cup": (VOLUME, 236.5882),
    "pt": (VOLUME, 473.1765),
    "qt": (VOLUME, 946.3529),
    "gal": (VOLUME, 3785.412),
    "ml": (VOLUME, 1.0),
    "l": (VOLUME, 1000.0),
    "g": (WEIGHT, 1.0),
    "kg": (WEIGHT, 1000.0),
    "oz": (WEIGHT, 28.34952),
    "lb": (WEIGHT, 453.5924),
}

# Units that name a container or a piece. They never convert into each other.
COUNT_UNITS = [
    "pinch", "dash", "clove", "can", "stick", "slice", "sprig", "bunch",
    "head", "package", "scoop", "piece", "jar", "bottle", "handful", "stalk",
]
for _u in COUNT_UNITS:
    UNITS[_u] = (COUNT, 1.0)

METRIC = {"ml", "l", "g", "kg"}

# Units whose amount stays put when servings change.
NO_SCALE = {"pinch", "dash"}

_PLURAL_UNITS = {
    "pinch": "pinches", "dash": "dashes", "bunch": "bunches",
    "cup": "cups", "clove": "cloves", "can": "cans", "stick": "sticks",
    "slice": "slices", "sprig": "sprigs", "head": "heads",
    "package": "packages", "scoop": "scoops", "piece": "pieces",
    "jar": "jars", "bottle": "bottles", "handful": "handfuls",
    "stalk": "stalks",
}

# Case-sensitive aliases are checked first ("T" is tablespoon, "t" teaspoon).
_CASE_ALIASES = {"T": "tbsp", "t": "tsp", "Tb": "tbsp", "L": "l"}

_ALIASES: dict[str, str] = {}


def _alias(canonical: str, *names: str) -> None:
    for n in (canonical, *names):
        _ALIASES[n.lower()] = canonical


_alias("tsp", "tsps", "teaspoon", "teaspoons", "tsp.")
_alias("tbsp", "tbsps", "tbs", "tbl", "tablespoon", "tablespoons", "tbsp.")
_alias("fl oz", "fl. oz.", "fl. oz", "fl oz.", "fluid ounce", "fluid ounces", "floz")
_alias("cup", "cups", "c.")
_alias("pt", "pint", "pints")
_alias("qt", "quart", "quarts")
_alias("gal", "gallon", "gallons")
_alias("ml", "milliliter", "milliliters", "millilitre", "millilitres")
_alias("l", "liter", "liters", "litre", "litres")
_alias("g", "gram", "grams", "gr")
_alias("kg", "kilogram", "kilograms", "kgs")
_alias("oz", "ounce", "ounces", "oz.")
_alias("lb", "lbs", "pound", "pounds", "lb.", "lbs.")
for _u in COUNT_UNITS:
    _alias(_u, _PLURAL_UNITS.get(_u, _u + "s"))
_alias("package", "pkg", "pkgs", "packet", "packets", "pack", "packs")
_alias("piece", "pc", "pcs")


def canonical_unit(word: str) -> str | None:
    """Return the canonical unit for a word, or None if it is not a unit."""
    if word in _CASE_ALIASES:
        return _CASE_ALIASES[word]
    return _ALIASES.get(word.lower())


def unit_kind(unit: str | None) -> str | None:
    if unit is None:
        return None
    return UNITS[unit][0]


def unit_label(unit: str, amount: float | None) -> str:
    """Display form of a unit for an amount: '1 cup', '2 cups', '3 tbsp'."""
    if amount is not None and amount > 1 and unit in _PLURAL_UNITS:
        return _PLURAL_UNITS[unit]
    return unit


# --------------------------------------------------------------------------
# Amounts
# --------------------------------------------------------------------------

UNICODE_FRACTIONS = {
    "½": "1/2", "⅓": "1/3", "⅔": "2/3", "¼": "1/4", "¾": "3/4",
    "⅕": "1/5", "⅖": "2/5", "⅗": "3/5", "⅘": "4/5", "⅙": "1/6",
    "⅚": "5/6", "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8",
}

_NUM = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?|\.\d+)"
_AMOUNT_RE = re.compile(
    rf"^\s*(?P<low>{_NUM})(?:\s*(?:-|–|—|to)\s*(?P<high>{_NUM}))?(?=\s|$)"
)


def normalize_fractions(text: str) -> str:
    """'1½' -> '1 1/2', '½' -> '1/2', fraction slash -> '/'."""
    text = text.replace("⁄", "/")
    for ch, frac in UNICODE_FRACTIONS.items():
        text = re.sub(rf"(\d){ch}", rf"\1 {frac}", text)
        text = text.replace(ch, frac)
    return text


def parse_number(text: str) -> float:
    text = text.strip()
    if " " in text:
        whole, frac = text.split(None, 1)
        return float(whole) + parse_number(frac)
    if "/" in text:
        num, den = text.split("/", 1)
        if float(den) == 0:
            raise ValueError(f"zero denominator in {text!r}")
        return float(num) / float(den)
    return float(text)


def split_amount(text: str) -> tuple[float | None, float | None, str]:
    """Split a leading amount or range off text.

    Returns (low, high, rest). high is None unless a range was written.
    low is None when the text does not start with a number.
    """
    text = normalize_fractions(text)
    m = _AMOUNT_RE.match(text)
    if not m:
        return None, None, text.strip()
    low = parse_number(m.group("low"))
    high = parse_number(m.group("high")) if m.group("high") else None
    if high is not None and high <= low:
        high = None
    return low, high, text[m.end():].strip()


_NICE_FRACTIONS = [
    (0.0, ""), (1 / 8, "1/8"), (1 / 4, "1/4"), (1 / 3, "1/3"), (3 / 8, "3/8"),
    (1 / 2, "1/2"), (5 / 8, "5/8"), (2 / 3, "2/3"), (3 / 4, "3/4"),
    (7 / 8, "7/8"), (1.0, ""),
]


def format_amount(value: float, unit: str | None = None) -> str:
    """Kitchen-friendly display of an amount.

    Metric units round to whole numbers (one decimal under 10). Everything
    else snaps to the nearest eighth or third: 0.333 -> '1/3', 2.5 -> '2 1/2'.
    """
    if value <= 0:
        return "0"
    if unit in METRIC:
        if value >= 10:
            return str(int(round(value)))
        return f"{value:.1f}".rstrip("0").rstrip(".")
    if value >= 20:
        return str(int(round(value)))
    whole = int(value)
    frac = value - whole
    nearest = min(_NICE_FRACTIONS, key=lambda f: abs(f[0] - frac))
    if nearest[0] == 1.0:
        whole, label = whole + 1, ""
    else:
        label = nearest[1]
    if whole and label:
        return f"{whole} {label}"
    if label:
        return label
    return str(whole) if whole else f"{value:.2g}"


# --------------------------------------------------------------------------
# Conversion and merging (for the shopping list)
# --------------------------------------------------------------------------


def to_base(amount: float, unit: str) -> float:
    return amount * UNITS[unit][1]


def best_unit(base_amount: float, kind: str, metric: bool) -> tuple[float, str]:
    """Pick a readable unit for a merged amount in base units (ml or g)."""
    if kind == VOLUME:
        if metric:
            return (base_amount / 1000, "l") if base_amount >= 1000 else (base_amount, "ml")
        for unit, threshold in (("cup", UNITS["cup"][1] / 4), ("tbsp", UNITS["tbsp"][1])):
            if base_amount >= threshold - 1e-6:
                return base_amount / UNITS[unit][1], unit
        return base_amount / UNITS["tsp"][1], "tsp"
    if kind == WEIGHT:
        if metric:
            return (base_amount / 1000, "kg") if base_amount >= 1000 else (base_amount, "g")
        if base_amount >= UNITS["lb"][1] - 1e-6:
            return base_amount / UNITS["lb"][1], "lb"
        return base_amount / UNITS["oz"][1], "oz"
    raise ValueError(f"cannot pick a unit for kind {kind!r}")


_CLEAN = (0.0, 1 / 4, 1 / 3, 1 / 2, 2 / 3, 3 / 4, 1.0)
_SPOON_MIN = {"cup": 0.25, "tbsp": 1.0, "tsp": 0.0}  # biggest first


def _is_clean(value: float, unit: str) -> bool:
    frac = value - int(value)
    cleans = _CLEAN + ((1 / 8, 3 / 8, 5 / 8, 7 / 8) if unit == "tsp" else ())
    return any(abs(frac - c) < 0.01 for c in cleans)


def readable(amount: float, unit: str | None) -> tuple[float, str | None]:
    """Re-express a scaled spoon or cup measure the way a cook would say it.

    4 tbsp -> 1/4 cup, 6 tsp -> 2 tbsp, 1/8 cup -> 2 tbsp. The biggest unit
    giving a whole number or a quarter, third or half wins, so '10 tbsp'
    stays '10 tbsp' rather than becoming '5/8 cup'.
    """
    if unit not in _SPOON_MIN:
        return amount, unit
    base = to_base(amount, unit)
    for candidate, minimum in _SPOON_MIN.items():
        value = base / UNITS[candidate][1]
        if value >= minimum - 1e-6 and _is_clean(value, candidate):
            return value, candidate
    if amount >= _SPOON_MIN[unit] - 1e-6:
        return amount, unit
    for candidate, minimum in _SPOON_MIN.items():
        value = base / UNITS[candidate][1]
        if value >= minimum - 1e-6:
            return value, candidate
    return amount, unit


@dataclass
class Quantity:
    amount: float | None  # None means "to taste" / unmeasured
    unit: str | None


def merge_quantities(quantities: list[Quantity]) -> list[Quantity]:
    """Add up amounts of one ingredient.

    Volume adds to volume and weight to weight, converting between units of
    the same kind. Volume and weight are never converted into each other.
    Count units (cans, cloves) add only to the same unit. Unmeasured entries
    are kept once at the end.
    """
    volume = weight = 0.0
    any_volume = any_weight = False
    vol_metric = wt_metric = True
    counts: dict[str | None, float] = {}
    unmeasured = False
    for q in quantities:
        if q.amount is None:
            unmeasured = True
            continue
        kind = unit_kind(q.unit)
        if kind == VOLUME:
            volume += to_base(q.amount, q.unit)
            any_volume = True
            vol_metric &= q.unit in METRIC
        elif kind == WEIGHT:
            weight += to_base(q.amount, q.unit)
            any_weight = True
            wt_metric &= q.unit in METRIC
        else:
            counts[q.unit] = counts.get(q.unit, 0.0) + q.amount
    out: list[Quantity] = []
    if any_weight:
        out.append(Quantity(*best_unit(weight, WEIGHT, wt_metric)))
    if any_volume:
        out.append(Quantity(*best_unit(volume, VOLUME, vol_metric)))
    for unit, amount in counts.items():
        out.append(Quantity(amount, unit))
    if unmeasured and not out:
        out.append(Quantity(None, None))
    return out


# --------------------------------------------------------------------------
# Durations
# --------------------------------------------------------------------------

_DUR_UNITS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
}
_DUR_PART = r"(\d+(?:\.\d+)?)\s*(" + "|".join(sorted(_DUR_UNITS, key=len, reverse=True)) + r")(?![a-z])"
_DUR_ONE = rf"(?:{_DUR_PART}\s*)+"
_DUR_RE = re.compile(rf"^\s*({_DUR_ONE})\s*$", re.I)
_RANGE_RE = re.compile(rf"^\s*(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*({_DUR_ONE})\s*$", re.I)
_RANGE_FULL_RE = re.compile(rf"^\s*(?P<a>{_DUR_ONE})\s*(?:-|–|to)\s*(?P<b>{_DUR_ONE})\s*$", re.I)


def _dur_seconds(text: str) -> int:
    total = 0.0
    for num, unit in re.findall(_DUR_PART, text, re.I):
        total += float(num) * _DUR_UNITS[unit.lower()]
    return int(round(total))


def parse_duration(text: str) -> tuple[int, int] | None:
    """Parse '30m', '1h30m', '90s', '1.5h', '35-45m', '45m-1h'.

    Returns (low_seconds, high_seconds); equal when it is not a range.
    None if the text is not a duration.
    """
    m = _DUR_RE.match(text)
    if m:
        s = _dur_seconds(m.group(1))
        return s, s
    m = _RANGE_RE.match(text)
    if m:
        high = _dur_seconds(m.group(2))
        unit = re.findall(_DUR_PART, m.group(2), re.I)[0][1]
        low = int(round(float(m.group(1)) * _DUR_UNITS[unit.lower()]))
        return (low, high) if low < high else None
    m = _RANGE_FULL_RE.match(text)
    if m:
        low, high = _dur_seconds(m.group("a")), _dur_seconds(m.group("b"))
        return (low, high) if low < high else None
    return None


def format_duration(seconds: int) -> str:
    """Compact tag form: 90s, 30m, 1h, 1h30m, 3d."""
    if seconds % 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    if minutes % (24 * 60) == 0 and minutes >= 48 * 60:
        return f"{minutes // (24 * 60)}d"
    hours, rest = divmod(minutes, 60)
    return f"{hours}h{rest}m" if rest else f"{hours}h"


def format_duration_range(low: int, high: int) -> str:
    if low == high:
        return format_duration(high)
    lo, hi = format_duration(low), format_duration(high)
    # '35m-45m' reads better as '35-45m' when both are plain minutes.
    if lo.endswith("m") and hi.endswith("m") and "h" not in lo + hi:
        return f"{lo[:-1]}-{hi}"
    return f"{lo}-{hi}"


def human_duration(seconds: int) -> str:
    """Reader-facing: '45 min', '1 hr 15 min', '8 hr', '90 sec'."""
    if seconds < 60:
        return f"{seconds} sec"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} hr {rest} min" if rest else f"{hours} hr"


# --------------------------------------------------------------------------
# Temperatures
# --------------------------------------------------------------------------

_TEMP_RE = re.compile(r"^(\d{2,3})\s*°?\s*([FC])$", re.I)


def parse_temperature(text: str) -> tuple[int, str] | None:
    """'425F', '425°F', '220 C' -> (425, 'F'). None if not a temperature."""
    m = _TEMP_RE.match(text.strip())
    if not m:
        return None
    return int(m.group(1)), m.group(2).upper()


def to_fahrenheit(value: int, unit: str) -> int:
    if unit == "F":
        return value
    # Oven dials work in 5 degree steps.
    return int(5 * round((value * 9 / 5 + 32) / 5))
