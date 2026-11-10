from pathlib import Path

from noita_rl.curriculum import CurriculumManager


def test_curriculum_advances_on_success():
    root = Path(__file__).resolve().parents[1]
    manager = CurriculumManager(root / "examples" / "curricula" / "starter.json", root / "examples" / "scenarios")
    assert manager.current_stage["id"] == "movement"
    for _ in range(10):
        manager.record_episode(True, 1.0)
    assert manager.current_stage["id"] == "combat"
