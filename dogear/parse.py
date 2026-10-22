"""Read a recipe Markdown file into a `Recipe`.

The format is documented in docs/RECIPE-FORMAT.md. Change both together.

Problems are collected, not raised: an `error` means the recipe cannot be
used, a `warning` means it works but something is probably wrong, and a
`note` points out something Dogear guessed (shown by `check --strict`).
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import units
from .model import (
    COURSES, EQUIPMENT, EQUIPMENT_ALIASES, PASSIVE_EQUIPMENT, Appliance,
    Fallback, Ingredient, Issue, Recipe, Step,
)
from .text import singular, tag_name

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

KNOWN_KEYS = {
    "title", "course", "category", "tags", "yield", "max-yield", "hold",
    "summary", "description", "source", "image", "added", "nutrition",
    "nutrition-note", "storage", "review",
}

SECTION_ALIASES = {
    "ingredients": "ingredients",
    "steps": "steps", "method": "steps", "directions": "steps", "instructions": "steps",
    "notes": "notes", "tips": "notes", "adjustments": "notes",
}

PASSIVE_WORDS = re.compile(
    r"\b(rest|rests|resting|soak|soaks|soaking|marinate|marinates|marinating|"
    r"chill|chills|chilling|cool|cools|cooling|rise|rises|proof|proofs|steep|"
    r"steeps|refrigerate|refrigerates|freeze|freezes|bake|bakes|baking|roast|"
    r"roasts|roasting|set aside|sit|sits|overnight|simmer|simmers|braise|braises)\b",
    re.I,
)


@dataclass
class ParseResult:
    recipe: Recipe | None
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.recipe is not None and not any(i.level == "error" for i in self.issues)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]


class _Collector:
    def __init__(self) -> None:
        self.issues: list[Issue] = []

    def error(self, message: str, line: int | None = None) -> None:
        self.issues.append(Issue("error", message, line))

    def warning(self, message: str, line: int | None = None) -> None:
        self.issues.append(Issue("warning", message, line))

    def note(self, message: str, line: int | None = None) -> None:
        self.issues.append(Issue("note", message, line))


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------


def parse_file(path: str | Path) -> ParseResult:
    path = Path(path)
    return parse_recipe(path.read_text(encoding="utf-8"), path.stem)


def load_dir(directory: str | Path) -> dict[str, ParseResult]:
    """Parse every recipe in a folder, keyed by slug, in file name order."""
    return {p.stem: parse_file(p) for p in sorted(Path(directory).glob("*.md"))}


def parse_recipe(text: str, slug: str) -> ParseResult:
    c = _Collector()
    if not SLUG_RE.match(slug):
        c.error(f"file name {slug!r} must be lowercase letters, digits and hyphens")

    text = text.replace("\r\n", "\n").lstrip("﻿")
    fm_text, body, body_line = _split_front_matter(text, c)
    if fm_text is None:
        return ParseResult(None, c.issues)
    try:
        meta = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        c.error(f"front matter is not valid YAML: {getattr(exc, 'problem', exc)}",
                mark.line + 2 if mark else None)
        return ParseResult(None, c.issues)
    if not isinstance(meta, dict):
        c.error("front matter must be a list of 'key: value' lines", 1)
        return ParseResult(None, c.issues)

    recipe = _parse_meta(meta, slug, c)
    sections = _split_sections(body, body_line, c)

    for raw_line, line_no, group in _section_lines(sections.get("ingredients", [])):
        ing = parse_ingredient(raw_line, group=group, line=line_no, issues=c)
        if ing is not None:
            recipe.ingredients.append(ing)
    recipe.steps = _parse_steps(sections.get("steps", []), c)
    recipe.notes = "\n".join(t for t, _ in sections.get("notes", [])).strip()

    if "ingredients" not in sections or not recipe.ingredients:
        c.error("the recipe has no ingredients (add a '## Ingredients' list)")
    if "steps" not in sections or not recipe.steps:
        c.error("the recipe has no steps (add a '## Steps' numbered list)")
    _check_timing(recipe, c)
    return ParseResult(recipe, c.issues)


# --------------------------------------------------------------------------
# Front matter
# --------------------------------------------------------------------------


def _split_front_matter(text: str, c: _Collector) -> tuple[str | None, str, int]:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        c.error("the file must start with a front matter block between '---' lines", 1)
        return None, "", 1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:]), i + 2
    c.error("the front matter block is never closed with '---'", 1)
    return None, "", 1


def _parse_meta(meta: dict, slug: str, c: _Collector) -> Recipe:
    title = meta.get("title")
    if not isinstance(title, str) or not title.strip():
        c.error("'title' is required")
        title = slug
    r = Recipe(slug=slug, title=str(title).strip())

    y = meta.get("yield")
    if y is None:
        c.error("'yield' is required, for example 'yield: 4 servings'")
    else:
        low, _high, noun = units.split_amount(str(y))
        if low is None or low <= 0:
            c.error(f"'yield' must start with a number, for example '4 servings' (got {y!r})")
        else:
            r.yield_count = low
            r.yield_noun = noun or "servings"

    if "max-yield" in meta:
        try:
            r.max_yield = float(meta["max-yield"])
            if r.max_yield < r.yield_count:
                c.warning("'max-yield' is smaller than 'yield'")
        except (TypeError, ValueError):
            c.warning(f"'max-yield' must be a number (got {meta['max-yield']!r})")

    if "hold" in meta and meta["hold"] not in (None, "", 0):
        d = units.parse_duration(str(meta["hold"]))
        if d is None:
            c.warning(f"'hold' must be a time such as 15m or 1h (got {meta['hold']!r})")
        else:
            r.hold_s = d[1]

    course = str(meta.get("course") or "main").strip().lower()
    if course not in COURSES:
        c.warning(f"unknown course {course!r}; use one of: {', '.join(COURSES)}")
    r.course = course

    for key, attr in (("category", "category"), ("summary", "summary"),
                      ("description", "description"), ("source", "source"),
                      ("image", "image"), ("nutrition-note", "nutrition_note"),
                      ("storage", "storage")):
        value = meta.get(key)
        if value is not None and str(value).strip():
            setattr(r, attr, str(value).strip())
    if r.summary and len(r.summary) > 140:
        c.warning(f"'summary' is {len(r.summary)} characters; cards show about 140")

    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [t for t in tags.split(",")]
    if not isinstance(tags, list):
        c.warning("'tags' must be a list such as [weeknight, vegetarian]")
        tags = []
    seen: list[str] = []
    for t in tags:
        name = tag_name(t)
        if name and name not in seen:
            seen.append(name)
    r.tags = seen

    added = meta.get("added")
    if isinstance(added, (dt.date, dt.datetime)):
        r.added = added.strftime("%Y-%m-%d")
    elif added:
        try:
            r.added = dt.date.fromisoformat(str(added)).isoformat()
        except ValueError:
            c.warning(f"'added' must be a date like 2026-10-21 (got {added!r})")

    nutrition = meta.get("nutrition")
    if nutrition is not None:
        if not isinstance(nutrition, dict):
            c.warning("'nutrition' must be a nested block of numbers")
        else:
            clean = {}
            for k, v in nutrition.items():
                try:
                    clean[str(k)] = float(v)
                except (TypeError, ValueError):
                    c.warning(f"nutrition {k!r} must be a number (got {v!r})")
            r.nutrition = clean or None

    review = meta.get("review", False)
    r.review = bool(review) if isinstance(review, bool) else str(review).lower() in ("true", "yes")

    for key in meta:
        if key not in KNOWN_KEYS:
            c.warning(f"unknown front matter key {key!r} (kept, but not used)")
            r.extra[key] = meta[key]
    return r


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------


def _split_sections(body: str, first_line: int, c: _Collector) -> dict[str, list[tuple[str, int]]]:
    sections: dict[str, list[tuple[str, int]]] = {}
    current: str | None = None
    for offset, line in enumerate(body.split("\n")):
        line_no = first_line + offset
        m = re.match(r"^##\s+(.+?)\s*#*\s*$", line)
        if m and not line.startswith("###"):
            name = SECTION_ALIASES.get(m.group(1).strip().lower())
            if name is None:
                c.error(f"unknown section '## {m.group(1).strip()}' "
                        "(use Ingredients, Steps and Notes)", line_no)
                current = "_ignored"
            elif name in sections:
                c.error(f"section '## {m.group(1).strip()}' appears twice", line_no)
                current = "_ignored"
            else:
                current = name
                sections[name] = []
            continue
        if current is None:
            if line.strip():
                c.warning("text before the first section is ignored", line_no)
                current = "_ignored"
            continue
        if current != "_ignored":
            sections[current].append((line, line_no))
    return sections


def _section_lines(lines: list[tuple[str, int]]):
    """Yield (text, line, group) for each list item, tracking ### groups."""
    group = None
    for text, line_no in lines:
        stripped = text.strip()
        if not stripped:
            continue
        m = re.match(r"^###\s+(.+?)\s*#*$", stripped)
        if m:
            group = m.group(1).strip().rstrip(":")
            continue
        yield stripped, line_no, group


