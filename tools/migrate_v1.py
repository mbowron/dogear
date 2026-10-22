#!/usr/bin/env python3
"""Convert Dogear v1 recipe files to the v2 format.

    python tools/migrate_v1.py OLD_RECIPES_DIR NEW_RECIPES_DIR [--report FILE]
                                [--force] [--dry-run]

What it does, per recipe:

* Front matter: v1 keys are mapped to v2 (`based-on` becomes `source`,
  `course` is lowercased). `time`, `schedule-anchor`, `schedule-default` and
  `keywords` are dropped because v2 works them out or does not use them.
* Ingredients are copied line for line. The v2 grammar is a superset of v1.
* Steps keep their text. The v1 `{timer: ...}` and `{at: ...}` tags are turned
  into a v2 tag: durations come from the gap between one step's `at` time and
  the next, or from the timer; equipment, temperature and active/passive are
  guessed from the wording ("roast at 425°F" -> oven 425F, passive).
* `## Schedule` is dropped (v2 computes the timeline). Its rows go into the
  report so a reviewer can check the drafted durations against them.
* `## Adjustments` becomes `## Notes`.
* Every migrated recipe gets `review: true`, which the app shows as
  "needs review" until someone confirms the drafted step data and removes it.

Nothing in the old folder is changed. Existing files in the new folder are
skipped unless --force is given. Photos in OLD/images are copied across.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dogear import units  # noqa: E402
from dogear.model import Appliance, PASSIVE_EQUIPMENT, Recipe, Step  # noqa: E402
from dogear.parse import parse_ingredient, parse_recipe  # noqa: E402
from dogear.text import tag_name  # noqa: E402
from dogear.write import step_tag, to_markdown  # noqa: E402

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".svg")


# --------------------------------------------------------------------------
# Reading v1
# --------------------------------------------------------------------------


@dataclass
class V1Step:
    lead: str
    body: str
    timer_s: int | None = None
    at_min: float | None = None


@dataclass
class V1Recipe:
    slug: str
    meta: dict
    ingredients: list[tuple[str, str | None]] = field(default_factory=list)  # (line, group)
    schedule: list[str] = field(default_factory=list)
    steps: list[V1Step] = field(default_factory=list)
    adjustments: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _v1_value(raw: str):
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        return [x.strip().strip("'\"") for x in raw[1:-1].split(",") if x.strip()]
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        return raw[1:-1]
    return raw


def read_v1(path: Path) -> V1Recipe:
    """Read a v1 file the way v1's build.py did (no real YAML)."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").lstrip("﻿")
    rec = V1Recipe(slug=path.stem, meta={})
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        rec.problems.append("no front matter block")
        return rec
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        rec.problems.append("front matter never closed")
        return rec

    nested: dict | None = None
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")) and nested is not None:
            k, _, v = line.strip().partition(":")
            nested[k.strip()] = _v1_value(v)
            continue
        k, sep, v = line.partition(":")
        if not sep:
            rec.problems.append(f"front matter line not understood: {line!r}")
            continue
        k = k.strip()
        if v.strip() == "":
            nested = rec.meta[k] = {}
        else:
            nested = None
            rec.meta[k] = _v1_value(v)

    section = None
    group = None
    step_lines: list[list[str]] = []
    for line in lines[end + 1:]:
        h = re.match(r"^##\s+(.+?)\s*$", line)
        if h and not line.startswith("###"):
            section = h.group(1).strip().lower()
            group = None
            continue
        if section == "ingredients":
            g = re.match(r"^###\s+(.+?)\s*$", line.strip())
            if g:
                group = g.group(1).rstrip(":")
            elif line.strip():
                rec.ingredients.append((line.strip(), group))
        elif section == "schedule":
            if line.strip().startswith(("-", "*")):
                rec.schedule.append(line.strip()[1:].strip())
        elif section == "steps":
            m = re.match(r"^\d+[.)]\s+(.*)$", line)
            if m:
                step_lines.append([m.group(1)])
            elif line.strip() and step_lines:
                step_lines[-1].append(line.strip())
        elif section == "adjustments":
            rec.adjustments.append(line.rstrip())
        elif section and line.strip():
            rec.problems.append(f"unknown v1 section '{section}' skipped")
            section = "_skipped"

    for parts in step_lines:
        rec.steps.append(_read_v1_step("\n".join(parts)))
    return rec


_TIMER_RE = re.compile(r"\{\s*timer\s*:\s*([^,}]+?)\s*(?:,\s*\"[^\"]*\"\s*)?\}", re.I)
_AT_RE = re.compile(r"\{\s*at\s*:\s*([^}]+?)\s*\}", re.I)


