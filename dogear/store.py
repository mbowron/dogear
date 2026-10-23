"""SQLite for what the recipe files don't hold: ratings and the cook log.

Rows are keyed by recipe slug (the file name), so renaming a file orphans its
history. The database lives in the data folder, never in the recipes folder.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import threading
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS ratings (
    slug   TEXT PRIMARY KEY,
    stars  INTEGER NOT NULL CHECK (stars BETWEEN 1 AND 5)
);
CREATE TABLE IF NOT EXISTS cooks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    slug       TEXT NOT NULL,
    cooked_on  TEXT NOT NULL,          -- YYYY-MM-DD, the cook's local date
    servings   REAL,
    note       TEXT
);
CREATE INDEX IF NOT EXISTS cooks_slug ON cooks (slug, cooked_on);
"""


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def _run(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock, self._db:
            return self._db.execute(sql, args).fetchall()

    # ratings

    def set_rating(self, slug: str, stars: int) -> None:
        if stars == 0:
            self._run("DELETE FROM ratings WHERE slug = ?", (slug,))
        else:
            self._run("INSERT INTO ratings (slug, stars) VALUES (?, ?) "
                      "ON CONFLICT (slug) DO UPDATE SET stars = excluded.stars", (slug, stars))

    # cook log

    def add_cook(self, slug: str, cooked_on: dt.date | None = None,
                 servings: float | None = None, note: str | None = None) -> int:
        day = (cooked_on or dt.date.today()).isoformat()
        with self._lock, self._db:
            cur = self._db.execute(
                "INSERT INTO cooks (slug, cooked_on, servings, note) VALUES (?, ?, ?, ?)",
                (slug, day, servings, (note or "").strip() or None))
            return int(cur.lastrowid)

    def update_cook(self, cook_id: int, note: str | None) -> bool:
        with self._lock, self._db:
            cur = self._db.execute("UPDATE cooks SET note = ? WHERE id = ?",
                                   ((note or "").strip() or None, cook_id))
            return cur.rowcount > 0

    def delete_cook(self, cook_id: int) -> bool:
        with self._lock, self._db:
            return self._db.execute("DELETE FROM cooks WHERE id = ?", (cook_id,)).rowcount > 0

    def history(self, slug: str) -> dict[str, Any]:
        rating = self._run("SELECT stars FROM ratings WHERE slug = ?", (slug,))
        cooks = self._run("SELECT id, cooked_on, servings, note FROM cooks WHERE slug = ? "
                          "ORDER BY cooked_on DESC, id DESC", (slug,))
        return {
            "rating": rating[0]["stars"] if rating else 0,
            "cooks": [{"id": r["id"], "date": r["cooked_on"], "servings": r["servings"],
                       "note": r["note"]} for r in cooks],
        }

    def summary(self) -> dict[str, dict[str, Any]]:
        """Per slug: rating, times cooked, last cooked date."""
        out: dict[str, dict[str, Any]] = {}
        for r in self._run("SELECT slug, COUNT(*) AS n, MAX(cooked_on) AS last "
                           "FROM cooks GROUP BY slug"):
            out[r["slug"]] = {"rating": 0, "timesCooked": r["n"], "lastCooked": r["last"]}
        for r in self._run("SELECT slug, stars FROM ratings"):
            out.setdefault(r["slug"], {"rating": 0, "timesCooked": 0, "lastCooked": None})
            out[r["slug"]]["rating"] = r["stars"]
        return out
