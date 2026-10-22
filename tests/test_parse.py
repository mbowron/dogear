import pytest

from conftest import recipe_text
from dogear.parse import parse_file, parse_ingredient, parse_recipe

BASIC_INGREDIENTS = "## Ingredients\n\n- 1 cup rice\n\n"


def steps_recipe(steps: str, front: str = "title: Test\nyield: 4 servings"):
    return parse_recipe(recipe_text(BASIC_INGREDIENTS + "## Steps\n\n" + steps, front), "test")


def levels(result, level):
    return [i.message for i in result.issues if i.level == level]


# --------------------------------------------------------------------------
# Sample recipes
# --------------------------------------------------------------------------


def test_samples_parse_cleanly(sample_paths):
    assert len(sample_paths) >= 5
    for path in sample_paths:
        result = parse_file(path)
        assert result.ok, (path.name, result.issues)
        assert not levels(result, "warning"), (path.name, result.issues)
        assert all(s.mode_set for s in result.recipe.steps), path.name


def test_ingredient_groups(sample_paths):
    cornbread = parse_file(next(p for p in sample_paths if p.stem == "skillet-cornbread")).recipe
    assert [i.group for i in cornbread.ingredients] == ["Dry"] * 5 + ["Wet"] * 3
    assert cornbread.ingredients[0].grams == 150


# --------------------------------------------------------------------------
# Ingredient lines
# --------------------------------------------------------------------------


def ing(text):
    return parse_ingredient(text)


def test_range_unit_prep_and_pantry():
    i = ing("- 2-3 cloves garlic, minced [pantry]")
    assert (i.amount, i.amount_max, i.unit) == (2, 3, "clove")
    assert i.name == "garlic, minced" and i.item == "garlic"
    assert i.pantry and not i.optional and i.parsed


def test_package_size_becomes_note():
    i = ing("- 1 (14.5 oz) can diced tomatoes")
    assert (i.amount, i.unit, i.name, i.note) == (1, "can", "diced tomatoes", "14.5 oz")


def test_grams_and_note_parentheticals():
    i = ing("- 1 cup flour (125 g) (sifted)")
    assert (i.grams, i.note, i.unit) == (125, "sifted", "cup")
    i = ing("- 1 1/2 cups (180 g) flour")
    assert (i.amount, i.unit, i.grams, i.name) == (1.5, "cup", 180, "flour")
    i = ing("- 2 cans (15 oz each) black beans, drained")
    assert (i.unit, i.note, i.item) == ("can", "15 oz each", "black beans")


def test_counted_items_are_stored_singular():
    i = ing("- 4 chicken thighs, bone-in and skin-on")
    assert i.unit is None and i.name == "chicken thigh, bone-in and skin-on"
    assert i.display_name(4) == "chicken thighs, bone-in and skin-on"
    assert i.display_name(1) == "chicken thigh, bone-in and skin-on"
    assert ing("- 3 large eggs").name == "large egg"
    assert ing("- 2 tomatoes").display_name(2) == "tomatoes"


def test_unmeasured_and_a_pinch():
    i = ing("- salt and pepper, to taste [pantry]")
    assert i.amount is None and i.parsed and i.pantry and not i.scales
    p = ing("- a pinch of kosher salt")
    assert (p.amount, p.unit, p.name) == (1, "pinch", "kosher salt")
    assert not p.scales
    assert ing("- 4 pinches ground nutmeg").scales


def test_unit_word_alone_is_the_name():
    i = ing("- 2 cloves")
    assert (i.amount, i.unit, i.name) == (2, None, "clove")


def test_unreadable_amount_is_kept_as_written():
    result = parse_recipe(recipe_text("## Ingredients\n\n- 1-inch piece ginger\n\n## Steps\n\n1. **Go.**"), "x")
    i = result.recipe.ingredients[0]
    assert not i.parsed and i.amount is None
    assert any("could not read the amount" in m for m in levels(result, "warning"))


