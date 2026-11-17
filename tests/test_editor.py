"""Exercise the actual Lua 5.1 editor with a small, explicit game API harness."""
import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from lupa.lua51 import LuaRuntime
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "mod/files/editor"


@pytest.fixture
def lua():
    runtime = LuaRuntime(unpack_returned_tuples=True)
    runtime.execute((EDITOR / "model.lua").read_text())
    return runtime


@pytest.fixture
def game(lua):
    """Load editor.lua against mocked Noita APIs; globals expose the fake game state."""
    lua.execute('''
        settings, stamps, killed = {}, {}, {}
        buttons, frame, hp, money, px, py, enabled = {}, 1, 4, 0, 28, 132, false
        alive = {}
        GUI_OPTION = {NonInteractive = 1}
        function dofile_once() end
        function ModSettingGet(key) return settings[key] end
        function ModSettingSet(key, value) settings[key] = value end
        local function sorted_keys()
            local keys = {}
            for key in pairs(settings) do table.insert(keys, key) end
            table.sort(keys)
            return keys
        end
        function ModSettingGetCount() return #sorted_keys() end
        function ModSettingGetAtIndex(i)
            local key = sorted_keys()[i + 1]
            if key then return key, settings[key], settings[key] end
        end
        function EntityGetFirstComponentIncludingDisabled(_, kind) return kind end
        function ComponentSetValue2(_, key, value)
            if key == "hp" then hp = value elseif key == "money" then money = value
            elseif key == "enabled" then enabled = value end
        end
        function ComponentGetValue2(_, key)
            if key == "hp" then return hp elseif key == "money" then return money end
        end
        function EntitySetComponentIsEnabled() error("never disable player components") end
        -- Spawn, then run the one-step-per-frame setup until the editor is ready.
        function boot()
            noita_editor_spawn(1)
            for _ = 1, 7 do noita_editor_pre_update() end
        end
        function EntitySetTransform(_, x, y) px, py = x, y end
        function EntityGetTransform() return px, py end
        function EntityGetIsAlive(id) return alive[id] ~= false end
        function EntityGetInRadiusWithTag() return {} end
        function EntityKill(id) killed[id] = true end
        next_entity = 200
        function EntityLoad() next_entity = next_entity + 1; return next_entity end
        function LoadPixelScene(...) table.insert(stamps, {...}) end
        function GameSetCameraFree() end
        function GameSetCameraPos() end
        function GameGetFrameNum() return frame end
        function InputIsMouseButtonDown() return false end
        function noita_rl_apply_loadout() hp = 4 end
        function GuiCreate() return 1 end
        function GuiStartFrame() end
        function GuiText() end
        function GuiOptionsAddForNextWidget() end
        function GuiColorSetForNextWidget() end
        function GuiBeginAutoBox() end
        function GuiEndAutoBoxNinePiece() end
        function GuiButton(_, id)
            local clicked = buttons[id]; buttons[id] = nil; return clicked
        end
        function GuiImageButton() return false, false end
        function GuiGetPreviousWidgetInfo() return false, false, false end
    ''')
    lua.execute((EDITOR / "editor.lua").read_text())
    return lua


def editor_message(lua):
    """Read the editor's private state table (upvalue E) for assertions."""
    return lua.eval('''(function()
        local i = 1
        while true do
            local name, value = debug.getupvalue(noita_editor_update, i)
            if not name then return nil end
            if name == "E" then return value.message end
            i = i + 1
        end
    end)()''')


