import datetime as dt

from conftest import RECIPES, recipe_text
from dogear.parse import parse_file, parse_recipe
from dogear.schedule import plan

MIN = 60


def load(slug):
    return parse_file(RECIPES / f"{slug}.md").recipe


def mins(t):
    return (t.start_s // MIN, t.end_s // MIN)


def test_ends_with_and_last_step_at_plate():
    p = plan(load("crispy-smashed-potatoes"))
    assert p.total_s == 66 * MIN
    boil, oven, drain, smash, roast, finish = p.steps
    assert oven.end_s == boil.end_s  # oven is hot when the potatoes are done
    assert mins(roast) == (-31, -1)
    assert finish.end_s == 0


def test_with_and_after():
    p = plan(load("skillet-cornbread"))
    preheat, dry, wet, pour, bake, cool = p.steps
    assert dry.start_s == preheat.start_s
    assert wet.start_s == dry.end_s
    assert pour.start_s == preheat.end_s  # waits for every earlier step
    assert p.active_s == 12 * MIN


def test_plate_and_start_now():
    r = load("sheet-pan-chicken-thighs")
    plate = dt.datetime(2026, 10, 21, 18, 30)
    p = plan(r, plate=plate)
    assert p.total_s == 65 * MIN
    assert p.start == dt.datetime(2026, 10, 21, 17, 25)
    assert p.clock(p.steps[2].start_s) == dt.datetime(2026, 10, 21, 17, 40)

    start = dt.datetime(2026, 10, 21, 17, 0)
    p2 = plan(r, start=start)
    assert p2.plate == dt.datetime(2026, 10, 21, 18, 5)


def test_ends_with_reaching_before_first_step():
    text = recipe_text("## Ingredients\n\n- 1 egg\n\n## Steps\n\n"
                       "1. **Short.** {10m, active}\n"
                       "2. **Long, finishing together.** {30m, passive, ends with 1}\n")
    p = plan(parse_recipe(text, "x").recipe)
    assert p.total_s == 30 * MIN
    assert mins(p.steps[0]) == (-10, 0) and mins(p.steps[1]) == (-30, 0)


def test_overlapping_active_counted_once():
    text = recipe_text("## Ingredients\n\n- 1 egg\n\n## Steps\n\n"
                       "1. **A.** {10m, active}\n2. **B.** {10m, active, with 1}\n"
                       "3. **C.** {10m, passive}\n")
    p = plan(parse_recipe(text, "x").recipe)
    assert p.total_s == 20 * MIN and p.active_s == 10 * MIN


def test_untimed_steps_take_no_time():
    text = recipe_text("## Ingredients\n\n- 1 egg\n\n## Steps\n\n"
                       "1. **A.** {10m, active}\n2. **Serve.**\n")
    p = plan(parse_recipe(text, "x").recipe)
    assert mins(p.steps[1]) == (0, 0) and p.total_s == 10 * MIN
