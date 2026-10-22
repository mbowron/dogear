"""Turn a recipe's steps into a timeline.

Rules (also in docs/RECIPE-FORMAT.md):

* A step starts when every earlier step has finished.
* `with N` starts the step when step N starts.
* `after N` starts the step when step N ends.
* `ends with N` ends the step when step N ends.
* A step without a duration takes no time.
* The last step to finish ends at plate time.

Times are seconds relative to plate time, so they are zero or negative.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .model import Recipe


@dataclass
class TimedStep:
    number: int
    start_s: int   # seconds before plate time (negative)
    end_s: int
    mode: str

    @property
    def duration_s(self) -> int:
        return self.end_s - self.start_s

    def to_dict(self) -> dict:
        return {"number": self.number, "startS": self.start_s, "endS": self.end_s,
                "mode": self.mode}


@dataclass
class Plan:
    steps: list[TimedStep]
    total_s: int            # first start to plate
    active_s: int           # time with hands busy (overlaps counted once)
    plate: dt.datetime | None = None

    @property
    def start(self) -> dt.datetime | None:
        return self.plate - dt.timedelta(seconds=self.total_s) if self.plate else None

    def clock(self, offset_s: int) -> dt.datetime | None:
        return self.plate + dt.timedelta(seconds=offset_s) if self.plate else None

    def for_step(self, number: int) -> TimedStep:
        return self.steps[number - 1]


def relative_times(recipe: Recipe) -> list[tuple[int, int]]:
    """(start, end) for each step in seconds from the first start (>= 0)."""
    starts: list[int] = []
    ends: list[int] = []
    for step in recipe.steps:
        dur = step.duration_s or 0
        if step.with_step:
            start = starts[step.with_step - 1]
        elif step.after_step:
            start = ends[step.after_step - 1]
        elif step.ends_with:
            start = ends[step.ends_with - 1] - dur
        else:
            start = max(ends, default=0)
        starts.append(start)
        ends.append(start + dur)
    if not starts:
        return []
    shift = -min(starts)  # 'ends with' can reach before the first step
    return [(s + shift, e + shift) for s, e in zip(starts, ends)]


def _union_length(intervals: list[tuple[int, int]]) -> int:
    total, cur_start, cur_end = 0, None, None
    for s, e in sorted(intervals):
        if cur_end is None or s > cur_end:
            if cur_end is not None:
                total += cur_end - cur_start
            cur_start, cur_end = s, e
        else:
            cur_end = max(cur_end, e)
    if cur_end is not None:
        total += cur_end - cur_start
    return total


def plan(recipe: Recipe, plate: dt.datetime | None = None,
         start: dt.datetime | None = None) -> Plan:
    """Lay the steps out against plate time.

    Give `plate` to work backward from when food hits the table, or `start`
    ("start now") to get the plate time forward. Neither gives offsets only.
    """
    rel = relative_times(recipe)
    total = max((e for _, e in rel), default=0)
    steps = [TimedStep(s.number, a - total, b - total, s.mode)
             for s, (a, b) in zip(recipe.steps, rel)]
    active = _union_length([(t.start_s, t.end_s) for t in steps if t.mode == "active"])
    if plate is None and start is not None:
        plate = start + dt.timedelta(seconds=total)
    return Plan(steps=steps, total_s=total, active_s=active, plate=plate)