# --------------------------------------------------------------------------
# Ingredients
# --------------------------------------------------------------------------

_FLAG_RE = re.compile(r"\s*\[(pantry|optional)\]\s*$", re.I)
_TRAILING_PAREN_RE = re.compile(r"\s*\(([^()]*)\)\s*$")
_GRAMS_RE = re.compile(r"^(?:about\s+|~\s*)?(\d+(?:\.\d+)?)\s*(?:g|grams?)$", re.I)


def parse_ingredient(text: str, group: str | None = None, line: int | None = None,
                     issues: _Collector | None = None) -> Ingredient | None:
    """Parse one ingredient line such as '2-3 cloves garlic, minced [pantry]'."""
    c = issues or _Collector()
    raw = text.strip()
    body = re.sub(r"^[-*+]\s+", "", raw)
    if not body:
        return None
    if body == raw and not re.match(r"^\d", raw):
        # Not a list item. Accept it, but it is probably a stray sentence.
        c.warning("ingredient lines should start with '- '", line)

    pantry = optional = False
    while True:
        m = _FLAG_RE.search(body)
        if not m:
            break
        if m.group(1).lower() == "pantry":
            pantry = True
        else:
            optional = True
        body = body[: m.start()]

    notes: list[str] = []
    grams = None
    while True:
        m = _TRAILING_PAREN_RE.search(body)
        if not m:
            break
        inner = m.group(1).strip()
        g = _GRAMS_RE.match(inner)
        if g and grams is None:
            grams = float(g.group(1))
        elif inner:
            notes.insert(0, inner)
        body = body[: m.start()]
    if re.search(r"\boptional\b", " ".join(notes), re.I):
        optional = True

    amount, amount_max, rest = units.split_amount(body)
    if amount is None:
        a = re.match(r"^(a|an)\s+(\S+)\s+(.+)$", rest, re.I)
        if a and units.canonical_unit(a.group(2)):
            amount, rest = 1.0, f"{a.group(2)} {a.group(3)}"

    # '1 (14.5 oz) can tomatoes': the package size becomes a note.
    m = re.match(r"^\(([^()]*)\)\s*", rest)
    if amount is not None and m:
        notes.insert(0, m.group(1).strip())
        rest = rest[m.end():]

    unit = None
    if amount is not None:
        unit, rest = _take_unit(rest)
        # '2 cans (15 oz each) beans', '1 1/2 cups (180 g) flour'
        m = re.match(r"^\(([^()]*)\)\s*", rest)
        if unit and m:
            inner = m.group(1).strip()
            g = _GRAMS_RE.match(inner)
            if g and grams is None:
                grams = float(g.group(1))
            elif inner:
                notes.insert(0, inner)
            rest = rest[m.end():]

    name = rest.strip()
    parsed = True
    if amount is not None and not name:
        if unit:  # '2 cloves' alone is the spice, not garlic
            name, unit = units.unit_label(unit, amount), None
        else:
            c.warning(f"ingredient {raw!r} has an amount but no name", line)
            name, parsed, amount, amount_max = raw.lstrip("-*+ ").strip(), False, None, None
    if amount is None and re.match(r"^\d", body.strip()):
        c.warning(f"could not read the amount in {raw!r}; it is shown as written "
                  "and will not scale", line)
        parsed = False
    if amount is not None and unit is None and amount > 1:
        name = _singular_noun(name)

    if grams is not None and unit is None and amount is None:
        c.warning(f"gram weight in {raw!r} has no amount to scale with", line)

    return Ingredient(
        raw=raw if raw.startswith(("-", "*", "+")) else f"- {raw}",
        name=name, amount=amount, amount_max=amount_max, unit=unit,
        note="; ".join(notes) or None, grams=grams, pantry=pantry,
        optional=optional, group=group, parsed=parsed, line=line,
    )