@pytest.mark.parametrize("text, unit", [
    ("- 2 Tbsp olive oil", "tbsp"), ("- 1 T sugar", "tbsp"), ("- 1 t salt", "tsp"),
    ("- 1 fl oz lime juice", "fl oz"), ("- 2 lbs. potatoes", "lb"), ("- 500 grams flour", "g"),
    ("- 1 cup of milk", "cup"),
])
def test_unit_spellings(text, unit):
    i = ing(text)
    assert i.unit == unit
    assert not i.name.startswith("of ")


def test_optional_flag_and_note():
    assert ing("- 1 tbsp sugar (optional)").optional
    assert ing("- 4 sprigs thyme [optional]").optional


# --------------------------------------------------------------------------
# Step tags
# --------------------------------------------------------------------------


def test_step_tag_fields():
    r = steps_recipe(
        "1. **Boil.** {25m, passive, burner}\n"
        "2. **Heat the oven.** {15m, passive, oven 450F, ends with 1}\n"
        "3. **Roast.** {25-30m, passive, oven 450F, or air fryer 400F 15-18m}\n"
        "4. **Sear.** {3m, active, burner x2, after 1}\n"
        "5. **Brown.** {oven broil, 3m, with 4}\n"
        "6. **Bake.** {20m, oven 220C}\n"
    )
    assert r.ok, r.issues
    s = r.recipe.steps
    assert (s[0].duration_s, s[0].mode, s[0].appliance.kind) == (1500, "passive", "burner")
    assert s[1].ends_with == 1 and s[1].appliance.temp_f == 450
    assert (s[2].duration_min_s, s[2].duration_s, s[2].timer_s) == (1500, 1800, 1500)
    fb = s[2].fallbacks[0]
    assert (fb.appliance.kind, fb.appliance.temp, fb.duration_min_s, fb.duration_s) == \
        ("air-fryer", 400, 900, 1080)
    assert s[3].appliance.count == 2 and s[3].after_step == 1
    assert s[4].appliance.broil and s[4].appliance.setting == "broil" and s[4].with_step == 4
    assert s[5].appliance.temp_f == 430 and s[5].appliance.temp_unit == "C"


def test_multiline_step_body_and_optional():
    r = steps_recipe("1. **Mix.** Stir well.\n   Optional: add nuts. {5m, active}\n2. **Eat.**")
    s = r.recipe.steps[0]
    assert s.body == "Stir well.\nOptional: add nuts." and s.duration_s == 300


def test_mode_is_inferred_and_noted():
    r = steps_recipe("1. **Let it rest.** {10m}\n2. **Slice.** {2m}\n3. **Roast.** {20m, oven 400F}")
    s = r.recipe.steps
    assert [x.mode for x in s] == ["passive", "active", "passive"]
    assert not any(x.mode_set for x in s)
    assert len([m for m in levels(r, "note") if "mode not given" in m]) == 3


def test_lead_without_bold_is_noted():
    r = steps_recipe("1. Chop the onion. Use a sharp knife. {5m, active}")
    s = r.recipe.steps[0]
    assert s.lead == "Chop the onion." and s.body == "Use a sharp knife."
    assert levels(r, "note")


@pytest.mark.parametrize("steps, fragment", [
    ("1. **A.** {5m} {active}", "tags"),
    ("1. **A.** {5m}\n2. **B.** {5m, with 3}", "earlier step"),
    ("1. **A.** {5m, with 1}", "earlier step"),
    ("1. **A.** {5m, sprinkle}", "did not understand"),
    ("1. **A.** {5m, oven 400F, grill 500F}", "two appliances"),
    ("1. **A.** {5m}\n2. **B.** {5m, with 1, after 1}", "only one of"),
    ("1. **A.** {5m, 10m}", "two durations"),
    ("1. **A.** {5m, or air fryer 400F}", "no main appliance"),
    ("1. **A.** {5m, oven 400F, or spaceship 9m}", "fallback"),
])
def test_step_errors(steps, fragment):
    r = steps_recipe(steps)
    assert not r.ok
    assert any(fragment in m for m in levels(r, "error")), r.issues