def test_blueprint_round_trip_and_reject_invalid_saves(lua):
    lua.execute('''
        local M = EditorModel
        local room = M.new()
        M.paint(room, 100, "material", 5)
        M.paint(room, 101, "entity", 2)
        M.paint(room, 102, "spawn", 1)
        local encoded = M.encode(room)
        local restored = M.decode(encoded)
        assert(M.encode(restored) == encoded)
        assert(restored.tiles[100] == 5 and restored.objects[101] == 2)
        assert(restored.spawn == 102)
        assert(M.decode(nil) == nil)
        assert(M.decode("return os.execute('bad')") == nil)
        assert(M.decode(encoded .. "!") == nil)
        assert(M.decode(encoded .. string.rep("x", 30)) == nil) -- id longer than 32
        assert(M.decode(string.gsub(encoded, "NRE2:102:", "NRE2:0:")) == nil)
        assert(M.decode(string.gsub(encoded, "NRE2:", "NRE1:")) == nil)
        assert(M.decode(string.gsub(encoded, ":my_room$", ":9bad")) == nil)
        assert(M.decode(string.gsub(encoded, ":1:3:my_room$", ":7:3:my_room")) == nil)
        assert(M.decode(string.gsub(encoded, ":27,14,30,17:", ":27,14,40,17:")) == nil)
        room.goal = nil
        assert(M.decode(M.encode(room)).goal == nil)
    ''')


def test_version_1_saves_still_load_with_default_task(lua):
    lua.execute('''
        local M = EditorModel
        local tiles, objects = string.match(M.encode(M.new()), "^NRE2:%d+:([1-8]+):([0-3]+):")
        local room = M.decode("NRE1:100:" .. tiles .. ":" .. objects)
        assert(room and room.spawn == 100 and room.objective == 1 and room.goal and room.name == "my_room")
        assert(string.sub(M.encode(room), 1, 9) == "NRE2:100:")
    ''')


def test_paint_preserves_player_and_removes_conflicting_objects(lua):
    lua.execute('''
        local M, room = EditorModel, EditorModel.new()
        M.paint(room, room.spawn, "material", 4)
        M.paint(room, room.spawn, "entity", 1)
        assert(room.tiles[room.spawn] == 1 and room.objects[room.spawn] == nil)
        M.paint(room, 100, "entity", 1)
        assert(room.tiles[100] == 1 and room.objects[100] == 1)
        M.paint(room, 100, "material", 2)
        assert(room.objects[100] == nil and room.tiles[100] == 2)
        M.paint(room, 100, "spawn", 1)
        assert(room.spawn == 100 and room.tiles[100] == 1)
        local before = M.encode(room)
        M.paint(room, 0, "material", 2)
        M.paint(room, 641, "material", 2)
        assert(before == M.encode(room))
        local x, y = M.position(640)
        assert(x == 252 and y == 156)
    ''')


def test_goal_zone_and_task_validation(lua):
    lua.execute('''
        local M = EditorModel
        local room = M.new()
        assert(M.problem(room) == nil)
        local function cell(x, y) return y * M.width + x + 1 end
        M.set_goal(room, cell(10, 5), cell(7, 3)) -- dragged up-left
        assert(room.goal.x0 == 7 and room.goal.y0 == 3 and room.goal.x1 == 10 and room.goal.y1 == 5)
        local r = M.goal_rect(room)
        assert(r[1] == 56 and r[2] == 24 and r[3] == 88 and r[4] == 48)
        assert(M.in_goal(room, cell(8, 4)) and not M.in_goal(room, cell(11, 4)))
        M.set_goal(room, room.spawn, room.spawn)
        assert(string.find(M.problem(room), "inside the goal"))
        room.goal = nil
        assert(string.find(M.problem(room), "needs a goal zone"))
        room.objective = 2
        assert(string.find(M.problem(room), "at least one enemy"))
        M.paint(room, cell(20, 10), "entity", 2)
        assert(M.problem(room) == nil)
        room.objective = 3
        assert(string.find(M.problem(room), "gold"))
        room.objective = 4
        assert(M.problem(room) == nil)
        M.paint(room, room.spawn - M.width, "material", 2)
        assert(string.find(M.problem(room), "Player spawn"))
    ''')


def export_room(lua, setup: str) -> dict:
    return json.loads(lua.eval(f'''(function()
        local M = EditorModel
        local room = M.new()
        local function cell(x, y) return y * M.width + x + 1 end
        {setup}
        assert(M.problem(room) == nil, M.problem(room))
        return M.json(M.to_scenario(room))
    end)()'''))


