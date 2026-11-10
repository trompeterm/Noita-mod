"""Material color mapping for compiled pixel scenes."""

from __future__ import annotations

# Arbitrary RGB keys mapped to Noita material names at runtime via color_to_material_table.
MATERIAL_COLORS: dict[str, tuple[int, int, int]] = {
    "air": (0, 0, 0),
    "rock_static_glow": (64, 64, 64),
    "rock_static": (48, 48, 48),
    "wood_static": (120, 72, 24),
    "snow_static": (220, 220, 255),
    "lava": (255, 96, 16),
    "water": (32, 96, 220),
    "grass": (32, 180, 48),
    "gold_static": (255, 210, 32),
}

DEFAULT_MATERIAL = "rock_static"


def material_to_rgb(material: str) -> tuple[int, int, int]:
    return MATERIAL_COLORS.get(material, MATERIAL_COLORS[DEFAULT_MATERIAL])