def _at_minutes(raw: str) -> float | None:
    raw = raw.strip().replace(" ", "")
    m = re.match(r"^([+-]?\d+(?:\.\d+)?)(h|hr|m|min)?$", raw, re.I)
    if not m:
        return None
    value = float(m.group(1))
    return value * 60 if (m.group(2) or "").lower().startswith("h") else value


def _read_v1_step(text: str) -> V1Step:
    timer_s = at_min = None
    t = _TIMER_RE.search(text)
    if t:
        d = units.parse_duration(t.group(1))
        timer_s = d[1] if d else None
    a = _AT_RE.search(text)
    if a:
        at_min = _at_minutes(a.group(1))
    text = _AT_RE.sub("", _TIMER_RE.sub("", text))
    text = re.sub(r"[ \t]+\n", "\n", text).strip()
    text = re.sub(r"[ \t]{2,}", " ", text)
    m = re.match(r"^\*\*(.+?)\*\*\s*(.*)$", text, re.S)
    lead, body = (m.group(1).strip(), m.group(2).strip()) if m else (text.split("\n")[0], "\n".join(text.split("\n")[1:]))
    return V1Step(lead=lead, body=body, timer_s=timer_s, at_min=at_min)


# --------------------------------------------------------------------------
# Guessing equipment and mode from wording
# --------------------------------------------------------------------------

_TEMP_RE = re.compile(r"(\d{3})\s*°?\s*([FC])\b")
_OVEN_WORDS = re.compile(r"\b(oven|bake|baked|baking|roast|roasted|roasting|broil|broiler)\b", re.I)
_PAN_NOT_STOVE = re.compile(r"\b(sheet|baking|loaf|cake|muffin|roasting|bundt|pie|tart|springform)\s+pan", re.I)
_STOVE_WORDS = re.compile(
    r"\b(skillet|saucepan|pan|pot|stovetop|stove|burner|simmer|simmering|boil|boiling|"
    r"saut[eé]|sear|fry|frying|griddle|wok|heat the oil|medium heat|high heat|low heat|"
    r"medium-high|medium-low)\b", re.I)
_PASSIVE_WORDS = re.compile(
    r"\b(rest|resting|soak|soaking|marinate|marinating|chill|chilling|cool|cooling|"
    r"rise|proof|steep|refrigerate|freeze|bake|baking|roast|roasting|set aside|sit|"
    r"overnight|simmer|simmering|braise|braising|boil until|let it|let them)\b", re.I)


def guess_appliance(text: str) -> tuple[Appliance | None, str]:
    """Return (appliance, reason). Reason explains the guess for the report."""
    low = text.lower()
    temp = _TEMP_RE.search(text)

    def with_temp(kind: str) -> Appliance:
        a = Appliance(kind=kind)
        if temp and 150 <= int(temp.group(1)) <= 600:
            a.temp, a.temp_unit = int(temp.group(1)), temp.group(2).upper()
        return a

    if "air fryer" in low or "air-fryer" in low:
        return with_temp("air-fryer"), "mentions the air fryer"
    if "toaster oven" in low:
        return with_temp("toaster-oven"), "mentions the toaster oven"
    if "slow cooker" in low or "crock" in low:
        return Appliance("slow-cooker"), "mentions a slow cooker"
    if "instant pot" in low or "pressure cook" in low:
        return Appliance("pressure-cooker"), "mentions a pressure cooker"
    if "smoker" in low:
        return with_temp("smoker"), "mentions the smoker"
    if re.search(r"\bgrill\b", low):
        return with_temp("grill"), "mentions the grill"
    if "broil" in low:
        return Appliance("oven", broil=True), "mentions broiling"
    # 'the oven' is a strong cue; 'roast' or 'bake' alone is weak, because
    # 'put the roasting pan over medium heat' is a stovetop step.
    says_oven = re.search(r"\boven\b", low.replace("dutch oven", "")) is not None
    oven_word = _OVEN_WORDS.search(text.replace("Dutch oven", "").replace("dutch oven", ""))
    stove = _STOVE_WORDS.search(_PAN_NOT_STOVE.sub("", text))
    if says_oven or (oven_word and not stove):
        reason = "mentions the oven" if says_oven else f"mentions '{oven_word.group(0)}'"
        if stove:
            reason += f" (also '{stove.group(0)}': check)"
        return with_temp("oven"), reason
    if stove:
        return Appliance("burner"), f"mentions '{stove.group(0)}'"
    if re.search(r"\b(fridge|refrigerat\w*|chill|overnight)\b", low):
        return Appliance("fridge"), "mentions the fridge"
    if "microwave" in low:
        return Appliance("microwave"), "mentions the microwave"
    return None, ""


