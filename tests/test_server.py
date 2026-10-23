import os
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dogear.scale import ingredient_text, scaled_view
from dogear.parse import parse_ingredient, parse_file
from dogear.server import create_app

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def client(tmp_path):
    recipes = tmp_path / "recipes"
    shutil.copytree(ROOT / "recipes", recipes)
    app = create_app(recipes, tmp_path / "data", ROOT / "web")
    with TestClient(app) as c:
        c.recipes = recipes
        yield c


def test_ingredient_text_scales_and_reads_well():
    ing = parse_ingredient("2 tbsp butter")
    assert ingredient_text(ing, 2) == ("1/4 cup", "butter")
    ing = parse_ingredient("2-3 cloves garlic")
    assert ingredient_text(ing, 1) == ("2–3 cloves", "garlic")
    ing = parse_ingredient("1 egg")
    assert ingredient_text(ing, 3) == ("3", "eggs")
    ing = parse_ingredient("salt to taste")
    assert ingredient_text(ing, 2)[0] == ""


def test_scaled_view_clamps_servings():
    r = parse_file(ROOT / "recipes" / "crispy-smashed-potatoes.md").recipe
    assert scaled_view(r, 1000)["servings"] == r.max_yield_value
    assert scaled_view(r, None)["servings"] == r.yield_count
    assert scaled_view(r, 6)["ingredients"][0]["amount"] == "3 lb"


def test_list_and_detail(client):
    data = client.get("/api/recipes").json()["recipes"]
    slugs = {c["slug"] for c in data}
    assert "crispy-smashed-potatoes" in slugs
    card = next(c for c in data if c["slug"] == "crispy-smashed-potatoes")
    assert card["totalS"] > 0 and "potatoes" in card["search"]

    body = client.get("/api/recipes/crispy-smashed-potatoes?servings=8").json()
    assert body["ok"] and body["view"]["servings"] == 8
    assert body["view"]["ingredients"][0]["amount"] == "4 lb"
    assert len(body["recipe"]["timing"]["steps"]) == len(body["recipe"]["steps"])


def test_missing_recipe_is_404(client):
    assert client.get("/api/recipes/nope").status_code == 404
    assert client.get("/api/nothing-here").status_code == 404


def test_rating_and_cook_log(client):
    slug = "garlicky-green-beans"
    assert client.put(f"/api/recipes/{slug}/rating", json={"stars": 4}).json()["rating"] == 4
    h = client.post(f"/api/recipes/{slug}/cooks", json={"servings": 4, "note": " Good "}).json()
    assert h["cooks"][0]["note"] == "Good"
    cook_id = h["cooks"][0]["id"]
    assert client.patch(f"/api/cooks/{cook_id}", json={"note": "Better with more lemon"}).status_code == 200
    card = next(c for c in client.get("/api/recipes").json()["recipes"] if c["slug"] == slug)
    assert card["rating"] == 4 and card["timesCooked"] == 1
    assert client.delete(f"/api/cooks/{cook_id}").status_code == 200
    assert client.put(f"/api/recipes/{slug}/rating", json={"stars": 0}).json()["rating"] == 0
    assert client.put(f"/api/recipes/{slug}/rating", json={"stars": 9}).status_code == 422


def test_edits_on_disk_show_up(client):
    path = client.recipes / "garlicky-green-beans.md"
    text = path.read_text().replace("title: Garlicky Green Beans", "title: Lemony Green Beans")
    path.write_text(text)
    os.utime(path, ns=(time.time_ns(), time.time_ns() + 10_000_000))
    body = client.get("/api/recipes/garlicky-green-beans").json()
    assert body["recipe"]["title"] == "Lemony Green Beans"


def test_broken_file_is_listed_with_issues(client):
    (client.recipes / "broken.md").write_text("no front matter here\n")
    card = next(c for c in client.get("/api/recipes").json()["recipes"] if c["slug"] == "broken")
    assert card["ok"] is False
    body = client.get("/api/recipes/broken").json()
    assert body["recipe"] is None and body["issues"]


def test_front_end_routes_serve_the_shell(client):
    for path in ("/", "/r/crispy-smashed-potatoes", "/cook/crispy-smashed-potatoes"):
        res = client.get(path)
        assert res.status_code == 200 and "<title>Dogear</title>" in res.text
    assert client.get("/js/app.js").status_code == 200
    assert client.get("/js/missing.js").status_code == 404
    assert client.get("/../pyproject.toml").status_code == 404


def test_images_stay_in_their_folder(client):
    (client.recipes / "images").mkdir()
    (client.recipes / "images" / "a.jpg").write_bytes(b"\xff\xd8\xff")
    assert client.get("/api/images/a.jpg").status_code == 200
    assert client.get("/api/images/..%2Fgarlicky-green-beans.md").status_code == 404
