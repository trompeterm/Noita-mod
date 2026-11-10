from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def render_scenario_preview(scenario_path: Path, materials_png: Path, output_path: Path) -> Path:
    image = Image.open(materials_png).convert("RGB")
    draw = ImageDraw.Draw(image)

    import json

    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    px, py = scenario["room"]["spawns"]["player"]["x"], scenario["room"]["spawns"]["player"]["y"]
    draw.ellipse((px - 2, py - 2, px + 2, py + 2), outline=(255, 0, 255), width=1)

    for ent in scenario["room"]["spawns"]["entities"]:
        x, y = ent["x"], ent["y"]
        draw.rectangle((x - 1, y - 1, x + 1, y + 1), outline=(0, 255, 255), width=1)

    for cond in scenario["termination"]["success_conditions"]:
        if cond.get("type") == "reach_region":
            x0, y0, x1, y1 = cond["rect"]
            draw.rectangle((x0, y0, x1, y1), outline=(0, 255, 0), width=1)

    title = scenario.get("name") or scenario["id"]
    draw.text((2, 2), title, fill=(255, 255, 255))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return output_path
