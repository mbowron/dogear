"""The web app: a JSON API over the recipes folder, plus the static front end.

Run it with `python -m dogear serve`. Configuration comes from arguments or
environment variables:

  DOGEAR_RECIPES  folder of recipe .md files     (default: ./recipes)
  DOGEAR_DATA     folder for dogear.db           (default: ./data)

The recipes folder is the source of truth. Files are re-read whenever they
change on disk, so editing a recipe in a text editor shows up on reload.
"""

from __future__ import annotations

import datetime as dt
import os
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import __version__
from .parse import ParseResult, parse_file
from .scale import scaled_view
from .store import Store

WEB_DIR = Path(os.environ.get("DOGEAR_WEB", Path(__file__).resolve().parent.parent / "web"))
IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}


# --------------------------------------------------------------------------
# Recipes folder
# --------------------------------------------------------------------------


@dataclass
class _Entry:
    mtime_ns: int
    size: int
    result: ParseResult


class Library:
    """Parsed recipes, re-parsed only when a file changes."""

    def __init__(self, folder: str | Path) -> None:
        self.folder = Path(folder)
        self._cache: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def scan(self) -> dict[str, ParseResult]:
        with self._lock:
            seen: dict[str, _Entry] = {}
            for path in sorted(self.folder.glob("*.md")):
                st = path.stat()
                old = self._cache.get(path.stem)
                if old and old.mtime_ns == st.st_mtime_ns and old.size == st.st_size:
                    seen[path.stem] = old
                else:
                    seen[path.stem] = _Entry(st.st_mtime_ns, st.st_size, parse_file(path))
            self._cache = seen
            return {slug: e.result for slug, e in seen.items()}

    def get(self, slug: str) -> ParseResult | None:
        return self.scan().get(slug)


# --------------------------------------------------------------------------
# JSON shapes
# --------------------------------------------------------------------------


def _issues(result: ParseResult) -> list[dict[str, Any]]:
    return [{"level": i.level, "message": i.message, "line": i.line}
            for i in result.issues if i.level != "note"]


def card(slug: str, result: ParseResult, stats: dict[str, Any] | None) -> dict[str, Any]:
    """One row of the recipe box."""
    stats = stats or {"rating": 0, "timesCooked": 0, "lastCooked": None}
    r = result.recipe
    if r is None:
        return {"slug": slug, "title": slug.replace("-", " ").capitalize(), "ok": False,
                "course": None, "search": slug, **stats}
    d = r.to_dict()
    words = [r.title, r.category or "", " ".join(r.tags)] + [i.item for i in r.ingredients]
    return {
        "slug": slug, "title": r.title, "ok": result.ok, "review": r.review,
        "course": r.course, "category": r.category, "tags": r.tags,
        "summary": r.summary, "image": r.image, "added": r.added,
        "totalS": d["timing"]["totalS"], "activeS": d["timing"]["activeS"],
        "holdS": r.hold_s, "search": " ".join(words).lower(), **stats,
    }


class RatingIn(BaseModel):
    stars: int = Field(ge=0, le=5)


class CookIn(BaseModel):
    date: dt.date | None = None
    servings: float | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=4000)


class NoteIn(BaseModel):
    note: str | None = Field(default=None, max_length=4000)


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------


def create_app(recipes: str | Path | None = None, data: str | Path | None = None,
               web: str | Path | None = None) -> FastAPI:
    recipes_dir = Path(recipes or os.environ.get("DOGEAR_RECIPES", "recipes")).resolve()
    data_dir = Path(data or os.environ.get("DOGEAR_DATA", "data")).resolve()
    web_dir = Path(web or WEB_DIR).resolve()
    if not recipes_dir.is_dir():
        raise SystemExit(f"Recipes folder not found: {recipes_dir}")

    library = Library(recipes_dir)
    store = Store(data_dir / "dogear.db")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        store.close()

    app = FastAPI(title="Dogear", version=__version__, docs_url="/api/docs",
                  openapi_url="/api/openapi.json", redoc_url=None, lifespan=lifespan)
    app.state.library, app.state.store = library, store

    def need(slug: str) -> ParseResult:
        result = library.get(slug)
        if result is None:
            raise HTTPException(404, f"No recipe named {slug!r}")
        return result

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__, "recipes": len(library.scan())}

    @app.get("/api/recipes")
    def list_recipes() -> dict[str, Any]:
        stats = store.summary()
        cards = [card(s, r, stats.get(s)) for s, r in library.scan().items()]
        return {"recipes": cards}

    @app.get("/api/recipes/{slug}")
    def get_recipe(slug: str, servings: float | None = None) -> dict[str, Any]:
        result = need(slug)
        body: dict[str, Any] = {"slug": slug, "ok": result.ok, "issues": _issues(result),
                                "history": store.history(slug), "recipe": None, "view": None}
        if result.recipe is not None:
            body["recipe"] = result.recipe.to_dict()
            body["view"] = scaled_view(result.recipe, servings)
        return body

    @app.put("/api/recipes/{slug}/rating")
    def put_rating(slug: str, body: RatingIn) -> dict[str, Any]:
        need(slug)
        store.set_rating(slug, body.stars)
        return store.history(slug)

    @app.post("/api/recipes/{slug}/cooks", status_code=201)
    def post_cook(slug: str, body: CookIn) -> dict[str, Any]:
        need(slug)
        store.add_cook(slug, body.date, body.servings, body.note)
        return store.history(slug)

    @app.patch("/api/cooks/{cook_id}")
    def patch_cook(cook_id: int, body: NoteIn) -> dict[str, bool]:
        if not store.update_cook(cook_id, body.note):
            raise HTTPException(404, "No such cook")
        return {"ok": True}

    @app.delete("/api/cooks/{cook_id}")
    def delete_cook(cook_id: int) -> dict[str, bool]:
        if not store.delete_cook(cook_id):
            raise HTTPException(404, "No such cook")
        return {"ok": True}

    @app.get("/api/images/{name}")
    def image(name: str) -> FileResponse:
        path = (recipes_dir / "images" / name).resolve()
        if path.parent != (recipes_dir / "images").resolve() or path.suffix.lower() not in IMAGE_TYPES \
                or not path.is_file():
            raise HTTPException(404, "No such image")
        return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def api_404(rest: str) -> JSONResponse:
        return JSONResponse({"detail": "Not found"}, status_code=404)

    # Front end: real files when they exist, otherwise the app shell so that
    # links like /r/crispy-smashed-potatoes work on reload.
    @app.get("/{path:path}", include_in_schema=False)
    def front(path: str, request: Request) -> FileResponse:
        target = (web_dir / path).resolve()
        if path and target.is_file() and web_dir in target.parents:
            return FileResponse(target, headers={"Cache-Control": "no-cache"})
        if Path(path).suffix:  # a missing asset, not an app route
            raise HTTPException(404, "Not found")
        return FileResponse(web_dir / "index.html", headers={"Cache-Control": "no-cache"})

    return app


def serve(host: str = "0.0.0.0", port: int = 8000, recipes: str | None = None,
          data: str | None = None) -> None:
    import uvicorn

    uvicorn.run(create_app(recipes, data), host=host, port=port, proxy_headers=True,
                forwarded_allow_ips="*", log_level="info")
