"""Decode the RL-agent telemetry strip drawn by mod/files/agent/agent.lua.

The mod draws the packet as a grid of solid-colour cells in the top-left corner of the
game, three bytes per cell (R, G, B), AGENT_COLS cells per row. The first cell is always
("N", "R", version) = (78, 82, 2), which is how the strip is found in a screenshot without
knowing the window border, the GUI scale or the exact cell size in pixels.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum

import numpy as np

from noita_rl.telemetry.protocol import checksum

AGENT_VERSION = 3
AGENT_COLS = 96
RAYS = 16
ENEMY_SLOTS = 8
GOLD_SLOTS = 4
RAY_RANGE = 160.0
# Action keys in the mod's bit order (mod/files/agent/agent.lua, A.BUTTONS).
BUTTONS = ("left", "right", "up", "down", "jump", "fire", "kick", "interact",
           "aim_left", "aim_right", "aim_up", "aim_down")
LOCATOR = (78, 82, AGENT_VERSION)

_HEAD = "<2sBH" "II" "B" "BBHB" "BB" "II" "ii" "hhhh" "HHI" "B" "Hhh" "HH" "hhH" "BB"
_BODY = "hhH" * ENEMY_SLOTS + "hh" * GOLD_SLOTS + "B" + "H" * RAYS * 2
_PACKET = struct.Struct(_HEAD + _BODY + "I")
PACKET_BYTES = _PACKET.size


class Objective(IntEnum):
    REACH_GOAL = 1
    KILL_ALL = 2
    COLLECT_GOLD = 3
    SURVIVE = 4


class Reason(IntEnum):
    NONE = 0
    SUCCESS = 1
    DIED = 2
    LEFT_ROOM = 3
    TIMEOUT = 4


@dataclass(slots=True)
class Target:
    """Something relative to the player: dx, dy in world pixels (target minus player)."""

    dx: float
    dy: float
    hp: float = 0.0


@dataclass(slots=True)
class AgentPacket:
    frame: int
    episode: int
    cmd_seq: int
    room_index: int
    room_count: int
    attempt: int
    objective: Objective
    terminal: bool
    reason: Reason
    steps: int
    max_steps: int
    reward: float
    episode_return: float
    x: float  # relative to the room's top-left corner
    y: float
    vx: float
    vy: float
    hp: float
    max_hp: float
    gold: int
    on_ground: bool
    has_goal: bool
    in_goal: bool
    overlay: bool
    buttons: frozenset[str]  # action keys the mod saw held this frame
    aim_x: float  # aim direction (unit vector)
    aim_y: float
    mana: int
    mana_max: int
    goal_dx: float
    goal_dy: float
    goal_dist: float
    enemies_alive: int
    gold_left: int
    enemies: list[Target] = field(default_factory=list)  # nearest first, at most 8
    golds: list[Target] = field(default_factory=list)  # nearest first, at most 4
    rays: list[float] = field(default_factory=list)  # distance to terrain, 16 directions
    liquid_rays: list[float] = field(default_factory=list)  # distance to terrain or liquid


def parse_packet(data: bytes) -> AgentPacket:
    if len(data) < PACKET_BYTES:
        raise ValueError(f"Agent packet too short: {len(data)} < {PACKET_BYTES}")
    if tuple(data[:3]) != LOCATOR:
        raise ValueError("Not an agent packet (bad magic or version)")
    length = int.from_bytes(data[3:5], "little")
    if length != PACKET_BYTES - 4:
        raise ValueError(f"Agent packet length {length} != {PACKET_BYTES - 4}: mod and Python out of sync")
    v = _PACKET.unpack(data[:PACKET_BYTES])
    if checksum(data[:length]) != v[-1]:
        raise ValueError("Agent packet checksum mismatch")
    (_, _, _, frame, episode, cmd_seq, room_index, room_count, attempt, objective, terminal, reason,
     steps, max_steps, reward, ret, x, y, vx, vy, hp, max_hp, gold, flags, buttons, aim_x, aim_y,
     mana, mana_max, goal_dx, goal_dy, goal_dist, enemies_alive, gold_left) = v[:34]
    i = 34
    enemies = []
    for _ in range(ENEMY_SLOTS):
        dx, dy, ehp = v[i : i + 3]
        i += 3
        if len(enemies) < enemies_alive:
            enemies.append(Target(dx / 10, dy / 10, ehp / 100))
    golds = []
    for _ in range(GOLD_SLOTS):
        dx, dy = v[i : i + 2]
        i += 2
        if len(golds) < gold_left:
            golds.append(Target(dx / 10, dy / 10))
    ray_count = v[i]
    i += 1
    rays = [d / 10 for d in v[i : i + ray_count]]
    liquid = [d / 10 for d in v[i + ray_count : i + 2 * ray_count]]
    return AgentPacket(
        frame=frame, episode=episode, cmd_seq=cmd_seq, room_index=room_index, room_count=room_count,
        attempt=attempt, objective=Objective(objective), terminal=bool(terminal), reason=Reason(reason),
        steps=steps, max_steps=max_steps, reward=reward / 1000, episode_return=ret / 1000,
        x=x / 10, y=y / 10, vx=vx / 10, vy=vy / 10, hp=hp / 100, max_hp=max_hp / 100, gold=gold,
        on_ground=bool(flags & 1), has_goal=bool(flags & 2), in_goal=bool(flags & 4), overlay=bool(flags & 8),
        buttons=frozenset(name for bit, name in enumerate(BUTTONS) if buttons >> bit & 1),
        aim_x=aim_x / 1000, aim_y=aim_y / 1000,
        mana=mana, mana_max=mana_max, goal_dx=goal_dx / 10, goal_dy=goal_dy / 10, goal_dist=goal_dist / 10,
        enemies_alive=enemies_alive, gold_left=gold_left, enemies=enemies, golds=golds,
        rays=rays, liquid_rays=liquid,
    )


def sensor_vector(packet: AgentPacket) -> np.ndarray:
    """A flat float32 feature vector, roughly normalised, for a policy network."""
    room_w, room_h = 256.0, 160.0
    values = [
        packet.x / room_w, packet.y / room_h, packet.vx / 200, packet.vy / 200,
        packet.hp / max(packet.max_hp, 0.01), float(packet.on_ground),
        packet.mana / max(packet.mana_max, 1),
        1 - packet.steps / max(packet.max_steps, 1),
        float(packet.has_goal), packet.goal_dx / room_w, packet.goal_dy / room_h, float(packet.in_goal),
        packet.enemies_alive / ENEMY_SLOTS, packet.gold_left / GOLD_SLOTS,
    ]
    values += [1.0 if packet.objective == o else 0.0 for o in Objective]
    for slot in range(ENEMY_SLOTS):
        e = packet.enemies[slot] if slot < len(packet.enemies) else None
        values += [e.dx / room_w, e.dy / room_h, 1.0] if e else [0.0, 0.0, 0.0]
    for slot in range(GOLD_SLOTS):
        g = packet.golds[slot] if slot < len(packet.golds) else None
        values += [g.dx / room_w, g.dy / room_h, 1.0] if g else [0.0, 0.0, 0.0]
    values += [d / RAY_RANGE for d in packet.rays]
    values += [d / RAY_RANGE for d in packet.liquid_rays]
    return np.asarray(values, dtype=np.float32)


SENSOR_VECTOR_SIZE = 14 + len(Objective) + 3 * ENEMY_SLOTS + 3 * GOLD_SLOTS + 2 * RAYS


def _locate(pixels: np.ndarray, search: int = 240) -> tuple[int, int, int, int] | None:
    """Top-left pixel of the locator cell and its run length in x and y."""
    region = pixels[:search, :search, :3].astype(np.int16)
    mask = (np.abs(region - np.array(LOCATOR, dtype=np.int16)) <= 2).all(axis=2)
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return None
    y0 = int(ys.min())
    x0 = int(xs[ys == y0].min())
    run_x = 0
    while x0 + run_x < mask.shape[1] and mask[y0, x0 + run_x]:
        run_x += 1
    run_y = 0
    while y0 + run_y < mask.shape[0] and mask[y0 + run_y, x0]:
        run_y += 1
    return x0, y0, run_x, run_y


def _read(pixels: np.ndarray, x0: float, y0: float, pitch: float, cells: int) -> bytes:
    index = np.arange(cells)
    cols, rows = index % AGENT_COLS, index // AGENT_COLS
    xs = np.floor(x0 + (cols + 0.5) * pitch).astype(int)
    ys = np.floor(y0 + (rows + 0.5) * pitch).astype(int)
    if xs.max() >= pixels.shape[1] or ys.max() >= pixels.shape[0]:
        raise ValueError("Strip runs off the captured image")
    return pixels[ys, xs, :3].astype(np.uint8).tobytes()


def decode_agent_strip(pixels: np.ndarray, hint: tuple[float, float, float] | None = None
                       ) -> tuple[AgentPacket, tuple[float, float, float]]:
    """Find and decode the strip in an RGB screenshot (H x W x 3).

    Returns the packet and (x0, y0, pitch); pass that back as ``hint`` on the next frame
    to skip the search. Raises ValueError if no valid strip is visible.
    """
    cells = -(-PACKET_BYTES // 3)
    if hint is not None:
        try:
            return parse_packet(_read(pixels, *hint, cells)), hint
        except ValueError:
            pass
    found = _locate(pixels)
    if found is None:
        raise ValueError("Telemetry strip not found: is Noita in RL agent mode and fully visible?")
    x0, y0, run_x, run_y = found
    run = max(run_x, run_y)
    errors = []
    # The cell edge may be blended with its neighbour, so try nearby pitches and origins.
    for pitch in np.arange(max(1.0, run - 0.75), run + 2.0, 0.05):
        for shift in (0.0, -0.5, 0.5):
            guess = (x0 + shift, y0 + shift, float(pitch))
            try:
                return parse_packet(_read(pixels, *guess, cells)), guess
            except ValueError as error:
                errors.append(str(error))
    raise ValueError(f"Telemetry strip found at {x0},{y0} but did not decode ({errors[-1]})")
