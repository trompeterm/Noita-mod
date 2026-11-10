from pathlib import Path

from noita_rl.schema import load_and_validate_json, validate_document


def test_example_scenarios_validate():
    root = Path(__file__).resolve().parents[1]
    for name in ("movement_basics", "combat_arena"):
        load_and_validate_json(root / "examples" / "scenarios" / f"{name}.json", "scenario")


def test_curriculum_validates():
    root = Path(__file__).resolve().parents[1]
    load_and_validate_json(root / "examples" / "curricula" / "starter.json", "curriculum")


def test_invalid_scenario_reports_path():
    errors = validate_document("scenario", {"schema_version": 1})
    assert any("<root>" in error for error in errors)
