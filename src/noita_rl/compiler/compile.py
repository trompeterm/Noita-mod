from __future__ import annotations

import hashlib
import json
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image

from noita_rl.compiler.materials import DEFAULT_MATERIAL, material_to_rgb
from noita_rl.schema import load_and_validate_json


def scenario_build_dir(output_root: Path, scenario_id: str) -> Path:
    return output_root / "scenarios" / scenario_id


def compile_scenario(scenario_path: Path, output_root: Path) -> Path:
    scenario = load_and_validate_json(scenario_path, "scenario")
    scenario_id = scenario["id"]
    build_dir = scenario_build_dir(output_root, scenario_id)
    build_dir.mkdir(parents=True, exist_ok=True)

    room = scenario["room"]
    width = int(room["width"])
    height = int(room["height"])

    pixels = [[material_to_rgb(DEFAULT_MATERIAL) for _ in range(width)] for _ in range(height)]
    for tile in room.get("tiles", []):
        material = tile["material"]
        x0, y0, x1, y1 = tile["rect"]
        rgb = material_to_rgb(material)
        for y in range(max(0, y0), min(height, y1)):
            for x in range(max(0, x0), min(width, x1)):
                pixels[y][x] = rgb

    image = Image.new("RGB", (width, height))
    image.putdata([value for row in pixels for value in row])
    materials_path = build_dir / "materials.png"
    image.save(materials_path)

    # Empty colors image is accepted by LoadPixelScene.
    colors_path = build_dir / "colors.png"
    Image.new("RGB", (width, height), (0, 0, 0)).save(colors_path)

    materials_used = {DEFAULT_MATERIAL, *(tile["material"] for tile in room.get("tiles", []))}
    color_table: dict[str, str] = {}
    for material in sorted(materials_used):
        r, g, b = material_to_rgb(material)
        color_table[f"{r:02x}{g:02x}{b:02x}"] = material

    manifest_lua = render_manifest_lua(scenario, color_table)
    (build_dir / "manifest.lua").write_text(manifest_lua, encoding="utf-8")
    (build_dir / "scenario.json").write_text(json.dumps(scenario, indent=2), encoding="utf-8")
    return build_dir


def render_manifest_lua(scenario: dict[str, Any], color_table: dict[str, str]) -> str:
    room = scenario["room"]
    entities = room["spawns"]["entities"]
    inventory = scenario["player"]["inventory"]
    rewards = scenario["rewards"]
    termination = scenario["termination"]

    entity_lines = []
    for ent in entities:
        tags = ent.get("tags", [])
        tag_repr = "{" + ", ".join(f'"{tag}"' for tag in tags) + "}"
        entity_lines.append(
            f'    {{ entity = "{ent["entity"]}", x = {ent["x"]}, y = {ent["y"]}, tags = {tag_repr} }},'
        )

    inventory_lines = []
    for idx, item in enumerate(inventory):
        spells = item.get("spells", [])
        spell_repr = "{" + ", ".join(f'"{spell}"' for spell in spells) + "}"
        inventory_lines.append(
            f'    {{ entity = "{item["entity"]}", spells = {spell_repr}, slot = {idx} }},'
        )

    color_lines = [f'    ["{key}"] = "{value}",' for key, value in sorted(color_table.items())]
    success_lines = []
    for cond in termination["success_conditions"]:
        payload = ", ".join(f'{key} = {json.dumps(value)}' for key, value in cond.items())
        success_lines.append(f"    {{ {payload} }},")

    return textwrap.dedent(
        f"""
        -- Auto-generated scenario manifest for {scenario["id"]}

        return {{
            id = "{scenario["id"]}",
            seed = {scenario["seed"]},
            origin = {{ x = {room["origin"]["x"]}, y = {room["origin"]["y"]} }},
            room = {{
                width = {room["width"]},
                height = {room["height"]},
                materials = "mods/noita_rl/files/build/scenarios/{scenario["id"]}/materials.png",
                colors = "mods/noita_rl/files/build/scenarios/{scenario["id"]}/colors.png",
                color_to_material = {{
        {chr(10).join(color_lines)}
                }},
            }},
            player = {{
                hp = {scenario["player"]["hp"]},
                gold = {scenario["player"]["gold"]},
                spawn = {{ x = {room["spawns"]["player"]["x"]}, y = {room["spawns"]["player"]["y"]} }},
                inventory = {{
        {chr(10).join(inventory_lines)}
                }},
            }},
            entities = {{
        {chr(10).join(entity_lines)}
            }},
            rewards = {{
                per_step = {rewards["per_step"]},
                pickup_gold = {rewards["pickup_gold"]},
                enemy_kill = {rewards["enemy_kill"]},
                damage_taken = {rewards["damage_taken"]},
                goal_reached = {rewards["goal_reached"]},
            }},
            termination = {{
                max_steps = {termination["max_steps"]},
                success_conditions = {{
        {chr(10).join(success_lines)}
                }},
            }},
        }}
        """
    ).strip() + "\n"


def activate_scenario(build_dir: Path, active_dir: Path) -> None:
    active_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_dir / "manifest.lua"
    scenario_json = build_dir / "scenario.json"
    (active_dir / "manifest.lua").write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8")
    (active_dir / "scenario.json").write_text(scenario_json.read_text(encoding="utf-8"), encoding="utf-8")
    (active_dir / "scenario_id.txt").write_text(build_dir.name + "\n", encoding="utf-8")


def compile_and_activate(scenario_path: Path, repo_root: Path) -> Path:
    mod_build = repo_root / "mod" / "files" / "build"
    built = compile_scenario(scenario_path, mod_build)
    activate_scenario(built, mod_build / "active")
    return built


def filename_hash(path: str) -> int:
    digest = hashlib.sha1(path.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "little")
