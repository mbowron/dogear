# Dogear recipe format (v2)

Audience: anyone, person or AI agent, who writes, converts or edits a recipe, or who changes the parser. The parser (`dogear/parse.py`) and the writer (`dogear/write.py`) implement exactly this; change them together with this file.

Check your work with:

```sh
python -m dogear check recipes/            # errors and warnings
python -m dogear check --strict recipes/   # also notes about what Dogear guessed
python -m dogear show recipes/<slug>.md --plate 18:30 --servings 6
```

## 1. Files

```
recipes/<slug>.md          one recipe per file: the source of truth
recipes/images/<slug>.jpg  optional photo (.jpg .jpeg .png .webp .avif .svg)
```

- The file name is the slug and the recipe's permanent ID: lowercase letters, digits and hyphens. Cook logs, notes and ratings hang off it, so **never rename a recipe file** once it is in use.
- A file is: front matter, then `## Ingredients`, `## Steps`, and optionally `## Notes`, in that order. Any other `##` heading is an error. (`Directions`, `Method` and `Instructions` are read as Steps; `Tips` and `Adjustments` as Notes.)

## 2. Front matter

Real YAML between `---` lines. Quote a value that contains `: ` (`summary: "Crisp skin: the classic"`); the app's editor does this for you.

| Key | Req | Meaning |
|---|---|---|
| `title` | yes | Recipe name. |
| `yield` | yes | `<number> <noun>`: `4 servings`, `8 wedges`, `2 jars`. Ingredient amounts are written for this many. The noun labels the servings control. |
| `course` | no | `main` (default), `side`, `soup`, `salad`, `bread`, `sauce`, `appetizer`, `dessert`, `drink`, `breakfast`, `snack`. The meal builder groups dishes by it. |
| `category` | no | One filter chip on the box, such as `Chicken`. Spell it the same way across recipes. |
| `tags` | no | `[weeknight, gluten-free]`. Stored lowercase with hyphens. |
| `max-yield` | no | Top of the servings control. Default: 12 or twice the yield, whichever is larger. |
| `hold` | no | How long the dish can wait once done and still be good: `10m`, `30m`. Default 0. The meal builder uses it to give a dish slack. |
| `summary` | no | One line for the recipe card, up to about 140 characters. |
| `description` | no | A subtitle for the recipe page, if it should differ from `summary`. |
| `source` | no | Where it came from: a web address (shown as a link) or text such as a cookbook and page. |
| `image` | no | A file in `recipes/images/` or a web address. Left out, `recipes/images/<slug>.*` is used if it exists. |
| `added` | no | `2026-10-21`. Drives "recently added". |
| `storage` | no | `keeps 3 days in the fridge`. |
| `nutrition` | no | Nested numbers **per one yield unit**: `calories`, `protein`, `carbs`, `fat` (grams). |
| `nutrition-note` | no | Where the numbers came from. |
| `review` | no | `true` means some step data was guessed (by the migration script or an import) and a person should check it. The app shows "needs review". Delete the line once checked. |

Unknown keys are kept on save but warned about.

## 3. Ingredients

A bulleted list, one ingredient per line. Optional `### Heading` lines group them (`### Sauce`).

```
- <amount> <unit> <name>, <prep> (<grams> g) (<note>) [pantry] [optional]
```

| Part | Rules |
|---|---|
| amount | `2`, `1.5`, `1/2`, `1 1/2`, `½`, `1½`, or a range `2-3` / `2 to 3`. `a pinch of salt` counts as 1. Leave it out for unmeasured items: `- salt and pepper, to taste [pantry]`. |
| unit | Volume `tsp tbsp cup fl oz pt qt gal ml l`; weight `oz lb g kg`; pieces `pinch dash clove can stick slice sprig bunch head package scoop piece jar bottle handful stalk`. Plurals and long forms are fine (`tablespoons`, `lbs.`). `T` is a tablespoon and `t` a teaspoon. Leave it out for counted things: `- 3 large eggs`. |
| name | The rest of the line. Keep brand names (`H-E-B honey peanut butter`). For counted things, put the noun before the first comma: `4 chicken thighs, bone-in` (the app pluralizes `thigh`), not `4 bone-in chicken thighs`. The part before the first comma is also the shopping-list name. |
| `(150 g)` | A parenthetical that is a gram weight powers the grams toggle and scales with the amount. Any other parenthetical is a note shown under the ingredient. `1 (14.5 oz) can tomatoes` puts the can size in the note. |
| `[pantry]` | A staple (salt, oil, water) left off the shopping list unless the cook asks for it. |
| `[optional]` | Shown as optional. `(optional)` as a note does the same. |

Scaling: amounts multiply with servings; a single `pinch` or `dash` stays put (`4 pinches`, one per jar, scales); a line whose amount could not be read is shown as written and does not scale (warning). Scaled spoon and cup amounts are re-expressed when that reads better (4 tbsp shows as 1/4 cup; 10 tbsp stays 10 tbsp).

## 4. Steps

A numbered list. The whole list is shown at once, as a checklist.

```
3. **Roast until crisp.** Roast without turning until the edges are deep brown. {25-30m, passive, oven 450F, or air fryer 400F 15-18m}
   Optional: dust with smoked paprika before roasting.
```

