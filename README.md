# Dogear

*Keep the good ones.*

Dogear is a self-hosted recipe box and cooking guide for one household. It keeps the recipes you actually cook as plain Markdown files, walks you through a cook with timers, scales servings, works backward from the time you want to eat, and builds a multi-dish meal that all lands on the table together.

> **Status: early.** The recipe box, recipe pages and cook mode work. Adding and editing recipes in the app, the meal builder, the shopping list and TickTick export come next.

## What works now

- **Recipe box**: search by name or ingredient, filter by course, see what needs review.
- **Recipe page**: scale servings, pick a plate time (or start now) and see when each step starts, with step timers, notes, ratings and a cook log.
- **Cook mode**: what needs your hands now, running timers with alarms, what's next and every step, laid out for phone, iPad and desktop. Keeps the screen awake and survives a reload.
- **Recipe format** with timed steps: duration, hands-on or hands-off, the appliance and its temperature, and steps that overlap. See [docs/RECIPE-FORMAT.md](docs/RECIPE-FORMAT.md).
- **Command line**: `python -m dogear check` validates recipes, `show` prints a timeline, `serve` runs the app.
- **v1 converter**: `tools/migrate_v1.py` turns v1 recipe files into v2 and writes a review report.

## Install

Dogear is built to run in Docker on a home server, reachable over HTTPS through Tailscale. See [docs/INSTALL.md](docs/INSTALL.md).

## Develop

Requires Python 3.10 or newer.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

python -m dogear serve            # http://localhost:8000, recipes from ./recipes
python -m dogear check recipes/
python -m dogear show recipes/crispy-smashed-potatoes.md --plate 18:30
pytest
```

The front end is plain JavaScript modules and CSS in `web/`, with no build step: edit and reload. The API is described at `/api/docs` while the server runs.

## Converting v1 recipes

```sh
python tools/migrate_v1.py path/to/old/recipes recipes/ --report migration-report.md
```

The old folder is never changed, and recipes already in the new folder are skipped (use `--force` to overwrite). Durations come from the v1 step times and timers; equipment and hands-on/off are guessed from the wording. Every converted recipe is marked `review: true`, and the report lists each drafted step tag next to the old schedule so it can be checked.

## Layout

```
dogear/            parser, units, scheduler, writer, server, command line
web/               front end (HTML, CSS, JavaScript modules, fonts)
deploy/            Tailscale serve config and a compose file
docs/              recipe format and install guide
recipes/           sample recipes (yours live in a mounted folder, not the repo)
tools/             v1 converter
tests/             pytest suite and v1 fixtures
```

## License

MIT. See [LICENSE](LICENSE).
