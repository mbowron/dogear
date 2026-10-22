import pytest

from dogear import units
from dogear.units import Quantity


@pytest.mark.parametrize("text, low, high, rest", [
    ("1 1/2 cups flour", 1.5, None, "cups flour"),
    ("½ cup oats", 0.5, None, "cup oats"),
    ("1½ cups milk", 1.5, None, "cups milk"),
    ("2-3 cloves garlic", 2, 3, "cloves garlic"),
    ("2–3 cloves garlic", 2, 3, "cloves garlic"),
    ("1 to 2 tsp salt", 1, 2, "tsp salt"),
    (".5 tsp salt", 0.5, None, "tsp salt"),
    ("3 eggs", 3, None, "eggs"),
    ("1-inch piece ginger", None, None, "1-inch piece ginger"),
    ("salt to taste", None, None, "salt to taste"),
])
def test_split_amount(text, low, high, rest):
    a, b, r = units.split_amount(text)
    assert a == (pytest.approx(low) if low is not None else None)
    assert b == (pytest.approx(high) if high is not None else None)
    assert r == rest


@pytest.mark.parametrize("value, unit, expected", [
    (1 / 3, None, "1/3"),
    (2.5, "cup", "2 1/2"),
    (0.125, "tsp", "1/8"),
    (1.999, None, "2"),
    (0.66, "cup", "2/3"),
    (250.4, "g", "250"),
    (7.5, "g", "7.5"),
    (24.2, None, "24"),
    (0.02, "cup", "0.02"),
])
def test_format_amount(value, unit, expected):
    assert units.format_amount(value, unit) == expected


@pytest.mark.parametrize("text, expected", [
    ("30m", (1800, 1800)),
    ("1h30m", (5400, 5400)),
    ("1h10m", (4200, 4200)),
    ("1h 30m", (5400, 5400)),
    ("90s", (90, 90)),
    ("1.5h", (5400, 5400)),
    ("45 min", (2700, 2700)),
    ("35-45m", (2100, 2700)),
    ("45m-1h", (2700, 3600)),
    ("8h", (28800, 28800)),
    ("2d", (172800, 172800)),
    ("45-30m", None),
    ("oven", None),
    ("30", None),
])
def test_parse_duration(text, expected):
    assert units.parse_duration(text) == expected


@pytest.mark.parametrize("seconds", [90, 1800, 3600, 4200, 28800, 172800])
def test_format_duration_round_trips(seconds):
    assert units.parse_duration(units.format_duration(seconds)) == (seconds, seconds)


def test_format_duration_range():
    assert units.format_duration_range(2100, 2700) == "35-45m"
    assert units.format_duration_range(2700, 3600) == "45m-1h"
    assert units.format_duration_range(600, 600) == "10m"


@pytest.mark.parametrize("amount, unit, expected", [
    (4, "tbsp", (0.25, "cup")),
    (10, "tbsp", (10, "tbsp")),
    (6, "tsp", (2, "tbsp")),
    (0.125, "cup", (2, "tbsp")),
    (1.5, "tsp", (1.5, "tsp")),
    (48, "tsp", (1, "cup")),
    (3, "lb", (3, "lb")),
])
def test_readable(amount, unit, expected):
    value, u = units.readable(amount, unit)
    assert (round(value, 3), u) == (pytest.approx(expected[0], abs=1e-3), expected[1])


def test_merge_same_kind_converts():
    [q] = units.merge_quantities([Quantity(1, "cup"), Quantity(8, "tbsp")])
    assert q.unit == "cup" and q.amount == pytest.approx(1.5)
    [q] = units.merge_quantities([Quantity(1, "lb"), Quantity(8, "oz")])
    assert q.unit == "lb" and q.amount == pytest.approx(1.5)


def test_merge_metric_stays_metric():
    [q] = units.merge_quantities([Quantity(200, "ml"), Quantity(300, "ml")])
    assert (q.amount, q.unit) == (pytest.approx(500), "ml")
    [q] = units.merge_quantities([Quantity(600, "g"), Quantity(0.5, "kg")])
    assert (q.amount, q.unit) == (pytest.approx(1.1), "kg")


def test_merge_never_converts_volume_to_weight():
    out = units.merge_quantities([Quantity(1, "cup"), Quantity(100, "g")])
    assert {q.unit for q in out} == {"cup", "g"}


def test_merge_counts_and_unmeasured():
    out = units.merge_quantities([Quantity(1, "can"), Quantity(2, "can"), Quantity(3, None)])
    assert {(q.unit, q.amount) for q in out} == {("can", 3), (None, 3)}
    assert units.merge_quantities([Quantity(None, None), Quantity(None, None)]) == [Quantity(None, None)]


def test_temperatures():
    assert units.parse_temperature("425F") == (425, "F")
    assert units.parse_temperature("425°F") == (425, "F")
    assert units.parse_temperature("220 c") == (220, "C")
    assert units.parse_temperature("hot") is None
    assert units.to_fahrenheit(220, "C") == 430
    assert units.to_fahrenheit(180, "C") == 355


def test_unit_aliases():
    assert units.canonical_unit("T") == "tbsp"
    assert units.canonical_unit("t") == "tsp"
    assert units.canonical_unit("Tablespoons") == "tbsp"
    assert units.canonical_unit("fl. oz.") == "fl oz"
    assert units.canonical_unit("lbs") == "lb"
    assert units.canonical_unit("large") is None
