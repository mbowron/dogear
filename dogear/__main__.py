"""Command line: python -m dogear check | show | json

  check [PATH ...] [--strict]   validate recipes (default folder: recipes/)
  show FILE [--plate 18:30 | --now] [--servings N]
                                print a recipe with its timeline
  json FILE                     print the JSON the app serves
  serve [--port 8000]           run the web app
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from . import units
from .parse import parse_file
from .scale import ingredient_text
from .schedule import plan


def _paths(args: list[str]) -> list[Path]:
    targets = [Path(a) for a in args] or [Path("recipes")]
    files: list[Path] = []
    for t in targets:
        files += sorted(t.glob("*.md")) if t.is_dir() else [t]
    return files


def cmd_check(ns: argparse.Namespace) -> int:
    files = _paths(ns.paths)
    if not files:
        print("No recipe files found.")
        return 1
    bad = 0
    for path in files:
        result = parse_file(path)
        shown = [i for i in result.issues if ns.strict or i.level != "note"]
        flag = "ok " if result.ok else "ERR"
        review = "  (needs review)" if result.recipe and result.recipe.review else ""
        print(f"{flag}  {path.name}{review}")
        for issue in shown:
            print(f"       {issue}")
        bad += not result.ok
    print(f"\n{len(files) - bad} of {len(files)} recipes OK.")
    return 1 if bad else 0


def _clock(t: dt.datetime) -> str:
    return t.strftime("%I:%M %p").lstrip("0")


def cmd_show(ns: argparse.Namespace) -> int:
    result = parse_file(ns.file)
    for issue in result.errors:
        print(issue)
    if not result.ok:
        return 1
    r = result.recipe
    factor = (ns.servings / r.yield_count) if ns.servings else 1.0
    count = r.yield_count * factor

    plate = start = None
    if ns.now:
        start = dt.datetime.now().replace(second=0, microsecond=0)
    elif ns.plate:
        hh, mm = (int(x) for x in ns.plate.split(":"))
        plate = dt.datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0)
    p = plan(r, plate=plate, start=start)

    print(f"{r.title}\n{'=' * len(r.title)}")
    print(f"{units.format_amount(count)} {r.yield_noun} · total "
          f"{units.human_duration(p.total_s)} · hands-on {units.human_duration(p.active_s)}")
    if p.plate:
        print(f"Start {_clock(p.start)} · plate {_clock(p.plate)}")

    print("\nIngredients")
    group = None
    for ing in r.ingredients:
        if ing.group != group:
            group = ing.group
            if group:
                print(f"  {group}")
        amount, name = ingredient_text(ing, factor)
        line = f"{amount} {name}" if amount else name
        extras = [x for x in (ing.note, "pantry" if ing.pantry else None,
                              "optional" if ing.optional else None) if x]
        print(f"  - {line}" + (f"  ({'; '.join(extras)})" if extras else ""))

    print("\nSteps")
    for step, t in zip(r.steps, p.steps):
        when = _clock(p.clock(t.start_s)) if p.plate else f"-{units.human_duration(-t.start_s)}" \
            if t.start_s else "plate"
        dur = units.human_duration(step.duration_s) if step.duration_s else "-"
        where = f" · {step.appliance.label()}" if step.appliance else ""
        alt = "".join(f" (or {f.label()})" for f in step.fallbacks)
        print(f"  {step.number:>2}. [{when:>9}] {step.lead}  ({dur}, {step.mode}{where}{alt})")
    return 0


def cmd_json(ns: argparse.Namespace) -> int:
    result = parse_file(ns.file)
    out = {"ok": result.ok, "issues": [i.__dict__ for i in result.issues],
           "recipe": result.recipe.to_dict() if result.recipe else None}
    json.dump(out, sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0 if result.ok else 1


def cmd_serve(ns: argparse.Namespace) -> int:
    from .server import serve

    serve(host=ns.host, port=ns.port, recipes=ns.recipes, data=ns.data)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dogear", description="Dogear recipe tools")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="validate recipe files")
    c.add_argument("paths", nargs="*")
    c.add_argument("--strict", action="store_true", help="also show notes about guesses")
    c.set_defaults(func=cmd_check)

    s = sub.add_parser("show", help="print a recipe with its timeline")
    s.add_argument("file")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--plate", help="plate time, 24-hour HH:MM")
    g.add_argument("--now", action="store_true", help="start now")
    s.add_argument("--servings", type=float)
    s.set_defaults(func=cmd_show)

    j = sub.add_parser("json", help="print the recipe as the app's JSON")
    j.add_argument("file")
    j.set_defaults(func=cmd_json)

    v = sub.add_parser("serve", help="run the web app")
    v.add_argument("--host", default="0.0.0.0")
    v.add_argument("--port", type=int, default=int(os.environ.get("DOGEAR_PORT", 8000)))
    v.add_argument("--recipes", help="recipes folder (env DOGEAR_RECIPES, default ./recipes)")
    v.add_argument("--data", help="data folder (env DOGEAR_DATA, default ./data)")
    v.set_defaults(func=cmd_serve)

    ns = ap.parse_args(argv)
    return ns.func(ns)


if __name__ == "__main__":
    sys.exit(main())