- Start each step with a **bold lead sentence**; detail follows. Continuation lines are indented three spaces. A line starting `Optional:` is styled as an optional note.
- `### Heading` lines between steps group them (`### Make the sauce`). Numbering continues across groups.
- One `{...}` tag per step, usually at the end of the first line. The timeline, the timers and the meal builder all come from the tags.

### 4.1 The step tag

Comma-separated items, in any order:

| Item | Example | Meaning |
|---|---|---|
| duration | `10m`, `90s`, `1h30m`, `8h`, `35-45m`, `45m-1h` | How long the step takes. For a range the timeline uses the high end and the timer goes off at the low end ("check it"). Every step with a duration gets a timer button. |
| mode | `active` or `passive` | Active: your hands are busy (chopping, searing, stirring). Passive: you can walk away (in the oven, resting, boiling, chilling). The meal builder flags two active steps at the same time. If left out it is guessed (passive for oven, fridge and the like, or when the lead says rest, bake, chill...), and `check --strict` says so. Write it. |
| appliance | `oven 425F`, `toaster oven 350F`, `air fryer 380F`, `burner`, `burner x2`, `grill 500F`, `smoker 225F`, `oven broil`, `microwave`, `slow cooker`, `pressure cooker`, `fridge`, `freezer` | What the step occupies. Temperatures in `F` or `C`. Oven, toaster oven and air fryer should always have a temperature. `fridge` and `freezer` are never counted as busy. |
| fallback | `or air fryer 400F 15-18m` | Another appliance that can do the step, with its own temperature and time. The meal builder uses it when the main one is taken. Only add one where the dish really works that way. |
| `with N` | `with 1` | Start at the same time as step N. |
| `after N` | `after 2` | Start when step N finishes. |
| `ends with N` | `ends with 1` | Finish at the same moment as step N (preheat so the oven is hot when the potatoes are drained). |

N always refers to an **earlier** step.

### 4.2 How the timeline is built

1. A step with no `with`, `after` or `ends with` starts once **every earlier step** has finished.
2. `with`, `after` and `ends with` place a step against one earlier step instead, so it can overlap.
3. A step with no duration takes no time ("Serve.").
4. The step that finishes last ends at **plate time**. Everything is worked backward from there; "start now" works forward.
5. Durations do not change with servings. A doubled roast still says 45 minutes, and the page says so.

Write the preheat as its own step: `**Heat the oven to 425°F.** {15m, passive, oven 425F}`, then `with 1` on the prep that happens meanwhile. That way the meal builder knows the oven is busy.

## 5. Notes

Free Markdown after `## Notes`: variations, substitutions, make-ahead advice. Use `**Bold lead:** explanation` bullets for scannability.

## 6. Example

```markdown
---
title: Crispy Smashed Potatoes
course: side
category: Potatoes
tags: [vegetarian, gluten-free]
yield: 4 servings
hold: 10m
summary: Boiled, smashed flat and roasted until the edges shatter.
added: 2026-10-21
---

## Ingredients

- 2 lb small Yukon Gold potatoes
- 1 tbsp kosher salt, for the water [pantry]
- 3 tbsp olive oil [pantry]
- 1/2 tsp flaky salt [pantry]
- 2 tbsp chopped parsley [optional]

## Steps

1. **Boil the potatoes.** Cover with cold water by an inch, add the kosher salt, bring to a boil and cook until a knife slides in easily. {25m, passive, burner}
2. **Heat the oven to 450°F.** {15m, passive, oven 450F, ends with 1}
3. **Drain and steam dry.** Drain and leave the potatoes in the colander so the surfaces dry. {5m, passive}
4. **Smash.** Oil a sheet pan, spread the potatoes out and press each one to about 1/2 inch with the bottom of a glass. Drizzle with the rest of the oil. {5m, active}
5. **Roast until crisp.** Roast without turning until the edges are deep brown. {25-30m, passive, oven 450F, or air fryer 400F 15-18m}
6. **Finish.** Sprinkle with the flaky salt and parsley. {1m, active}
```

## 7. Checklist for converting a recipe (people and agents)

1. Slug from the title; make sure the file name is free.
2. `yield` honestly matches the ingredient amounts as written.
3. One ingredient per line; grams in parentheses where known; `[pantry]` on staples.
4. Split steps so that each has **one** mode. "Sear 5 minutes, then roast 20" is two steps: `{5m, active, burner}` and `{20m, passive, oven 400F}`.
5. Give every step that takes real time a duration, a mode and, if it uses one, an appliance with its temperature. Make the preheat its own step.
6. Use `with` / `after` / `ends with` for work that overlaps, so the total time is realistic.
7. Add a fallback only when you know the dish works that way.
8. Never invent nutrition numbers, brands or quantities. If unsure about step data, guess sensibly and set `review: true`.
9. Run `python -m dogear check --strict`, then `python -m dogear show` with a plate time and read the timeline as a cook would.

## 8. Errors and warnings

Errors (the recipe is not loaded): no front matter or invalid YAML, missing `title` or `yield`, bad file name, unknown or repeated section, no ingredients, no steps, more than one tag in a step, an unreadable tag item, a step referring to itself or a later step, two appliances without `or`, two of `with`/`after`/`ends with`.

Warnings (loaded, but probably wrong): amount not readable, oven with no temperature, temperature on a burner, odd temperature, unknown course or front matter key, steps written as bullets, no durations at all, long summary.

Notes (`--strict` only): guessed mode, missing bold lead, steps without a duration.
