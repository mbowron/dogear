"""Scale a recipe to a number of servings and format it for display.

The browser never does unit math: it asks the server for a recipe at N
servings and shows the strings it gets back. The command line uses the same
functions, so what `python -m dogear show` prints is what the app shows.
"""

from __future__ import annotations

from typing import Any

from . import units
from .model import Ingredient, Recipe


def ingredient_text(ing: Ingredient, factor: float = 1.0) -> tuple[str, str]:
    """(amount, name) for display: ('1 1/2 lb', 'small Yukon Gold potatoes').

    The amount is '' for unmeasured lines ('salt to taste') and for lines the
    parser could not read, which are shown exactly as written.
    """
    if not ing.parsed:
        return "", (ing.raw or ing.name).lstrip("- ").strip()
    if ing.amount is None:
        return "", ing.name
    if not ing.scales:
        factor = 1.0

    amount, unit = ing.amount * factor, ing.unit
    if ing.amount_max is None and factor != 1:
        amount, unit = units.readable(amount, unit)
    text = units.format_amount(amount, unit)
    last = amount
    if ing.amount_max is not None:
        last = ing.amount_max * factor
        text += "–" + units.format_amount(last, unit)
    if unit:
        text += " " + units.unit_label(unit, last)
    return text, ing.display_name(last)


def clamp_servings(recipe: Recipe, servings: float | None) -> float:
    if not servings or servings <= 0:
        return recipe.yield_count
    return min(float(servings), recipe.max_yield_value)


def scaled_view(recipe: Recipe, servings: float | None = None) -> dict[str, Any]:
    """The parts of a recipe that change with servings, ready to show."""
    count = clamp_servings(recipe, servings)
    factor = count / recipe.yield_count if recipe.yield_count else 1.0
    ingredients = []
    for ing in recipe.ingredients:
        amount, name = ingredient_text(ing, factor)
        grams = round(ing.grams * factor) if ing.grams and ing.scales else ing.grams
        ingredients.append({
            "amount": amount, "name": name, "item": ing.item, "note": ing.note,
            "grams": grams, "pantry": ing.pantry, "optional": ing.optional,
            "group": ing.group,
        })
    return {
        "servings": count,
        "factor": factor,
        "yieldLabel": f"{units.format_amount(count)} {recipe.yield_noun}",
        "ingredients": ingredients,
    }