def test_exported_room_is_a_valid_scenario_that_compiles(lua, tmp_path):
    from noita_rl.compiler.compile import compile_scenario
    from noita_rl.compiler.materials import material_to_rgb
    from noita_rl.schema import validate_document

    scenario = export_room(lua, '''
        room.name = "lava_jump"
        M.paint(room, cell(15, 17), "material", 6) -- lava pit
        M.paint(room, cell(16, 17), "material", 6)
        M.paint(room, cell(15, 5), "material", 3)
        M.paint(room, cell(20, 16), "entity", 3)
    ''')
    assert validate_document("scenario", scenario) == []
    assert scenario["id"] == "lava_jump"
    assert scenario["termination"]["success_conditions"] == [
        {"type": "reach_region", "rect": [216, 112, 248, 144]}]
    assert scenario["room"]["spawns"]["player"] == {"x": 28, "y": 132}
    assert scenario["room"]["spawns"]["entities"][0]["x"] == 164
    path = tmp_path / "lava_jump.json"
    path.write_text(json.dumps(scenario))
    with Image.open(compile_scenario(path, tmp_path / "build") / "materials.png") as image:
        assert image.size == (256, 160)
        assert image.getpixel((0, 0)) == material_to_rgb("steel_static")
        assert image.getpixel((28, 132)) == material_to_rgb("air")
        assert image.getpixel((15 * 8 + 3, 17 * 8 + 3)) == material_to_rgb("lava")
        assert image.getpixel((15 * 8 + 3, 5 * 8 + 3)) == material_to_rgb("wood_static")
        assert image.getpixel((17 * 8 + 3, 17 * 8 + 3)) == material_to_rgb("air")
        assert image.getpixel((100, 19 * 8 + 3)) == material_to_rgb("steel_static")


@pytest.mark.parametrize(("objective", "expected"), [
    (2, {"type": "kill_tag", "tag": "enemy", "count": 2}),
    (3, {"type": "collect_gold", "gold": 50}),
    (4, {"type": "survive_steps", "steps": 1799}),
])
def test_exported_objectives(lua, objective, expected):
    from noita_rl.schema import validate_document

    scenario = export_room(lua, f'''
        room.objective = {objective}
        M.paint(room, cell(20, 16), "entity", 1)
        M.paint(room, cell(22, 16), "entity", 2)
        M.paint(room, cell(24, 16), "entity", 3)
    ''')
    assert validate_document("scenario", scenario) == []
    assert scenario["termination"] == {"max_steps": 1800, "success_conditions": [expected]}


def test_all_lua_files_parse_as_lua51(lua):
    parse = lua.eval("function(source, name) local f, err = loadstring(source, name); assert(f, err) end")
    for path in (ROOT / "mod").rglob("*.lua"):
        if "build" not in path.parts:
            parse(path.read_text(), str(path))


def test_world_is_empty_and_tiles_use_native_wang_colors():
    biome = ET.parse(EDITOR / "empty.xml").getroot()
    topology = biome.find("Topology")
    # Mirrors vanilla boss_arena_top.xml: no wang template and no materials = only air.
    assert topology.get("wang_template_file") == "" and topology.get("type") is None
    assert topology.get("lua_script") == "mods/noita_rl/files/editor/empty.lua"
    assert biome.find("Materials") is not None and len(biome.find("Materials")) == 0
    assert not biome.findall(".//VegetationComponent")
    assert ET.parse(EDITOR / "magic_numbers.xml").getroot().get("BIOME_MAP").endswith("editor/biome_map.lua")
    for name, rgba in {"air": (0, 0, 66, 255), "water": (47, 85, 76, 144),
                       "steel_static": (64, 64, 65, 255)}.items():
        with Image.open(EDITOR / "terrain" / f"{name}.png") as image:
            assert image.size == (8, 8)
            assert image.getextrema() == tuple((v, v) for v in rgba)
    with Image.open(EDITOR / "terrain/clear.png") as image:
        assert image.size == (320, 224)
        assert image.getextrema() == ((0, 0), (0, 0), (66, 66), (255, 255))


VANILLA_BIOMES = '''<BiomesToLoad
	biome_image_map="data/biome_impl/biome_map.png"
	biome_offset_y="14" >
	<Biome biome_filename="data/biome/mountain_top.xml" height_index="0" color="ff36d517" >
	</Biome>
</BiomesToLoad>
'''