def _take_unit(text: str) -> tuple[str | None, str]:
    words = text.split()
    for n in (3, 2, 1):  # 'fl. oz.' and 'fluid ounces' are two words
        if len(words) < n:
            continue
        unit = units.canonical_unit(" ".join(words[:n]))
        if unit:
            rest = words[n:]
            if rest and rest[0].lower() == "of":
                rest = rest[1:]
            return unit, " ".join(rest)
    return None, text


def _singular_noun(name: str) -> str:
    """'4 chicken thighs, bone-in' is stored as 'chicken thigh, bone-in'."""
    head, sep, tail = name.partition(",")
    words = head.rstrip().split(" ")
    words[-1] = singular(words[-1])
    return " ".join(words) + (sep + tail if sep else "")


# --------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------

_STEP_START_RE = re.compile(r"^(\d+)[.)]\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*+]\s+(.*)$")
_TAG_RE = re.compile(r"\{([^{}]*)\}")


def _parse_steps(lines: list[tuple[str, int]], c: _Collector) -> list[Step]:
    blocks: list[tuple[list[str], int, str | None]] = []
    group = None
    warned_bullets = False
    for text, line_no in lines:
        if not text.strip():
            if blocks:
                blocks[-1][0].append("")
            continue
        heading = re.match(r"^###\s+(.+?)\s*#*$", text.strip())
        if heading:
            group = heading.group(1).strip().rstrip(":")
            continue
        indented = text[:1] in (" ", "\t")
        m = _STEP_START_RE.match(text) if not indented else None
        b = _BULLET_RE.match(text) if not indented else None
        if m:
            blocks.append(([m.group(2)], line_no, group))
        elif b:
            if not warned_bullets:
                c.warning("steps should be a numbered list (1. 2. 3.)", line_no)
                warned_bullets = True
            blocks.append(([b.group(1)], line_no, group))
        elif blocks:
            blocks[-1][0].append(text.strip())
        else:
            c.warning("text in Steps before the first numbered step is ignored", line_no)

    steps = []
    for number, (parts, line_no, grp) in enumerate(blocks, start=1):
        while parts and not parts[-1]:
            parts.pop()
        steps.append(_parse_step(number, "\n".join(parts), line_no, grp, c))
    return steps


