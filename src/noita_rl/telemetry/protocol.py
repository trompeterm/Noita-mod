from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

from noita_rl.contracts import (
    MAGIC,
    PROTOCOL_VERSION,
    TELEMETRY_COLS,
    TerminalState,
)

_ROW0 = struct.Struct("<2sBIIiihhHHIBBBiIBI")
_INVENTORY_SLOT = struct.Struct("<BHHHHH")


@dataclass(slots=True)
class InventorySlotTelemetry:
    occupied: int
    item_kind: int
    filename_hash: int
    wand_capacity: int
    spell_count: int
    spell0_id: int


@dataclass(slots=True)
class TelemetryPacket:
    frame: int
    episode: int
    player_x: float
    player_y: float
    vel_x: float
    vel_y: float
    hp: float
    max_hp: float
    gold: int
    active_slot: int
    terminal: TerminalState
    terminal_reason: int
    reward: float
    event_flags: int
    inventory_slots: int
    inventory: list[InventorySlotTelemetry]


def checksum(payload: bytes) -> int:
    value = 0
    for offset in range(0, len(payload), 4):
        chunk = payload[offset : offset + 4].ljust(4, b"\x00")
        value ^= int.from_bytes(chunk, "little")
    return value & 0xFFFFFFFF


def pack_row0(packet: TelemetryPacket) -> bytes:
    body = _ROW0.pack(
        MAGIC,
        PROTOCOL_VERSION,
        packet.frame,
        packet.episode,
        int(packet.player_x),
        int(packet.player_y),
        int(packet.vel_x * 100),
        int(packet.vel_y * 100),
        int(packet.hp * 1000),
        int(packet.max_hp * 1000),
        packet.gold,
        packet.active_slot,
        int(packet.terminal),
        packet.terminal_reason,
        int(packet.reward * 1000),
        packet.event_flags,
        packet.inventory_slots,
        0,
    )
    crc = checksum(body[:-4])
    return body[:-4] + struct.pack("<I", crc)


def unpack_row0(data: bytes) -> TelemetryPacket:
    if len(data) < _ROW0.size:
        raise ValueError(f"Telemetry row too short: {len(data)}")
    values = _ROW0.unpack(data[: _ROW0.size])
    (
        magic,
        version,
        frame,
        episode,
        player_x,
        player_y,
        vel_x,
        vel_y,
        hp,
        max_hp,
        gold,
        active_slot,
        terminal,
        terminal_reason,
        reward_milli,
        event_flags,
        inventory_slots,
        crc,
    ) = values
    if magic != MAGIC:
        raise ValueError("Invalid telemetry magic")
    if version != PROTOCOL_VERSION:
        raise ValueError(f"Unsupported telemetry version {version}")
    if checksum(data[: _ROW0.size - 4]) != crc:
        raise ValueError("Telemetry checksum mismatch")
    return TelemetryPacket(
        frame=frame,
        episode=episode,
        player_x=float(player_x),
        player_y=float(player_y),
        vel_x=vel_x / 100.0,
        vel_y=vel_y / 100.0,
        hp=hp / 1000.0,
        max_hp=max_hp / 1000.0,
        gold=gold,
        active_slot=active_slot,
        terminal=TerminalState(terminal),
        terminal_reason=terminal_reason,
        reward=reward_milli / 1000.0,
        event_flags=event_flags,
        inventory_slots=inventory_slots,
        inventory=[],
    )


def unpack_inventory_row(row: bytes, slots: int) -> list[InventorySlotTelemetry]:
    items: list[InventorySlotTelemetry] = []
    offset = 0
    for _ in range(slots):
        chunk = row[offset : offset + _INVENTORY_SLOT.size]
        if len(chunk) < _INVENTORY_SLOT.size:
            break
        occupied, item_kind, filename_hash, wand_capacity, spell_count, spell0_id = _INVENTORY_SLOT.unpack(
            chunk
        )
        items.append(
            InventorySlotTelemetry(
                occupied=occupied,
                item_kind=item_kind,
                filename_hash=filename_hash,
                wand_capacity=wand_capacity,
                spell_count=spell_count,
                spell0_id=spell0_id,
            )
        )
        offset += _INVENTORY_SLOT.size
    return items


def bytes_to_strip(rows: list[bytes]) -> np.ndarray:
    """Represent telemetry rows as an RGB strip for tests and the mod renderer."""
    width = TELEMETRY_COLS
    height = len(rows)
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    for y, row in enumerate(rows):
        for x, value in enumerate(row[:width]):
            canvas[y, x] = (value, value, value)
    return canvas
