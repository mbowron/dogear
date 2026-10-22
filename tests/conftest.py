from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipes"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def recipe_text(body: str, front: str = "title: Test\nyield: 4 servings") -> str:
    return f"---\n{front}\n---\n\n{body}"


@pytest.fixture
def sample_paths():
    return sorted(RECIPES.glob("*.md"))
