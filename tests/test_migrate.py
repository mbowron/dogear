import shutil
import sys

from conftest import FIXTURES, ROOT
from dogear.parse import parse_file
from dogear.schedule import plan

sys.path.insert(0, str(ROOT / "tools"))
import migrate_v1  # noqa: E402

V1 = FIXTURES / "v1"


def run(tmp_path, **kw):
    src = tmp_path / "old"
    shutil.copytree(V1, src)
    dst = tmp_path / "new"
    return src, dst, migrate_v1.migrate(src, dst, **kw)


def test_all_fixtures_migrate_and_parse(tmp_path):
    _src, dst, outcomes = run(tmp_path)
    assert [o.status for o in outcomes] == ["migrated", "migrated"]
    for path in sorted(dst.glob("*.md")):
        result = parse_file(path)
        assert result.ok, (path.name, result.issues)
        assert result.recipe.review


def test_roast_timeline_matches_old_schedule(tmp_path):
    _src, dst, _ = run(tmp_path)
    r = parse_file(dst / "sunday-roast-chicken.md").recipe
    p = plan(r)
    starts = [t.start_s // 60 for t in p.steps]
    assert starts == [-95, -95, -80, -10, -10, 0]  # the v1 {at:} offsets
    roast, sauce = r.steps[2], r.steps[4]
    assert (roast.appliance.kind, roast.appliance.temp, roast.duration_s) == ("oven", 425, 4200)
    assert sauce.appliance.kind == "burner"  # 'roasting pan over medium heat'
    assert r.steps[1].with_step == 1 and sauce.with_step == 4


def test_front_matter_mapping(tmp_path):
    _src, dst, _ = run(tmp_path)
    roast = parse_file(dst / "sunday-roast-chicken.md").recipe
    assert roast.course == "main" and roast.source == "https://example.com/roast-chicken"
    assert roast.tags == ["sunday-dinner", "gluten-free"]
    assert roast.summary == "Whole bird, crisp skin: the classic with a quick pan sauce."
    shake = parse_file(dst / "chocolate-pb-shake.md").recipe
    assert shake.nutrition["calories"] == 865 and shake.max_yield == 6
    assert shake.description.startswith("A whole-food gainer shake")
    assert shake.notes.startswith("- **No honey.**")
    assert shake.ingredients[2].grams == 32


def test_optional_line_and_timers_survive(tmp_path):
    _src, dst, _ = run(tmp_path)
    text = (dst / "chocolate-pb-shake.md").read_text()
    assert "{10m, active}\n   Optional: let it sit 10 minutes" in text
    shake = parse_file(dst / "chocolate-pb-shake.md").recipe
    assert shake.steps[2].duration_s == 60


def test_report_lists_drafts_and_old_schedule(tmp_path):
    src, dst, outcomes = run(tmp_path)
    text = migrate_v1.report(outcomes, src, dst)
    assert "| sunday-roast-chicken | migrated | 5 of 6 |" in text
    assert "`{1h10m, passive, oven 425F}`" in text
    assert "- -80 min: Chicken in" in text


def test_existing_files_are_skipped_unless_forced(tmp_path):
    src, dst, _ = run(tmp_path)
    (dst / "chocolate-pb-shake.md").write_text("mine")
    again = migrate_v1.migrate(src, dst)
    assert {o.status for o in again} == {"skipped"}
    assert (dst / "chocolate-pb-shake.md").read_text() == "mine"
    forced = migrate_v1.migrate(src, dst, force=True)
    assert {o.status for o in forced} == {"migrated"}


def test_photos_are_copied(tmp_path):
    src = tmp_path / "old"
    shutil.copytree(V1, src)
    (src / "images").mkdir()
    (src / "images" / "sunday-roast-chicken.jpg").write_bytes(b"jpg")
    migrate_v1.migrate(src, tmp_path / "new")
    assert (tmp_path / "new" / "images" / "sunday-roast-chicken.jpg").read_bytes() == b"jpg"


def test_dry_run_writes_nothing(tmp_path):
    _src, dst, outcomes = run(tmp_path, dry=True)
    assert not dst.exists() and all(o.status == "migrated" for o in outcomes)


def test_guess_appliance():
    g = migrate_v1.guess_appliance
    assert g("Bake at 350°F until set.")[0].label() == "oven 350F"
    assert g("Arrange on a sheet pan.")[0] is None
    assert g("Sear in a hot skillet.")[0].kind == "burner"
    assert g("Brown in a Dutch oven over medium heat.")[0].kind == "burner"
    assert g("Air fryer at 380°F, shaking once.")[0].label() == "air fryer 380F"
    assert g("Chill overnight.")[0].kind == "fridge"