def guess_mode(text: str, appliance: Appliance | None) -> str:
    if appliance is not None and appliance.kind in PASSIVE_EQUIPMENT:
        return "passive"
    lead = text.split("\n")[0]
    return "passive" if _PASSIVE_WORDS.search(lead) else "active"


# --------------------------------------------------------------------------
# Converting
# --------------------------------------------------------------------------


@dataclass
class StepDraft:
    number: int
    lead: str
    tag: str
    evidence: str


@dataclass
class Outcome:
    slug: str
    status: str                    # "migrated", "skipped", "failed"
    drafts: list[StepDraft] = field(default_factory=list)
    schedule: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


def draft_durations(steps: list[V1Step]) -> list[tuple[int | None, int | None, str]]:
    """(duration_s, with_step, evidence) for each step, from at times and timers."""
    ats = [s.at_min for s in steps]
    known = [a for a in ats if a is not None]
    eat_anchor = bool(known) and max(known) <= 0  # offsets count down to eating
    out: list[tuple[int | None, int | None, str]] = []
    leader = 0
    for i, step in enumerate(steps):
        evidence = []
        with_step = None
        at = ats[i]
        if at is not None and i > 0 and ats[i - 1] == at:
            with_step = leader + 1
            evidence.append(f"same time as step {leader + 1}")
        else:
            leader = i
        gap = None
        if at is not None:
            later = [a for a in ats[i + 1:] if a is not None and a > at]
            if later:
                gap = int(round((later[0] - at) * 60))
            elif eat_anchor and at < 0:
                gap = int(round(-at * 60))
            if gap is not None:
                evidence.append(f"at {at:+g} min")
        # A timer is the cook's own measure of the wait, so it beats the gap
        # between step times (which can include slack).
        duration = None
        if step.timer_s:
            duration = step.timer_s
            evidence.append(f"timer {units.format_duration(step.timer_s)}")
        elif gap:
            duration = gap
        out.append((duration, with_step, ", ".join(evidence) or "no time data"))
    return out


def convert(v1: V1Recipe) -> tuple[Recipe, Outcome]:
    meta = v1.meta
    out = Outcome(slug=v1.slug, status="migrated", schedule=list(v1.schedule))
    out.messages += v1.problems

    r = Recipe(slug=v1.slug, title=str(meta.get("title") or v1.slug))
    low, _high, noun = units.split_amount(str(meta.get("yield") or ""))
    if low:
        r.yield_count, r.yield_noun = low, noun or "servings"
    else:
        out.messages.append("no usable yield; set to 4 servings")
    if meta.get("max-yield"):
        try:
            r.max_yield = float(meta["max-yield"])
        except ValueError:
            out.messages.append(f"max-yield {meta['max-yield']!r} dropped")
    r.course = str(meta.get("course") or "main").lower()
    r.category = meta.get("category") or None
    tags = meta.get("tags") or []
    r.tags = [tag_name(t) for t in (tags if isinstance(tags, list) else [tags]) if tag_name(t)]
    r.summary = meta.get("summary") or None
    desc = meta.get("description")
    r.description = desc if desc and desc != r.summary else None
    r.source = meta.get("based-on") or None
    r.image = meta.get("image") or None
    r.added = meta.get("added") or None
    r.storage = meta.get("storage") or None
    r.nutrition_note = meta.get("nutrition-note") or None
    if isinstance(meta.get("nutrition"), dict):
        clean = {}
        for k, v in meta["nutrition"].items():
            try:
                clean[k] = float(v)
            except ValueError:
                out.messages.append(f"nutrition {k} {v!r} dropped")
        r.nutrition = clean or None
    r.review = True
    dropped = [k for k in ("time", "schedule-anchor", "schedule-default", "keywords") if k in meta]
    if dropped:
        out.messages.append("dropped keys v2 does not use: " + ", ".join(dropped))
    known = {"title", "course", "category", "tags", "yield", "max-yield", "summary",
             "description", "based-on", "image", "added", "storage", "nutrition",
             "nutrition-note", "time", "schedule-anchor", "schedule-default", "keywords"}
    for k in meta:
        if k not in known:
            r.extra[k] = meta[k]
            out.messages.append(f"kept unknown key {k!r}")

    for line, group in v1.ingredients:
        ing = parse_ingredient(line, group=group)
        if ing is not None:
            r.ingredients.append(ing)

    for i, ((duration, with_step, evidence), v1s) in enumerate(
            zip(draft_durations(v1.steps), v1.steps), start=1):
        text = f"{v1s.lead}\n{v1s.body}"
        appliance, reason = guess_appliance(text)
        step = Step(number=i, lead=v1s.lead, body=v1s.body, duration_s=duration,
                    mode=guess_mode(text, appliance), mode_set=True,
                    appliance=appliance, with_step=with_step)
        r.steps.append(step)
        why = "; ".join(x for x in (evidence, reason) if x)
        out.drafts.append(StepDraft(i, v1s.lead, step_tag(step) or "(no tag)", why))

    if v1.adjustments:
        r.notes = "\n".join(v1.adjustments).strip()
    if v1.schedule:
        out.messages.append(f"## Schedule ({len(v1.schedule)} rows) dropped; "
                            "check the drafted durations against it")
    if not any(s.duration_s for s in r.steps):
        out.messages.append("no durations could be drafted; fill them in by hand")
    return r, out


