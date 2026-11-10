from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from noita_rl.contracts import (
    TELEMETRY_CELL_SIZE,
    TELEMETRY_COLS,
    TELEMETRY_ORIGIN_X,
    TELEMETRY_ORIGIN_Y,
    TELEMETRY_ROWS,
)
from noita_rl.telemetry.protocol import TelemetryPacket, unpack_inventory_row, unpack_row0


@dataclass(slots=True)
class DecodedObservation:
    pixels: np.ndarray
    telemetry: TelemetryPacket
    inventory: list


def decode_strip_from_pixels(pixels: np.ndarray) -> list[bytes]:
    rows: list[bytes] = []
    for row in range(TELEMETRY_ROWS):
        row_bytes: list[int] = []
        base_y = TELEMETRY_ORIGIN_Y + row * TELEMETRY_CELL_SIZE
        for col in range(TELEMETRY_COLS):
            base_x = TELEMETRY_ORIGIN_X + col * TELEMETRY_CELL_SIZE
            sample = pixels[base_y : base_y + TELEMETRY_CELL_SIZE, base_x : base_x + TELEMETRY_CELL_SIZE]
            if sample.size == 0:
                row_bytes.append(0)
                continue
            row_bytes.append(int(sample[..., 0].mean()))
        rows.append(bytes(row_bytes))
    return rows


def decode_observation(pixels: np.ndarray) -> DecodedObservation:
    rows = decode_strip_from_pixels(pixels)
    packet = unpack_row0(rows[0])
    inventory = unpack_inventory_row(rows[1], packet.inventory_slots)
    packet.inventory = inventory
    return DecodedObservation(pixels=pixels, telemetry=packet, inventory=inventory)
