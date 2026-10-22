"""Write a `Recipe` back to Markdown.

`parse_recipe(to_markdown(r))` gives back the same recipe. The editor and
the migration script both save through here.
"""

from __future__ import annotations

import json
import re
from typing import Any

import yaml

from . import units
from .model import Ingredient, Recipe, Step

KEY_ORDER = [
    "title", "course", "category", "tags", "yield", "max-yield", "hold",
    "summary", "description", "source", "image", "added", "storage",
    "nutrition", "nutrition-note", "review",
]


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _number(value)
    text = str(value)
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text  # YAML reads it as a date; the parser accepts that
    if "\n" not in text and text == text.strip() and text:
        try:
            if yaml.safe_load(text) == text:
                return text
        except yaml.YAMLError:
            pass
    return json.dumps(text, ensure_ascii=False)


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _yield(recipe: Recipe) -> str:
    count = recipe.yield_count
    return f"{_number(count) if float(count).is_integer() else units.format_amount(count)} {recipe.yield_noun}"


def front_matter(recipe: Recipe) -> str:
    fields: dict[str, Any] = {
        "title": recipe.title,
        "course": recipe.course,
        "category": recipe.category,
        "tags": recipe.tags or None,
        "yield": _yield(recipe),
        "max-yield": recipe.max_yield,
        "hold": units.format_duration(recipe.hold_s) if recipe.hold_s else None,
        "summary": recipe.summary,
        "description": recipe.description,
        "source": recipe.source,
        "image": recipe.image,
        "added": recipe.added,
        "storage": recipe.storage,
        "nutrition": recipe.nutrition,
        "nutrition-note": recipe.nutrition_note,
        "review": True if recipe.review else None,
    }
    lines = ["---"]
    for key in KEY_ORDER:
        value = fields[key]
        if value is None:
            continue
        if key == "tags":
            lines.append(f"tags: [{', '.join(value)}]")
        elif key == "nutrition":
            lines.append("nutrition:")
            for k, v in value.items():
                lines.append(f"  {k}: {_number(v)}")
        elif key == "yield":
            lines.append(f"yield: {_scalar(value)}")
        else:
            lines.append(f"{key}: {_scalar(value)}")
    for key, value in recipe.extra.items():
        lines.append(yaml.safe_dump({key: value}, sort_keys=False, allow_unicode=True,
                                    default_flow_style=None).strip())
    lines.append("---")
    return "\n".join(lines)


def ingredient_line(ing: Ingredient) -> str:
    if ing.raw:
        return ing.raw
    parts: list[str] = []
    if ing.amount is not None:
        amount = units.format_amount(ing.amount, ing.unit)
        if ing.amount_max is not None:
            amount += "-" + units.format_amount(ing.amount_max, ing.unit)
        parts.append(amount)
        if ing.unit:
            parts.append(units.unit_label(ing.unit, ing.amount_max or ing.amount))
    parts.append(ing.display_name(ing.amount_max or ing.amount))
    text = " ".join(parts)
    if ing.grams is not None:
        text += f" ({_number(round(ing.grams, 1))} g)"
    if ing.note:
        text += f" ({ing.note})"
    if ing.optional and not (ing.note and "optional" in ing.note.lower()):
        text += " [optional]"
    if ing.pantry:
        text += " [pantry]"
    return f"- {text}"


def step_tag(step: Step) -> str:
    items: list[str] = []
    if step.duration_s is not None:
        low = step.duration_min_s if step.duration_min_s is not None else step.duration_s
        items.append(units.format_duration_range(low, step.duration_s))
    if step.duration_s is not None or step.appliance is not None or step.mode_set:
        items.append(step.mode)
    if step.appliance is not None:
        items.append(step.appliance.label())
    items.extend("or " + f.label() for f in step.fallbacks)
    if step.with_step:
        items.append(f"with {step.with_step}")
    if step.after_step:
        items.append(f"after {step.after_step}")
    if step.ends_with:
        items.append(f"ends with {step.ends_with}")
    return "{" + ", ".join(items) + "}" if items else ""


def step_lines(step: Step) -> list[str]:
    body_lines = step.body.split("\n") if step.body else []
    first = f"{step.number}. **{step.lead}**"
    # 'Optional:' notes read best on their own line under the step.
    if body_lines and body_lines[0] and not body_lines[0].lower().startswith("optional:"):
        first += " " + body_lines.pop(0)
    tag = step_tag(step)
    if tag:
        first += " " + tag
    out = [first]
    for line in body_lines:
        out.append(f"   {line}" if line else "")
    return out


def to_markdown(recipe: Recipe) -> str:
    out = [front_matter(recipe), "", "## Ingredients"]
    group = None
    for ing in recipe.ingredients:
        if ing.group != group:
            group = ing.group
            out += ["", f"### {group}"] if group else [""]
        out.append(ingredient_line(ing))
    out += ["", "## Steps"]
    group = None
    for step in recipe.steps:
        if step.group != group:
            group = step.group
            out += ["", f"### {group}"] if group else [""]
        out += step_lines(step)
    if recipe.notes.strip():
        out += ["", "## Notes", "", recipe.notes.strip()]
    return "\n".join(_tidy(out)) + "\n"


def _tidy(lines: list[str]) -> list[str]:
    """Blank line after each heading, never two blank lines in a row."""
    out: list[str] = []
    for line in lines:
        if not line and out and not out[-1]:
            continue
        if out and out[-1].startswith("#") and line:
            out.append("")
        out.append(line)
    return out