def _copy_images(slug: str, image: str | None, src: Path, dst: Path, dry: bool) -> list[str]:
    copied = []
    src_dir, dst_dir = src / "images", dst / "images"
    candidates = [src_dir / f"{slug}{ext}" for ext in IMAGE_EXTS]
    if image and not re.match(r"^https?://", image):
        candidates.append(src_dir / image)
    for path in candidates:
        if path.is_file():
            if not dry:
                dst_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dst_dir / path.name)
            copied.append(path.name)
    return copied


def migrate(src: Path, dst: Path, force: bool = False, dry: bool = False) -> list[Outcome]:
    outcomes = []
    if not dry:
        dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.glob("*.md")):
        target = dst / path.name
        if target.exists() and not force:
            outcomes.append(Outcome(path.stem, "skipped", messages=["already exists in the new folder"]))
            continue
        v1 = read_v1(path)
        if not v1.meta:
            outcomes.append(Outcome(path.stem, "failed", messages=v1.problems or ["could not read"]))
            continue
        recipe, outcome = convert(v1)
        text = to_markdown(recipe)
        check = parse_recipe(text, path.stem)
        for issue in check.issues:
            if issue.level != "note":
                outcome.messages.append(f"v2 check {issue}")
        if not check.ok:
            outcome.status = "failed"
        elif not dry:
            target.write_text(text, encoding="utf-8")
        images = _copy_images(path.stem, recipe.image, src, dst, dry)
        if images:
            outcome.messages.append("copied photo: " + ", ".join(images))
        outcomes.append(outcome)
    return outcomes


def report(outcomes: list[Outcome], src: Path, dst: Path) -> str:
    lines = ["# Dogear v1 to v2 migration report", "",
             f"From `{src}` to `{dst}`.", "",
             "Every migrated recipe has `review: true`. Check each drafted step tag "
             "below, fix the recipe file, then delete the `review: true` line.", "",
             "| Recipe | Status | Steps with a drafted duration |", "| --- | --- | --- |"]
    for o in outcomes:
        timed = sum(1 for d in o.drafts if re.match(r"^\{\d", d.tag))
        lines.append(f"| {o.slug} | {o.status} | {timed} of {len(o.drafts)} |")
    for o in outcomes:
        lines += ["", f"## {o.slug}", "", f"Status: {o.status}."]
        if o.messages:
            lines += [""] + [f"- {m}" for m in o.messages]
        if o.drafts:
            lines += ["", "| Step | Drafted tag | Based on |", "| --- | --- | --- |"]
            for d in o.drafts:
                lead = d.lead.replace("|", "\\|")
                lines.append(f"| {d.number}. {lead} | `{d.tag}` | {d.evidence or '-'} |")
        if o.schedule:
            lines += ["", "Old schedule:", ""] + [f"- {row}" for row in o.schedule]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Convert Dogear v1 recipes to v2.")
    ap.add_argument("src", type=Path, help="the old recipes/ folder")
    ap.add_argument("dst", type=Path, help="the new recipes/ folder")
    ap.add_argument("--report", type=Path, default=Path("migration-report.md"))
    ap.add_argument("--force", action="store_true", help="overwrite files already in dst")
    ap.add_argument("--dry-run", action="store_true", help="write only the report")
    ns = ap.parse_args(argv)
    if not ns.src.is_dir():
        print(f"{ns.src} is not a folder", file=sys.stderr)
        return 2
    if ns.src.resolve() == ns.dst.resolve():
        print("the new folder must differ from the old one", file=sys.stderr)
        return 2
    outcomes = migrate(ns.src, ns.dst, ns.force, ns.dry_run)
    ns.report.write_text(report(outcomes, ns.src, ns.dst), encoding="utf-8")
    counts = {s: sum(o.status == s for o in outcomes) for s in ("migrated", "skipped", "failed")}
    print(f"{counts['migrated']} migrated, {counts['skipped']} skipped, "
          f"{counts['failed']} failed. Report: {ns.report}")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
