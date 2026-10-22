from conftest import recipe_text
from dogear.model import Appliance, Fallback, Ingredient, Recipe, Step
from dogear.parse import parse_file, parse_recipe
from dogear.write import ingredient_line, step_tag, to_markdown


def test_samples_round_trip(sample_paths):
    for path in sample_paths:
        first = parse_file(path).recipe
        text = to_markdown(first)
        second = parse_recipe(text, path.stem)
        assert second.ok, (path.name, second.issues)
        assert second.recipe.to_dict() == first.to_dict(), path.name
        assert to_markdown(second.recipe) == text, path.name  # stable


def test_ingredient_built_in_app_round_trips():
    built = Ingredient(raw=None, name="chicken thigh, skin-on", amount=4, unit=None,
                       grams=900, note="about 2 lb", pantry=False, optional=True)
    line = ingredient_line(built)
    assert line == "- 4 chicken thighs, skin-on (900 g) (about 2 lb) [optional]"
    back = parse_recipe(recipe_text(f"## Ingredients\n\n{line}\n\n## Steps\n\n1. **Go.** {{1m, active}}"), "x")
    i = back.recipe.ingredients[0]
    assert (i.name, i.amount, i.grams, i.note, i.optional) == \
        ("chicken thigh, skin-on", 4, 900, "about 2 lb", True)

    ranged = Ingredient(raw=None, name="garlic", amount=2, amount_max=3, unit="clove", pantry=True)
    assert ingredient_line(ranged) == "- 2-3 cloves garlic [pantry]"


def test_step_tag_order():
    s = Step(number=3, lead="Roast.", duration_s=1800, duration_min_s=1500, mode="passive",
             mode_set=True, appliance=Appliance("oven", 450, "F"),
             fallbacks=[Fallback(Appliance("air-fryer", 400, "F"), 1080, 900)], after_step=1)
    assert step_tag(s) == "{25-30m, passive, oven 450F, or air fryer 400F 15-18m, after 1}"
    assert step_tag(Step(number=1, lead="Serve.")) == ""


def test_front_matter_quotes_when_needed():
    r = Recipe(slug="x", title="Chili: The Good One", summary="yes", added="2026-10-21",
               ingredients=[Ingredient(raw="- 1 can beans", name="beans", amount=1, unit="can")],
               steps=[Step(number=1, lead="Simmer.", duration_s=600, mode="passive", mode_set=True)])
    text = to_markdown(r)
    assert 'title: "Chili: The Good One"' in text
    assert 'summary: "yes"' in text  # bare yes would read as true
    assert "added: 2026-10-21\n" in text
    back = parse_recipe(text, "x")
    assert back.ok and back.recipe.title == "Chili: The Good One" and back.recipe.summary == "yes"


def test_extra_keys_survive(sample_paths):
    front = "title: A\nyield: 2 servings\nflavor: smoky"
    r = parse_recipe(recipe_text("## Ingredients\n\n- 1 egg\n\n## Steps\n\n1. **Fry.** {2m, active}", front), "a")
    assert "flavor: smoky" in to_markdown(r.recipe)
