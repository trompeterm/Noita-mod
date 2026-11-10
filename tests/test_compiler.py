import json
from pathlib import Path

from noita_rl.compiler.compile import compile_scenario


def test_compile_scenario_is_deterministic(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    scenario = root / "examples" / "scenarios" / "movement_basics.json"
    first = compile_scenario(scenario, tmp_path / "a")
    second = compile_scenario(scenario, tmp_path / "b")
    assert (first / "materials.png").read_bytes() == (second / "materials.png").read_bytes()
    assert (first / "manifest.lua").read_text(encoding="utf-8") == (
        second / "manifest.lua"
    ).read_text(encoding="utf-8")
    manifest_scenario = json.loads((first / "scenario.json").read_text(encoding="utf-8"))
    assert manifest_scenario["id"] == "movement_basics"