def test_world_override_keeps_vanilla_biomes_and_adds_the_empty_one(lua):
    """Regression: replacing the whole biome list crashed Noita at startup, because
    data/scripts/biome_modifiers.lua edits vanilla biomes such as mountain_top.xml."""
    import re

    files = lua.eval("{}")
    files["data/biome/_biomes_all.xml"] = VANILLA_BIOMES
    lua.globals().files = files
    lua.execute('''
        function ModMagicNumbersFileAdd(path) magic = path end
        function ModTextFileGetContent(path) return files[path] end
        function ModTextFileSetContent(path, text) files[path] = text end
        function ModSettingGet() return nil end
        function ModSettingSet() end
        function dofile_once() end
        function print() end
    ''')
    lua.execute((ROOT / "mod/init.lua").read_text())
    root = ET.fromstring(files["data/biome/_biomes_all.xml"])
    assert root.get("biome_image_map") == "data/biome_impl/biome_map.png"
    names = [b.get("biome_filename") for b in root.findall("Biome")]
    assert names == ["data/biome/mountain_top.xml", "mods/noita_rl/files/editor/empty.xml"]
    color = root.findall("Biome")[-1].get("color")
    painted = re.search(r"BiomeMapSetPixel\(x, y, 0x(\w+)\)", (EDITOR / "biome_map.lua").read_text())
    assert painted and painted.group(1) == color
    for name in ("_pixel_scenes.xml", "_pixel_scenes_newgame_plus.xml"):
        scenes = ET.fromstring(files[f"data/biome/{name}"])
        assert [child.tag for child in scenes] == ["PixelSceneFiles", "BackgroundImages", "mBufferedPixelScenes"]
        assert not list(scenes.iter("PixelScene")) and not list(scenes.iter("File"))
    assert lua.eval("magic") == "mods/noita_rl/files/editor/magic_numbers.xml"


def test_editor_play_reset_save_load_and_death(game):
    game.execute('''
        boot()
        assert(not enabled)
        local original = settings["noita_rl.editor_draft"]
        buttons[6] = true; noita_editor_update() -- save slot
        assert(settings["noita_rl.editor_slot_1"] == original)
        buttons[1] = true; noita_editor_update() -- play
        assert(not enabled) -- UI click must not fire a wand
        frame = 4; noita_editor_pre_update(); assert(enabled)
        for _, call in ipairs(stamps) do assert(call[10] == true) end -- repeatable stamps
        hp = 0; noita_editor_update() -- fatal damage returns to editor
        assert(not enabled and hp == 4)
        assert(settings["noita_rl.editor_draft"] == original)
        buttons[7] = true; noita_editor_update() -- load
        buttons[2] = true; noita_editor_update() -- undo
        buttons[3] = true; noita_editor_update() -- redo
        assert(settings["noita_rl.editor_draft"] == original)
        buttons[1] = true; noita_editor_update()
        buttons[10] = true; noita_editor_update() -- manual reset
        assert(not enabled and settings["noita_rl.editor_draft"] == original)
    ''')


def test_play_test_is_scored_like_an_episode(game):
    game.execute('boot(); buttons[1] = true; noita_editor_update()')
    game.execute('frame = 30; px, py = 230, 130; noita_editor_update()')  # walk into goal
    assert editor_message(game).startswith("SUCCESS: reached goal in 0.5 s")
    game.execute('frame = 100; buttons[1] = true; noita_editor_update()')
    game.execute('frame = 100 + 30 * 60; px, py = 28, 132; noita_editor_update()')
    assert editor_message(game).startswith("FAILED: timed out after 30.0 s")
    # Kill-all: success only once every spawned enemy is dead.
    game.execute('''
        buttons[50] = true; noita_editor_update() -- objective -> kill all
        assert(string.find(settings["noita_rl.editor_draft"], ":2:3:my_room$"))
        buttons[1] = true; noita_editor_update()
        assert(next_entity == 200) -- refused: no enemies
    ''')
    assert "at least one enemy" in editor_message(game)


