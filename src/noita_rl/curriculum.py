from __future__ import annotations

import json
import random
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from noita_rl.schema import load_and_validate_json


@dataclass(slots=True)
class EpisodeRecord:
    success: bool
    return_value: float


@dataclass
class CurriculumState:
    stage_index: int = 0
    history: dict[str, deque[EpisodeRecord]] = field(default_factory=dict)


class CurriculumManager:
    def __init__(self, curriculum_path: Path, scenarios_root: Path):
        self.curriculum = load_and_validate_json(curriculum_path, "curriculum")
        self.scenarios_root = scenarios_root
        self.state = CurriculumState()
        for stage in self.curriculum["stages"]:
            self.state.history[stage["id"]] = deque(maxlen=max(
                stage["advance"]["window"], stage["regress"]["window"]
            ))

    @property
    def current_stage(self) -> dict:
        return self.curriculum["stages"][self.state.stage_index]

    def choose_scenario(self, rng: random.Random | None = None) -> Path:
        rng = rng or random.Random()
        stage = self.current_stage
        pool = stage["scenarios"]
        weights = [entry["weight"] for entry in pool]
        choice = rng.choices(pool, weights=weights, k=1)[0]
        scenario_id = choice["scenario"]
        path = self.scenarios_root / f"{scenario_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Scenario file not found for curriculum entry: {path}")
        return path

    def record_episode(self, success: bool, return_value: float) -> None:
        stage = self.current_stage
        self.state.history[stage["id"]].append(EpisodeRecord(success=success, return_value=return_value))
        self._maybe_advance()
        self._maybe_regress()

    def _success_rate(self, window: int) -> float:
        stage_id = self.current_stage["id"]
        records = list(self.state.history[stage_id])[-window:]
        if not records:
            return 0.0
        return sum(1 for record in records if record.success) / len(records)

    def _maybe_advance(self) -> None:
        stage = self.current_stage
        window = stage["advance"]["window"]
        if len(self.state.history[stage["id"]]) < window:
            return
        if self._success_rate(window) >= stage["advance"]["min_success_rate"]:
            if self.state.stage_index + 1 < len(self.curriculum["stages"]):
                self.state.stage_index += 1

    def _maybe_regress(self) -> None:
        if self.state.stage_index == 0:
            return
        stage = self.current_stage
        window = stage["regress"]["window"]
        if len(self.state.history[stage["id"]]) < window:
            return
        if self._success_rate(window) <= stage["regress"]["max_success_rate"]:
            self.state.stage_index -= 1

    def save(self, path: Path) -> None:
        serializable = {
            "stage_index": self.state.stage_index,
            "history": {
                stage_id: [{"success": r.success, "return_value": r.return_value} for r in records]
                for stage_id, records in self.state.history.items()
            },
        }
        path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")

    def load(self, path: Path) -> None:
        if not path.exists():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.state.stage_index = int(payload.get("stage_index", 0))
        for stage_id, items in payload.get("history", {}).items():
            dq = self.state.history.setdefault(stage_id, deque())
            dq.clear()
            for item in items:
                dq.append(EpisodeRecord(success=bool(item["success"]), return_value=float(item["return_value"])))