@pytest.mark.parametrize("steps, fragment", [
    ("1. **A.** {5m, oven}", "no temperature"),
    ("1. **A.** {5m, burner 400F}", "no temperature setting"),
    ("1. **A.** {5m, oven 40F}", "looks wrong"),
    ("1. **A.**\n2. **B.**", "no step has a duration"),
    ("- **A.** {5m}", "numbered list"),
])
def test_step_warnings(steps, fragment):
    r = steps_recipe(steps)
    assert r.ok
    assert any(fragment in m for m in levels(r, "warning")), r.issues


# --------------------------------------------------------------------------
# Front matter and structure
# --------------------------------------------------------------------------

GOOD_BODY = BASIC_INGREDIENTS + "## Steps\n\n1. **Cook.** {10m, active}\n"


@pytest.mark.parametrize("text, fragment", [
    ("no front matter", "must start with a front matter"),
    ("---\ntitle: A\n", "never closed"),
    ("---\ntitle: A: B: [\n---\n", "not valid YAML"),
    (recipe_text(GOOD_BODY, "yield: 4"), "'title' is required"),
    (recipe_text(GOOD_BODY, "title: A"), "'yield' is required"),
    (recipe_text(GOOD_BODY, "title: A\nyield: lots"), "must start with a number"),
    (recipe_text("## Ingredients\n\n- 1 egg\n"), "no steps"),
    (recipe_text("## Steps\n\n1. **Cook.**\n"), "no ingredients"),
    (recipe_text(GOOD_BODY + "\n## Serving\n\nhot\n"), "unknown section"),
    (recipe_text(GOOD_BODY + "\n## Steps\n\n1. **Again.**\n"), "appears twice"),
])
def test_recipe_errors(text, fragment):
    r = parse_recipe(text, "test")
    assert not r.ok
    assert any(fragment in m for m in levels(r, "error")), r.issues


def test_bad_slug():
    assert not parse_recipe(recipe_text(GOOD_BODY), "Bad Name").ok


def test_front_matter_fields_and_unknown_keys():
    front = ("title: Stew\nyield: 6 bowls\ncourse: Soup\ntags: [Week Night, cozy]\n"
             "hold: 1h\nadded: 2026-10-21\nnutrition:\n  calories: 400\n  protein: 30\n"
             "flavor: smoky\nreview: true")
    r = parse_recipe(recipe_text(GOOD_BODY, front), "stew")
    assert r.ok
    rec = r.recipe
    assert (rec.yield_count, rec.yield_noun, rec.course) == (6, "bowls", "soup")
    assert rec.tags == ["week-night", "cozy"] and rec.hold_s == 3600
    assert rec.added == "2026-10-21" and rec.nutrition == {"calories": 400, "protein": 30}
    assert rec.review and rec.extra == {"flavor": "smoky"}
    assert any("unknown front matter key" in m for m in levels(r, "warning"))


def test_section_aliases():
    text = recipe_text("## Ingredients\n\n- 1 egg\n\n## Directions\n\n1. **Fry.** {3m, active, burner}\n\n## Tips\n\nUse butter.")
    r = parse_recipe(text, "egg")
    assert r.ok and r.recipe.notes == "Use butter."


def test_format_doc_example_is_valid():
    from conftest import ROOT
    doc = (ROOT / "docs" / "RECIPE-FORMAT.md").read_text()
    example = doc.split("## 6. Example", 1)[1].split("```markdown\n", 1)[1].split("\n```", 1)[0]
    r = parse_recipe(example, "crispy-smashed-potatoes")
    assert r.ok and not levels(r, "warning"), r.issues


def test_to_dict_has_timing(sample_paths):
    d = parse_file(sample_paths[0]).recipe.to_dict()
    assert d["timing"]["totalS"] > 0
    assert len(d["timing"]["steps"]) == len(d["steps"])
    assert {"amount", "unit", "item", "pantry"} <= d["ingredients"][0].keys()