def test_reads_real_mod_settings_file_written_by_noita(lua):
    """tests/data/mod_settings_editor_draft.bin was written by Noita (Jan 25 2025) after the
    editor ran once; it is FastLZ-compressed and holds the autosaved draft."""
    from noita_rl.modsettings import read_mod_settings

    settings = read_mod_settings(ROOT / "tests/data/mod_settings_editor_draft.bin")
    assert settings["noita_rl.mode"] == "editor"
    assert settings["noita_rl._version"] == 1.0
    draft = settings["noita_rl.editor_draft"]
    assert len(draft) == 1314
    lua.globals().draft = draft
    assert lua.eval("EditorModel.encode(EditorModel.decode(draft)) == draft")
    assert lua.eval("EditorModel.encode(EditorModel.new()) == draft")


def test_debug_status_reports_last_stage(tmp_path, capsys):
    from noita_rl.cli import main

    fixture = str(ROOT / "tests/data/mod_settings_editor_draft.bin")
    assert main(["debug-status", "--settings", fixture]) == 0
    out = capsys.readouterr().out
    assert "noita_rl.mode = editor" in out and "<1314 chars>" in out
    assert "No editor breadcrumbs" in out
    assert main(["debug-status", "--settings", str(tmp_path / "missing.bin")]) == 1


def test_editor_records_breadcrumbs_through_first_frames(game):
    game.execute("noita_editor_spawn(1); noita_editor_update()")  # no drawing during setup
    assert game.eval('settings["noita_rl.debug_stage"]') == "spawn"
    game.execute("boot(); noita_editor_pre_update(); noita_editor_update(); noita_editor_update()")
    assert game.eval('settings["noita_rl.debug_stage"]') == "second_frame_done"
    steps = ["damage", "room", "controls", "position", "camera", "library", "editor"]
    assert game.eval('settings["noita_rl.debug_trace"]') == " > ".join(
        ["init", "spawn"] + [f"setup_{s}_{when}" for s in steps for when in ("begin", "done")]
        + ["pre_update", "update", "draw_start", "draw_toolbar_done", "draw_grid_done",
           "draw_done", "first_frame_done", "second_frame_done"])


def write_mod_settings(path: Path, settings: dict) -> None:
    """Write a mod_settings.bin in Noita's layout (uncompressed variant: equal sizes)."""
    import struct

    def value(v) -> tuple[int, bytes]:
        if v is None:
            return 0, b""
        if isinstance(v, bool):
            return 1, bytes([v])
        if isinstance(v, (int, float)):
            return 2, struct.pack(">d", v)
        data = v.encode("utf-8")
        return 3, struct.pack(">I", len(data)) + data

    body = struct.pack(">Q", len(settings))
    for name, current in settings.items():
        kind, data = value(current)
        body += struct.pack(">I", len(name)) + name.encode() + struct.pack(">II", kind, 0) + data
    path.write_bytes(struct.pack("<II", len(body), len(body)) + body)


