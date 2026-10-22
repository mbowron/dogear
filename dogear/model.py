"""The recipe data model and its JSON shape.

`Recipe.to_dict()` is the contract between the server and the browser.
Change it and the front end together.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import units
from .text import plural

# --------------------------------------------------------------------------
# Equipment
# --------------------------------------------------------------------------

# canonical id -> (display name, takes a temperature, counted by the kitchen)
EQUIPMENT: dict[str, tuple[str, bool, bool]] = {
    "oven": ("oven", True, True),
    "toaster-oven": ("toaster oven", True, True),
    "air-fryer": ("air fryer", True, True),
    "burner": ("burner", False, True),
    "grill": ("grill", True, True),
    "smoker": ("smoker", True, True),
    "microwave": ("microwave", False, True),
    "slow-cooker": ("slow cooker", False, True),
    "pressure-cooker": ("pressure cooker", False, True),
    "fridge": ("fridge", False, False),
    "freezer": ("freezer", False, False),
}

EQUIPMENT_ALIASES: dict[str, str] = {
    "oven": "oven", "range oven": "oven", "broiler": "oven",
    "toaster oven": "toaster-oven", "toaster-oven": "toaster-oven", "toaster": "toaster-oven",
    "air fryer": "air-fryer", "air-fryer": "air-fryer", "airfryer": "air-fryer",
    "burner": "burner", "burners": "burner", "stove": "burner", "stovetop": "burner",
    "cooktop": "burner", "hob": "burner",
    "grill": "grill", "smoker": "smoker", "microwave": "microwave",
    "slow cooker": "slow-cooker", "slow-cooker": "slow-cooker", "crockpot": "slow-cooker",
    "crock pot": "slow-cooker",
    "pressure cooker": "pressure-cooker", "pressure-cooker": "pressure-cooker",
    "instant pot": "pressure-cooker", "instant-pot": "pressure-cooker",
    "fridge": "fridge", "refrigerator": "fridge", "freezer": "freezer",
}

# Equipment that usually means the cook can walk away.
PASSIVE_EQUIPMENT = {
    "oven", "toaster-oven", "air-fryer", "smoker", "slow-cooker",
    "pressure-cooker", "fridge", "freezer", "microwave",
}

COURSES = [
    "main", "side", "soup", "salad", "bread", "sauce", "appetizer",
    "dessert", "drink", "breakfast", "snack",
]

DEFAULT_KITCHEN = {"oven": 1, "toaster-oven": 1, "air-fryer": 1, "burner": 4}


@dataclass
class Appliance:
    kind: str                     # key of EQUIPMENT
    temp: int | None = None       # in temp_unit
    temp_unit: str | None = None  # "F" or "C"
    broil: bool = False
    count: int = 1                # burners x2

    @property
    def name(self) -> str:
        return EQUIPMENT[self.kind][0]

    @property
    def temp_f(self) -> int | None:
        if self.temp is None:
            return None
        return units.to_fahrenheit(self.temp, self.temp_unit or "F")

    @property
    def setting(self) -> str | None:
        """What the dial is set to, for conflict checks: '425F', 'broil'."""
        if self.broil:
            return "broil"
        return f"{self.temp_f}F" if self.temp is not None else None

    def label(self) -> str:
        """Tag form: 'oven 425F', 'burner x2', 'oven broil'."""
        parts = [self.name]
        if self.count > 1:
            parts.append(f"x{self.count}")
        if self.broil:
            parts.append("broil")
        elif self.temp is not None:
            parts.append(f"{self.temp}{self.temp_unit or 'F'}")
        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "name": self.name, "temp": self.temp,
            "tempUnit": self.temp_unit, "tempF": self.temp_f, "broil": self.broil,
            "count": self.count, "setting": self.setting, "label": self.label(),
        }


@dataclass
class Fallback:
    """Another appliance the step can use, with its own temperature and time."""

    appliance: Appliance
    duration_s: int | None = None
    duration_min_s: int | None = None

    def label(self) -> str:
        text = self.appliance.label()
        if self.duration_s is not None:
            low = self.duration_min_s if self.duration_min_s is not None else self.duration_s
            text += " " + units.format_duration_range(low, self.duration_s)
        return text

    def to_dict(self) -> dict[str, Any]:
        return {
            "appliance": self.appliance.to_dict(),
            "durationS": self.duration_s, "durationMinS": self.duration_min_s,
            "label": self.label(),
        }


# --------------------------------------------------------------------------
# Ingredients and steps
# --------------------------------------------------------------------------


@dataclass
class Ingredient:
    raw: str | None               # the line as written; None when built in the app
    name: str                     # display name, noun singular for counted items
    amount: float | None = None   # amount for the recipe's default yield
    amount_max: float | None = None  # upper end of a range ("2-3 cloves")
    unit: str | None = None       # canonical unit, None for counted items
    note: str | None = None       # parenthetical that is not a gram weight
    grams: float | None = None    # gram weight for the default yield
    pantry: bool = False          # left off the shopping list by default
    optional: bool = False
    group: str | None = None      # '### Sauce' heading it sits under
    parsed: bool = True           # False: shown as written, never scaled
    line: int | None = None

    @property
    def item(self) -> str:
        """The shopping name: the part before the first comma, lowercase."""
        return self.name.split(",", 1)[0].strip().lower()

    @property
    def scales(self) -> bool:
        # 'a pinch' stays a pinch; '4 pinches' (one per jar) scales.
        if self.unit in units.NO_SCALE and (self.amount or 0) <= 1:
            return False
        return self.parsed and self.amount is not None

    def display_name(self, amount: float | None) -> str:
        """Pluralize the noun of a counted item: '2 eggs', '4 chicken thighs, bone-in'."""
        if self.unit is not None or amount is None or amount <= 1:
            return self.name
        head, sep, tail = self.name.partition(",")
        words = head.rstrip().split(" ")
        words[-1] = plural(words[-1])
        return " ".join(words) + (sep + tail if sep else "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw, "name": self.name, "item": self.item,
            "amount": self.amount, "amountMax": self.amount_max, "unit": self.unit,
            "unitKind": units.unit_kind(self.unit) if self.unit else None,
            "note": self.note, "grams": self.grams, "pantry": self.pantry,
            "optional": self.optional, "group": self.group, "parsed": self.parsed,
            "scales": self.scales,
        }


@dataclass
class Step:
    number: int                    # 1-based position in the recipe
    lead: str                      # the bold first sentence, without the asterisks
    body: str = ""                 # the rest, Markdown, may span lines
    duration_s: int | None = None  # upper bound used for scheduling
    duration_min_s: int | None = None  # lower bound when a range was written
    mode: str = "active"           # "active" (hands busy) or "passive"
    mode_set: bool = False         # False when inferred
    appliance: Appliance | None = None
    fallbacks: list[Fallback] = field(default_factory=list)
    with_step: int | None = None   # starts when this earlier step starts
    after_step: int | None = None  # starts when this earlier step ends
    ends_with: int | None = None   # ends when this earlier step ends
    group: str | None = None       # '### Make the sauce' heading it sits under
    line: int | None = None

    @property
    def timer_s(self) -> int | None:
        """Timers go off at the low end of a range: check early."""
        if self.duration_min_s is not None:
            return self.duration_min_s
        return self.duration_s

    @property
    def optional(self) -> bool:
        return self.lead.lower().startswith("optional")

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number, "lead": self.lead, "body": self.body,
            "durationS": self.duration_s, "durationMinS": self.duration_min_s,
            "timerS": self.timer_s, "mode": self.mode, "modeSet": self.mode_set,
            "appliance": self.appliance.to_dict() if self.appliance else None,
            "fallbacks": [f.to_dict() for f in self.fallbacks],
            "withStep": self.with_step, "afterStep": self.after_step,
            "endsWith": self.ends_with,
            "group": self.group,
        }


# --------------------------------------------------------------------------
# Recipe
# --------------------------------------------------------------------------


@dataclass
class Issue:
    level: str          # "error" or "warning"
    message: str
    line: int | None = None

    def __str__(self) -> str:
        where = f"line {self.line}: " if self.line else ""
        return f"{self.level}: {where}{self.message}"


@dataclass
class Recipe:
    slug: str
    title: str
    yield_count: float = 4
    yield_noun: str = "servings"
    course: str = "main"
    category: str | None = None
    tags: list[str] = field(default_factory=list)
    max_yield: float | None = None
    hold_s: int = 0
    summary: str | None = None
    description: str | None = None
    source: str | None = None
    image: str | None = None
    added: str | None = None
    nutrition: dict[str, float] | None = None
    nutrition_note: str | None = None
    storage: str | None = None
    review: bool = False
    ingredients: list[Ingredient] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)  # unknown front matter, kept on save

    @property
    def max_yield_value(self) -> float:
        return self.max_yield if self.max_yield else max(12, self.yield_count * 2)

    @property
    def yield_label(self) -> str:
        return f"{units.format_amount(self.yield_count)} {self.yield_noun}"

    def to_dict(self) -> dict[str, Any]:
        from .schedule import plan  # local import: schedule imports model

        p = plan(self)
        return {
            "slug": self.slug, "title": self.title, "course": self.course,
            "category": self.category, "tags": self.tags,
            "yield": {"count": self.yield_count, "noun": self.yield_noun,
                      "max": self.max_yield_value},
            "holdS": self.hold_s, "summary": self.summary,
            "description": self.description, "source": self.source,
            "image": self.image, "added": self.added, "nutrition": self.nutrition,
            "nutritionNote": self.nutrition_note, "storage": self.storage,
            "review": self.review,
            "ingredients": [i.to_dict() for i in self.ingredients],
            "steps": [s.to_dict() for s in self.steps],
            "notes": self.notes,
            "timing": {"totalS": p.total_s, "activeS": p.active_s,
                       "steps": [t.to_dict() for t in p.steps]},
        }
