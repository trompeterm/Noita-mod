from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from noita_rl.contracts import default_mod_install_path, default_mod_source_path, default_noita_exe


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOITA_RL_", extra="ignore")

    repo_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2])
    noita_exe: Path = Field(default_factory=lambda: Path(default_noita_exe()))
    mod_source: Path = Field(default_factory=lambda: Path(default_mod_source_path()))
    mod_install: Path = Field(default_factory=lambda: Path(default_mod_install_path()))
    window_title: str = "Noita"
    action_repeat: int = 4
    launch_timeout_s: float = 90.0
    step_timeout_s: float = 5.0
    frame_wait_s: float = 0.05
    expected_width: int = 1280
    expected_height: int = 720