def test_export_stores_scenario_in_mod_settings_and_pull_rooms_copies_it(game, tmp_path, capsys):
    from noita_rl.cli import main
    from noita_rl.schema import validate_document

    game.execute('''
        boot()
        buttons[53] = true; noita_editor_update() -- id: my_room -> lesson_01
        buttons[8] = true; noita_editor_update() -- export
        buttons[53] = true; noita_editor_update() -- lesson_02
        buttons[51] = true; noita_editor_update() -- time limit 30 s -> 60 s
        buttons[8] = true; noita_editor_update()
    ''')
    assert "pull-rooms" in editor_message(game)
    stored = {name: game.eval(f'settings["{name}"]') for name in
              ("noita_rl.export_lesson_01", "noita_rl.export_lesson_02")}
    assert all("\n" not in text for text in stored.values())
    assert validate_document("scenario", json.loads(stored["noita_rl.export_lesson_01"])) == []

    bin_path, dest = tmp_path / "mod_settings.bin", tmp_path / "scenarios"
    write_mod_settings(bin_path, {"noita_rl._version": 1.0, "noita_rl.mode": "editor",
                                  **stored, "noita_rl.export_broken": "{not json"})
    args = ["pull-rooms", "--settings", str(bin_path), "--dest", str(dest)]
    assert main(args) == 1  # the broken export is reported; the valid rooms are still copied
    out = capsys.readouterr().out
    assert "SKIP broken" in out and "OK   lesson_01" in out
    assert sorted(p.name for p in dest.iterdir()) == ["lesson_01.json", "lesson_02.json"]
    assert json.loads((dest / "lesson_02.json").read_text())["termination"]["max_steps"] == 3600

    # Re-exporting a changed room needs --overwrite; an unchanged one is fine.
    changed = json.loads(stored["noita_rl.export_lesson_01"])
    changed["termination"]["max_steps"] = 600
    write_mod_settings(bin_path, {"noita_rl.export_lesson_01": json.dumps(changed),
                                  "noita_rl.export_lesson_02": stored["noita_rl.export_lesson_02"]})
    assert main(args) == 1 and "use --overwrite" in capsys.readouterr().out
    assert main([*args, "--overwrite"]) == 0
    assert json.loads((dest / "lesson_01.json").read_text())["termination"]["max_steps"] == 600


def test_pull_rooms_explains_when_nothing_was_exported(tmp_path, capsys):
    from noita_rl.cli import main

    fixture = str(ROOT / "tests/data/mod_settings_editor_draft.bin")  # real file, no exports
    assert main(["pull-rooms", "--settings", fixture, "--dest", str(tmp_path)]) == 1
    assert "Export for RL" in capsys.readouterr().out
    assert main(["pull-rooms", "--settings", str(tmp_path / "missing.bin")]) == 1


def test_fastlz_level_2_streams_decode():
    """Hand-built level-2 stream: literals, a long match, and a far match (>8 KiB back)."""
    from noita_rl.modsettings import fastlz_decompress

    # 0x20 marks level 2; then a 4-byte literal run "abcd".
    stream = bytes([0x20 | 3]) + b"abcd"
    # Match: length code 7 (len 6 -> extended), extra bytes 255 then 10 => 6+255+10+3 = 274.
    stream += bytes([0xE0, 255, 10, 3])  # distance 3+1 = 4 back: repeats "abcd"
    expected = b"abcd" + (b"abcd" * 69)[:274]
    filler = bytes(range(32)) * 300  # 9600 literal bytes, in runs of 32
    for i in range(0, len(filler), 32):
        stream += bytes([31]) + filler[i:i + 32]
    expected += filler
    # Far match: ofs bits 31<<8, code 255, then 16-bit extra distance; copies 3 bytes.
    distance = len(expected) - 0  # back to the very first byte
    extra = distance - 8191 - 1
    stream += bytes([0x20 | 31, 255, extra >> 8, extra & 255])
    expected += expected[0:3]
    assert fastlz_decompress(stream, len(expected)) == expected


def test_course_lays_out_rooms_and_teleports_through_them(game):
    """Two exported rooms: clear room 1, get teleported to room 2 at x=512, fail it once
    (restart), then clear it to complete the course."""
    game.execute('''
        boot()
        buttons[53] = true; noita_editor_update() -- id lesson_01
        buttons[8] = true; noita_editor_update()  -- export
        buttons[53] = true; noita_editor_update() -- id lesson_02
        buttons[8] = true; noita_editor_update()
        assert(settings["noita_rl.room_lesson_02"])
        buttons[62] = true; noita_editor_update() -- add lesson_01 (library pick 1)
        buttons[61] = true; noita_editor_update() -- pick lesson_02
        buttons[62] = true; noita_editor_update() -- add lesson_02
        assert(settings["noita_rl.course"] == "lesson_01,lesson_02")
        stamps = {}
        frame = 100; buttons[64] = true; noita_editor_update() -- play course
    ''')
    stamped_x = {call[3] for call in game.eval("stamps").values()}
    assert -32 in stamped_x and 512 - 32 in stamped_x  # both rooms laid out in the world
    assert game.eval("px") == 28  # player in room 1
    game.execute("frame = 130; px, py = 230, 130; noita_editor_update()")  # reach goal 1
    assert game.eval("px") == 512 + 28  # teleported to room 2
    game.execute("frame = 140; hp = 0; noita_editor_update()")  # die in room 2 -> restart
    assert game.eval("px") == 512 + 28 and game.eval("hp") == 4
    game.execute("frame = 150; px, py = 512 + 230, 130; noita_editor_update()")
    assert editor_message(game).startswith("COURSE COMPLETE: 2 rooms")
    assert game.eval("px") == 28  # back in the editor