def _parse_step(number: int, text: str, line: int, group: str | None, c: _Collector) -> Step:
    tags = _TAG_RE.findall(text)
    if len(tags) > 1:
        c.error(f"step {number} has {len(tags)} {{...}} tags; put everything in one", line)
    text = _TAG_RE.sub("", text)
    text = re.sub(r"[ \t]+\n", "\n", text).strip()
    text = re.sub(r"[ \t]{2,}", " ", text)

    m = re.match(r"^\*\*(.+?)\*\*\s*(.*)$", text, re.S)
    if m:
        lead, body = m.group(1).strip(), m.group(2).strip()
    else:
        first, _, rest = text.partition("\n")
        s = re.match(r"^(.+?[.!?])\s+(.*)$", first)
        lead, body = (s.group(1), (s.group(2) + "\n" + rest).strip()) if s else (first, rest.strip())
        c.note(f"step {number} has no bold lead sentence; using {lead!r}", line)

    step = Step(number=number, lead=lead, body=body, group=group, line=line)
    if tags:
        _apply_tag(step, tags[0], line, c)
    if not step.mode_set:
        passive = (step.appliance is not None and step.appliance.kind in PASSIVE_EQUIPMENT) \
            or bool(PASSIVE_WORDS.search(step.lead))
        step.mode = "passive" if passive else "active"
        if step.duration_s:
            c.note(f"step {number}: mode not given, assumed {step.mode}", line)
    return step


