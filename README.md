# Dogear

*Keep the good ones.*

Dogear is a self-hosted recipe box and cooking guide for one household. It keeps the recipes you actually cook as plain Markdown files, walks you through a cook with timers, scales servings, works backward from the time you want to eat, and builds a multi-dish meal that all lands on the table together.

> **Status: early.** This is the v2 rewrite. What exists today is the recipe format, its parser and scheduler, and a converter from v1 files. The web app comes next.

## What works now

- **Recipe format** with timed steps: duration, hands-on or hands-off, the appliance and its temperature, and steps that overlap. See [docs/RECIPE-FORMAT.md](docs/RECIPE-FORMAT.md).
- **Checker**: `python -m dogear check` reports errors and warnings with line numbers.
- **Timeline**: `python -m dogear show` prints a recipe scaled to any servings with clock times for a plate time, or from "start now".
- **v1 converter**: `tools/migrate_v1.py` turns v1 recipe files into v2 and writes a review report.

## Quick start

Requires Python 3.10 or newer.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

python -m dogear check recipes/
python -m dogear show recipes/crispy-smashed-potatoes.md --plate 18:30
python -m dogear show recipes/skillet-cornbread.md --now --servings 16
pytest
```

## Converting v1 recipes

```sh
python tools/migrate_v1.py path/to/old/recipes recipes/ --report migration-report.md
```

The old folder is never changed, and recipes already in the new folder are skipped (use `--force` to overwrite). Durations come from the v1 step times and timers; equipment and hands-on/off are guessed from the wording. Every converted recipe is marked `review: true`, and the report lists each drafted step tag next to the old schedule so it can be checked.

## Layout

```
dogear/            parser, units, scheduler, writer, command line
docs/              recipe format
recipes/           sample recipes (yours live in a mounted folder, not the repo)
tools/             v1 converter
tests/             pytest suite and v1 fixtures
```

## License

MIT. See [LICENSE](LICENSE).