def test_course_survives_reload_and_rejects_missing_rooms(game):
    game.execute('''
        settings["noita_rl.course"] = "lesson_07,9bad,lesson_08"
        boot()
    ''')
    assert game.eval("EditorModel.course_text(EditorModel.parse_course(settings['noita_rl.course']))") == (
        "lesson_07,lesson_08")
    game.execute("buttons[64] = true; noita_editor_update()")
    assert "lesson_07 is missing" in editor_message(game)


def test_old_exports_recover_their_blueprint_from_a_matching_slot(game):
    """Rooms exported before courses existed (like the real lesson_01) become course-ready
    if the draft or a slot reproduces the export exactly; a mismatching slot is ignored."""
    game.execute('''
        local M = EditorModel
        local room = M.new(); room.name = "lesson_01"
        settings["noita_rl.export_lesson_01"] = string.gsub(M.json(M.to_scenario(room)), "\\n%s*", "")
        settings["noita_rl.editor_slot_1"] = M.encode(room)
        local other = M.new(); other.name = "lesson_03"
        settings["noita_rl.export_lesson_03"] = "{}" -- export does not match slot 2
        settings["noita_rl.editor_slot_2"] = M.encode(other)
        boot()
    ''')
    assert game.eval('settings["noita_rl.room_lesson_01"]') == game.eval('settings["noita_rl.editor_slot_1"]')
    assert game.eval('settings["noita_rl.room_lesson_03"]') is None
    game.execute("buttons[62] = true; noita_editor_update()")  # add the recovered room
    assert game.eval('settings["noita_rl.course"]') == "lesson_01"


def export_two_lessons(game):
    game.execute('''
        boot()
        buttons[53] = true; noita_editor_update() -- id lesson_01
        buttons[8] = true; noita_editor_update()  -- export
        buttons[53] = true; noita_editor_update() -- id lesson_02
        buttons[8] = true; noita_editor_update()
    ''')


def test_course_slots_save_load_and_clear(game):
    export_two_lessons(game)
    game.execute('''
        buttons[62] = true; noita_editor_update() -- add lesson_01
        buttons[61] = true; noita_editor_update()
        buttons[62] = true; noita_editor_update() -- add lesson_02
        buttons[66] = true; noita_editor_update() -- course slot 2
        buttons[67] = true; noita_editor_update() -- save course
    ''')
    assert game.eval('settings["noita_rl.course_slot_2"]') == "lesson_01,lesson_02"
    assert "course slot 2" in editor_message(game)
    game.execute("buttons[65] = true; noita_editor_update()")  # clear
    assert game.eval('settings["noita_rl.course"]') == ""
    game.execute("buttons[67] = true; noita_editor_update()")  # saving an empty course is refused
    assert game.eval('settings["noita_rl.course_slot_2"]') == "lesson_01,lesson_02"
    game.execute("buttons[68] = true; noita_editor_update()")  # load slot 2
    assert game.eval('settings["noita_rl.course"]') == "lesson_01,lesson_02"
    game.execute("buttons[66] = true; buttons[68] = true; noita_editor_update()")  # slot 3 is empty
    assert "slot 3 is empty" in editor_message(game)


