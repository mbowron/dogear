"""Small English and naming helpers: plurals, slugs, tag names."""

from __future__ import annotations

import re
import unicodedata

_IRREGULAR = {
    "leaf": "leaves", "loaf": "loaves", "half": "halves", "knife": "knives",
    "potato": "potatoes", "tomato": "tomatoes", "mango": "mangoes",
    "radish": "radishes", "dish": "dishes", "peach": "peaches",
    "anchovy": "anchovies", "cherry": "cherries", "berry": "berries",
    "tortilla": "tortillas", "child": "children", "mouse": "mice",
}
_IRREGULAR_REV = {v: k for k, v in _IRREGULAR.items()}
# Words that look plural but are not, or never change.
_UNCHANGED = {
    "asparagus", "hummus", "couscous", "molasses", "swiss", "grits", "oats",
    "greens", "noodles", "sprinkles", "chives", "fish", "rice", "bass",
    "series", "shrimp", "salmon", "trout", "cress", "lettuce", "glass",
    "watercress", "pasta", "quinoa", "bread", "cheese", "butter", "oil",
}


def plural(word: str) -> str:
    low = word.lower()
    if low in _UNCHANGED or low in _IRREGULAR_REV:
        return word
    if low in _IRREGULAR:
        return _match_case(word, _IRREGULAR[low])
    if re.search(r"[^aeiou]y$", low):
        return word[:-1] + "ies"
    if re.search(r"(s|x|z|ch|sh)$", low):
        return word + "es"
    return word + "s"


def singular(word: str) -> str:
    low = word.lower()
    if low in _UNCHANGED or low in _IRREGULAR:
        return word
    if low in _IRREGULAR_REV:
        return _match_case(word, _IRREGULAR_REV[low])
    if re.search(r"[^aeiou]ies$", low):
        return word[:-3] + "y"
    if re.search(r"(ss|us|is)$", low):
        return word
    if re.search(r"(xes|zes|ches|shes|sses)$", low):
        return word[:-2]
    if low.endswith("s") and len(low) > 2:
        return word[:-1]
    return word


def _match_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def slugify(text: str) -> str:
    """'Sheet-Pan Chicken Thighs!' -> 'sheet-pan-chicken-thighs'."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return re.sub(r"-{2,}", "-", text)


def tag_name(text: str) -> str:
    """Tags are lowercase words joined by hyphens: 'Week Night' -> 'week-night'."""
    return slugify(str(text))
