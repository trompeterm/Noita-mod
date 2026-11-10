"""Versioned protocol and space contracts shared by the mod and Python runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

PROTOCOL_VERSION = 1
MAGIC = b"NR"

TELEMETRY_ORIGIN_X = 4
TELEMETRY_ORIGIN_Y = 4
TELEMETRY_CELL_SIZE = 4
TELEMETRY_ROWS = 4
TELEMETRY_COLS = 96
TELEMETRY_BYTES = TELEMETRY_ROWS * TELEMETRY_COLS


class TerminalState(IntEnum):
    ACTIVE = 0
    SUCCESS = 1
    DEATH = 2
    TIMEOUT = 3
    ABORT = 4


class NoitaAction(IntEnum):
    NOOP = 0
    LEFT = 1
    RIGHT = 2
    UP = 3
    DOWN = 4
    JUMP = 5
    FIRE = 6
    KICK = 7
    USE = 8
    THROW = 9
    NEXT_ITEM = 10
    PREV_ITEM = 11


ACTION_NAMES = {action.name.lower(): int(action) for action in NoitaAction}
DISCRETE_ACTION_COUNT = len(NoitaAction)


@dataclass(frozen=True, slots=True)
class TelemetryLayout:
    """Fixed-layout telemetry packet (TELEMETRY_COLS bytes on row 0)."""

    magic: int = 0
    version: int = 2
    frame: int = 4
    episode: int = 8
    player_x: int = 12
    player_y: int = 16
    vel_x: int = 20
    vel_y: int = 22
    hp: int = 24
    max_hp: int = 26
    gold: int = 28
    active_slot: int = 32
    terminal: int = 33
    terminal_reason: int = 34
    reward_milli: int = 35
    event_flags: int = 39
    inventory_slots: int = 43
    checksum: int = 43


TELEMETRY_LAYOUT = TelemetryLayout()
INVENTORY_SLOT_BYTES = 12
MAX_INVENTORY_SLOTS = 10


def default_noita_exe() -> str:
    return r"C:\Program Files (x86)\Steam\steamapps\common\Noita\noita.exe"


def default_mod_install_path() -> str:
    return r"C:\Program Files (x86)\Steam\steamapps\common\Noita\mods\noita_rl"


def default_mod_source_path() -> str:
    from pathlib import Path

    return str(Path(__file__).resolve().parents[2] / "mod")