def _apply_tag(step: Step, content: str, line: int, c: _Collector) -> None:
    n = step.number
    for item in (i.strip() for i in content.split(",")):
        if not item:
            continue
        low = item.lower()
        if low in ("active", "hands-on"):
            step.mode, step.mode_set = "active", True
        elif low in ("passive", "hands-off"):
            step.mode, step.mode_set = "passive", True
        elif m := re.match(r"^ends?\s+with\s+(?:step\s+)?(\d+)$", low):
            step.ends_with = _step_ref(n, int(m.group(1)), line, c)
        elif m := re.match(r"^with\s+(?:step\s+)?(\d+)$", low):
            step.with_step = _step_ref(n, int(m.group(1)), line, c)
        elif m := re.match(r"^after\s+(?:step\s+)?(\d+)$", low):
            step.after_step = _step_ref(n, int(m.group(1)), line, c)
        elif low.startswith("or "):
            app, dur, problem = parse_appliance(item[3:], allow_duration=True)
            if app is None:
                c.error(f"step {n}: could not read fallback {item!r}: {problem}", line)
            else:
                _check_appliance(n, app, line, c)
                step.fallbacks.append(Fallback(app, dur[1] if dur else None,
                                               dur[0] if dur and dur[0] != dur[1] else None))
        elif (d := units.parse_duration(item)) is not None:
            if step.duration_s is not None:
                c.error(f"step {n} has two durations", line)
            step.duration_s = d[1]
            step.duration_min_s = d[0] if d[0] != d[1] else None
        else:
            app, dur, problem = parse_appliance(item, allow_duration=False)
            if app is None:
                c.error(f"step {n}: did not understand {item!r} in the {{...}} tag", line)
            elif step.appliance is not None:
                c.error(f"step {n} names two appliances; use 'or' for a fallback", line)
            else:
                _check_appliance(n, app, line, c)
                step.appliance = app
    if sum(bool(x) for x in (step.with_step, step.after_step, step.ends_with)) > 1:
        c.error(f"step {n} can use only one of 'with', 'after' and 'ends with'", line)
    if step.fallbacks and step.appliance is None:
        c.error(f"step {n} has an 'or' fallback but no main appliance", line)


def _step_ref(number: int, ref: int, line: int, c: _Collector) -> int | None:
    if not 1 <= ref < number:
        c.error(f"step {number} refers to step {ref}; it can only refer to an earlier step", line)
        return None
    return ref


def _check_appliance(number: int, app: Appliance, line: int, c: _Collector) -> None:
    _name, takes_temp, _counted = EQUIPMENT[app.kind]
    if app.temp is not None and not takes_temp:
        c.warning(f"step {number}: a {app.name} has no temperature setting", line)
    if takes_temp and app.temp is None and not app.broil and app.kind in (
            "oven", "toaster-oven", "air-fryer"):
        c.warning(f"step {number}: {app.name} has no temperature (for example "
                  f"'{app.name} 400F')", line)
    if app.temp_f is not None and not 90 <= app.temp_f <= 600:
        c.warning(f"step {number}: {app.temp}{app.temp_unit} looks wrong for an appliance", line)


def parse_appliance(text: str, allow_duration: bool = False):
    """Parse 'oven 425F', 'burner x2', '2 burners', 'air fryer 380F 14m'.

    Returns (Appliance | None, duration (low, high) | None, problem text).
    """
    low = text.strip().lower()
    count = 1
    m = re.match(r"^(\d+)\s+(.*)$", low)
    if m:
        count, low = int(m.group(1)), m.group(2)
    kind = None
    rest = ""
    for alias in sorted(EQUIPMENT_ALIASES, key=len, reverse=True):
        if low == alias or low.startswith(alias + " "):
            kind, rest = EQUIPMENT_ALIASES[alias], low[len(alias):].strip()
            break
    if kind is None:
        return None, None, "unknown appliance"
    app = Appliance(kind=kind, count=count)
    if low.startswith("broiler"):
        app.broil = True
    rest = re.sub(r"(\d)\s*°?\s*([fc])\b", r"\1\2", rest)
    leftover: list[str] = []
    for token in rest.split():
        if m := re.match(r"^x(\d+)$", token):
            app.count = int(m.group(1))
        elif token == "broil":
            app.broil = True
        elif (t := units.parse_temperature(token)) is not None:
            app.temp, app.temp_unit = t
        else:
            leftover.append(token)
    duration = None
    if leftover:
        if not allow_duration:
            return None, None, f"unexpected {' '.join(leftover)!r}"
        duration = units.parse_duration(" ".join(leftover))
        if duration is None:
            return None, None, f"unexpected {' '.join(leftover)!r}"
    return app, duration, ""


# --------------------------------------------------------------------------
# Whole-recipe timing checks
# --------------------------------------------------------------------------


def _check_timing(recipe: Recipe, c: _Collector) -> None:
    if not recipe.steps:
        return
    timed = [s for s in recipe.steps if s.duration_s]
    if not timed:
        c.warning("no step has a duration, so there is no timeline; add tags such "
                  "as {10m, active}")
        return
    untimed = [str(s.number) for s in recipe.steps[:-1] if s.duration_s is None]
    if untimed:
        c.note(f"steps without a duration are treated as instant: {', '.join(untimed)}")
