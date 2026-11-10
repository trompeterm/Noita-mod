from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any

import gymnasium as gym
import numpy as np

from noita_rl.actions import action_space, encode_action, repeated_action_vector
from noita_rl.compiler.compile import compile_and_activate
from noita_rl.contracts import TerminalState
from noita_rl.curriculum import CurriculumManager
from noita_rl.platform.windows.capture import MssFrameCapture
from noita_rl.platform.windows.input import TAP_ACTIONS, WindowsInputController
from noita_rl.platform.windows.process import WindowsProcessController
from noita_rl.settings import Settings
from noita_rl.telemetry.decode import decode_observation


class NoitaRLEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(
        self,
        scenario_path: Path | None = None,
        curriculum_path: Path | None = None,
        settings: Settings | None = None,
        auto_launch: bool = True,
    ) -> None:
        super().__init__()
        self.settings = settings or Settings()
        self._scenario_path = scenario_path
        self._curriculum = (
            CurriculumManager(curriculum_path, self.settings.repo_root / "examples" / "scenarios")
            if curriculum_path is not None
            else None
        )
        self._auto_launch = auto_launch
        self._episode = 0
        self._step_count = 0
        self._last_frame = -1
        self._cumulative_reward = 0.0

        self._process = WindowsProcessController(str(self.settings.noita_exe), [])
        self._capture = MssFrameCapture()
        self._input = WindowsInputController()
        self._window = None

        self.action_space = action_space()
        self.observation_space = gym.spaces.Dict(
            {
                "pixels": gym.spaces.Box(0, 255, shape=(self.settings.expected_height, self.settings.expected_width, 3), dtype=np.uint8),
                "player": gym.spaces.Dict(
                    {
                        "x": gym.spaces.Box(-np.inf, np.inf, (), dtype=np.float32),
                        "y": gym.spaces.Box(-np.inf, np.inf, (), dtype=np.float32),
                        "hp": gym.spaces.Box(0, np.inf, (), dtype=np.float32),
                        "gold": gym.spaces.Discrete(1_000_000),
                    }
                ),
                "frame": gym.spaces.Discrete(2_000_000_000),
                "terminal": gym.spaces.Discrete(8),
            }
        )

    def _choose_scenario(self, seed: int | None) -> Path:
        if self._scenario_path is not None:
            return self._scenario_path
        if self._curriculum is not None:
            rng = random.Random(seed)
            return self._curriculum.choose_scenario(rng)
        default = self.settings.repo_root / "examples" / "scenarios" / "movement_basics.json"
        if not default.exists():
            raise FileNotFoundError("No scenario configured and default example scenario is missing")
        return default

    def _launch_if_needed(self) -> None:
        if not self._auto_launch:
            self._window = self._process.wait_for_window(self.settings.window_title, self.settings.launch_timeout_s)
            return
        if not self._process.is_running():
            self._process.launch()
        self._window = self._process.wait_for_window(self.settings.window_title, self.settings.launch_timeout_s)

    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None):
        super().reset(seed=seed)
        scenario_path = self._choose_scenario(seed)
        compile_and_activate(scenario_path, self.settings.repo_root)
        self._episode += 1
        self._step_count = 0
        self._cumulative_reward = 0.0
        self._last_frame = -1
        self._input.reset()

        if self._auto_launch:
            self._process.terminate()
            self._launch_if_needed()

        pixels, info = self._wait_for_fresh_observation()
        obs = self._to_observation(pixels)
        return obs, info

    def step(self, action: int):
        decision = encode_action(action)
        tap = TAP_ACTIONS.get(decision)

        reward = 0.0
        terminated = False
        truncated = False
        info: dict[str, Any] = {}

        for _ in range(self.settings.action_repeat):
            self._input.apply_action(repeated_action_vector(decision), taps=[])
            pixels, step_info = self._wait_for_fresh_observation()
            decoded = decode_observation(pixels)
            reward += decoded.telemetry.reward
            self._step_count += 1
            info.update(step_info)
            if decoded.telemetry.terminal != TerminalState.ACTIVE:
                terminated = True
                break

        if tap is not None:
            self._input.apply_action(repeated_action_vector(decision), taps=tap)

        self._cumulative_reward += reward
        obs = self._to_observation(pixels)
        if self._step_count >= info.get("max_steps", 10_000):
            truncated = True
        return obs, reward, terminated, truncated, info

    def close(self) -> None:
        self._input.reset()
        if self._auto_launch:
            self._process.terminate()

    def _wait_for_fresh_observation(self) -> tuple[np.ndarray, dict[str, Any]]:
        assert self._window is not None
        deadline = time.time() + self.settings.step_timeout_s
        info: dict[str, Any] = {}
        pixels: np.ndarray | None = None
        while time.time() < deadline:
            pixels = self._capture.capture(self._window)
            if pixels.shape[1] < 64 or pixels.shape[0] < 64:
                time.sleep(self.settings.frame_wait_s)
                continue
            try:
                decoded = decode_observation(pixels)
            except (ValueError, IndexError):
                time.sleep(self.settings.frame_wait_s)
                continue
            if decoded.telemetry.frame > self._last_frame:
                self._last_frame = decoded.telemetry.frame
                info["telemetry"] = decoded.telemetry
                info["max_steps"] = 10_000
                return pixels, info
            time.sleep(self.settings.frame_wait_s)
        if pixels is None:
            raise TimeoutError("Failed to capture window pixels")
        raise TimeoutError("Timed out waiting for a fresh telemetry frame")

    def _to_observation(self, pixels: np.ndarray) -> dict[str, Any]:
        decoded = decode_observation(pixels)
        telemetry = decoded.telemetry
        return {
            "pixels": pixels,
            "player": {
                "x": np.float32(telemetry.player_x),
                "y": np.float32(telemetry.player_y),
                "hp": np.float32(telemetry.hp),
                "gold": int(telemetry.gold),
            },
            "frame": int(telemetry.frame),
            "terminal": int(telemetry.terminal),
        }