def test_human_mode_plays_the_chosen_course_and_loops(game):
    export_two_lessons(game)
    game.execute('''
        settings["noita_rl.course_slot_4"] = "lesson_02,lesson_01"
        settings["noita_rl.play_course"] = "4"
        settings["noita_rl.mode"] = "human"
    ''')
    # A new game: reload the editor with the human-mode settings in place.
    game.execute((EDITOR / "editor.lua").read_text())
    game.execute("frame = 100; boot(); noita_editor_update()")
    assert game.eval("px") == 28  # room 1 of the course (lesson_02) at origin 0
    game.execute("frame = 110; px, py = 230, 130; noita_editor_update()")
    assert game.eval("px") == 512 + 28  # room 2
    game.execute("frame = 120; px, py = 512 + 230, 130; noita_editor_update()")
    assert game.eval("px") == 28  # course complete: starts again instead of opening the editor
    game.execute("buttons[10] = true; noita_editor_update()")  # Restart course
    assert game.eval("px") == 28


def test_human_mode_explains_an_empty_course(game):
    game.execute('settings["noita_rl.mode"] = "human"; settings["noita_rl.play_course"] = "7"; boot()')
    message = editor_message(game)
    assert "Can't start course 7" in message and "empty" in message


def test_mod_settings_course_picker_skips_empty_slots(lua):
    lua.execute('''
        settings, next_values, clicks = {}, {}, {}
        function dofile() end
        function ModSettingGet(key) return settings[key] end
        function ModSettingSet(key, value) settings[key] = value end
        function ModSettingGetNextValue(key) return next_values[key] end
        function ModSettingSetNextValue(key, value, is_default)
            if not (is_default and next_values[key] ~= nil) then next_values[key] = value end
        end
        function mod_setting_get_id(mod_id, setting) return mod_id .. "." .. setting.id end
        function mod_setting_tooltip() end
        mod_setting_group_x_offset = 0
        labels = {}
        function GuiButton(_, id, _, _, text)
            table.insert(labels, text); local c = clicks[1]; clicks = {}; return c == "left", c == "right"
        end
    ''')
    lua.execute((ROOT / "mod/settings.lua").read_text())
    lua.execute('''
        settings["noita_rl.course_slot_3"] = "lesson_01,lesson_02"
        settings["noita_rl.course_slot_6"] = "lesson_09"
        settings["noita_rl.room_lesson_01"] = "x"; settings["noita_rl.room_lesson_02"] = "x"
        local course = mod_settings[2]
        next_values["noita_rl.play_course"] = "1"
        clicks = {"left"}; course.ui_fn("noita_rl", 1, true, 1, course)
    ''')
    assert lua.eval('next_values["noita_rl.play_course"]') == "3"
    lua.execute('clicks = {"left"}; mod_settings[2].ui_fn("noita_rl", 1, true, 1, mod_settings[2])')
    assert lua.eval('next_values["noita_rl.play_course"]') == "6"
    lua.execute('mod_settings[2].ui_fn("noita_rl", 1, true, 1, mod_settings[2])')
    label = lua.eval("labels[#labels]")
    assert label.startswith("Course to play: 6  (1 rooms: lesson_09") and "1 missing" in label
    lua.execute('clicks = {"right"}; mod_settings[2].ui_fn("noita_rl", 1, true, 1, mod_settings[2])')
    assert lua.eval('next_values["noita_rl.play_course"]') == "3"
    modes = [lua.eval(f"mod_settings[1].values[{i}][1]") for i in (1, 2, 3)]
    assert modes == ["editor", "human", "agent"]


def test_install_refuses_while_noita_runs_and_stale_files_are_listed(tmp_path, monkeypatch):
    from noita_rl import cli

    source, dest = tmp_path / "src", tmp_path / "dest"
    (source / "files").mkdir(parents=True)
    (source / "init.lua").write_text("new")
    (source / "files" / "agent.lua").write_text("x")
    dest.mkdir()
    (dest / "init.lua").write_text("old")
    assert cli.stale_mod_files(source, dest) == ["files/agent.lua", "init.lua"]
    monkeypatch.setattr(cli, "noita_is_running", lambda: True)
    args = argparse.Namespace(source=str(source), dest=str(dest), force=False)
    assert cli.cmd_install_mod(args) == 1 and (dest / "init.lua").read_text() == "old"
    monkeypatch.setattr(cli, "noita_is_running", lambda: False)
    assert cli.cmd_install_mod(args) == 0 and cli.stale_mod_files(source, dest) == []
