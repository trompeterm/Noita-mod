"""RL agent mode: the Lua packet writer and the Python strip decoder must agree exactly."""
import math

import numpy as np
import pytest

from noita_rl.telemetry.agent_packet import (
    PACKET_BYTES,
    SENSOR_VECTOR_SIZE,
    Objective,
    Reason,
    decode_agent_strip,
    parse_packet,
    sensor_vector,
)
from test_editor import EDITOR, ROOT, export_two_lessons, game, lua  # noqa: F401 (fixtures)

AGENT = ROOT / "mod/files/agent/agent.lua"

# LuaJIT's bit library, which Noita has and plain Lua 5.1 lacks.
BIT = '''
bit = {}
function bit.bxor(a, b)
    a, b = a % 4294967296, b % 4294967296
    local r, p = 0, 1
    for _ = 1, 32 do
        local x, y = a % 2, b % 2
        if x ~= y then r = r + p end
        a, b, p = (a - x) / 2, (b - y) / 2, p * 2
    end
    if r >= 2147483648 then r = r - 4294967296 end -- LuaJIT returns signed results
    return r
end
'''

SAMPLE = '''
s = {frame = 123456, episode = 7, cmd_seq = 300, room_index = 2, room_count = 3, attempt = 4,
     objective = 2, terminal = true, reason = 2, steps = 600, max_steps = 1800,
     reward = -0.201, episode_return = -3.5, x = 28.25, y = 128, vx = -40.5, vy = 120,
     hp = 2.5, max_hp = 4, gold = 150, on_ground = true, has_goal = true, in_goal = false,
     overlay = true, buttons = 2 + 32 + 1024, aim_x = 0.7071, aim_y = -0.7071, mana = 80, mana_max = 120, goal_dx = 200.5, goal_dy = -14, goal_dist = 200.99,
     enemies_alive = 2, gold_left = 1,
     enemies = {{dx = 30, dy = -2.5, hp = 1.5}, {dx = -100, dy = 0, hp = 0.25}},
     golds = {{dx = 5, dy = 6}}, rays = {}, liquid_rays = {}}
for i = 1, 16 do s.rays[i] = i * 10; s.liquid_rays[i] = i * 5 end
'''


@pytest.fixture
def agent(lua):  # noqa: F811
    lua.execute(BIT)
    lua.execute(AGENT.read_text())
    return lua


def packed(agent_lua) -> bytes:
    return bytes(agent_lua.eval("NoitaAgent.pack(s)").values())


def test_lua_packet_round_trips_through_python(agent):
    agent.execute(SAMPLE)
    data = packed(agent)
    assert len(data) % 3 == 0 and len(data) >= PACKET_BYTES
    p = parse_packet(data)
    assert (p.frame, p.episode, p.cmd_seq, p.room_index, p.room_count, p.attempt) == (123456, 7, 44, 2, 3, 4)
    assert p.objective == Objective.KILL_ALL and p.terminal and p.reason == Reason.DIED
    assert (p.steps, p.max_steps, p.reward, p.episode_return) == (600, 1800, -0.201, -3.5)
    assert (p.x, p.y, p.vx, p.vy, p.hp, p.max_hp, p.gold) == (28.3, 128, -40.5, 120, 2.5, 4, 150)
    assert p.on_ground and p.has_goal and not p.in_goal and p.overlay
    assert p.buttons == {"right", "fire", "aim_up"} and (p.aim_x, p.aim_y) == (0.707, -0.707)
    assert (p.mana, p.mana_max, p.goal_dx, p.goal_dy, p.goal_dist) == (80, 120, 200.5, -14, 201.0)
    assert [(e.dx, e.dy, e.hp) for e in p.enemies] == [(30, -2.5, 1.5), (-100, 0, 0.25)]
    assert [(g.dx, g.dy) for g in p.golds] == [(5, 6)]
    assert p.rays == [i * 10 for i in range(1, 17)] and p.liquid_rays == [i * 5 for i in range(1, 17)]
    assert sensor_vector(p).shape == (SENSOR_VECTOR_SIZE,)
    corrupt = bytearray(data)
    corrupt[20] ^= 1
    with pytest.raises(ValueError, match="checksum"):
        parse_packet(bytes(corrupt))


def render(data: bytes, pitch: float, left: int, top: int, size=(400, 700)) -> np.ndarray:
    """Draw the strip like Noita would: cells of `pitch` pixels, plus a window border."""
    image = np.full((*size, 3), 37, dtype=np.uint8)
    for cell in range(len(data) // 3):
        col, row = cell % 96, cell // 96
        x0, y0 = left + col * pitch, top + row * pitch
        image[math.floor(y0):math.floor(y0 + pitch), math.floor(x0):math.floor(x0 + pitch)] = list(
            data[cell * 3 : cell * 3 + 3])
    return image


@pytest.mark.parametrize("pitch,left,top", [(4, 10, 33), (3, 8, 31), (6, 0, 0), (4.5, 9, 40)])
def test_strip_is_found_and_decoded_at_any_scale(agent, pitch, left, top):
    agent.execute(SAMPLE)
    image = render(packed(agent), pitch, left, top)
    packet, hint = decode_agent_strip(image)
    assert packet.frame == 123456 and packet.rays[15] == 160
    again, _ = decode_agent_strip(image, hint)  # the hint skips the search
    assert again.frame == 123456


def test_missing_strip_is_reported(agent):
    with pytest.raises(ValueError, match="not found"):
        decode_agent_strip(np.zeros((300, 300, 3), dtype=np.uint8))


def test_ray_directions_cover_a_full_turn(agent):
    dirs = [agent.eval(f"{{NoitaAgent.ray_direction({i})}}") for i in range(1, 17)]
    assert dirs[0][1] == pytest.approx(1) and dirs[4][2] == pytest.approx(1)  # right, then down


AGENT_MOCKS = '''
keys_down, held_keys, strip, overlay_drawn, control = {}, {}, {}, false, {}
local color = {1, 1, 1}
function InputIsKeyJustDown(key) return keys_down[key] == true end
function InputIsKeyDown(key) return held_keys[key] == true end
local set_value = ComponentSetValue2
function ComponentSetValue2(component, key, a, b)
    if component == "ControlsComponent" and key ~= "enabled" then control[key] = b ~= nil and {a, b} or a end
    return set_value(component, key, a, b)
end
function RaytraceSurfaces(x, y, ex, ey) return true, x + (ex - x) * 0.25, y + (ey - y) * 0.25 end
function RaytraceSurfacesAndLiquiform(x, y, ex, ey) return true, x + (ex - x) * 0.125, y + (ey - y) * 0.125 end
function GuiStartFrame() strip = {}; overlay_drawn = false end
function GuiZSetForNextWidget() end
function GuiColorSetForNextWidget(_, r, g, b) color = {r, g, b} end
function GuiImage(_, id)
    if id >= 3000 and id < 5000 then strip[id - 3000] = color end
end
local text = GuiText
function GuiText(gui, x, y, line)
    if type(line) == "string" and string.find(line, "RL AGENT", 1, true) then overlay_drawn = true end
end
function GuiGetScreenDimensions() return 640, 360 end
function GameGetCameraPos() return 128, 80 end
function MagicNumbersGetValue() return nil end
'''


def strip_packet(lua_runtime):
    cells = lua_runtime.eval("strip")
    data = []
    for cell in range(len(cells) + 1):  # Lua table keyed from 0; len() counts 1..n
        data += [round(c * 255) for c in cells[cell].values()]
    return parse_packet(bytes(data))


def test_agent_mode_plays_the_course_and_obeys_numpad_commands(game):  # noqa: F811
    game.execute(BIT)
    game.execute(AGENT.read_text())
    game.execute(AGENT_MOCKS)
    export_two_lessons(game)
    game.execute('''
        settings["noita_rl.course_slot_1"] = "lesson_01,lesson_02"
        settings["noita_rl.mode"] = "agent"
    ''')
    game.execute((EDITOR / "editor.lua").read_text())  # a new game in agent mode
    game.execute("frame = 100; boot(); frame = 101; noita_editor_update()")
    p = strip_packet(game)
    assert (p.room_index, p.room_count, p.episode, p.terminal) == (1, 2, 1, False)
    assert p.objective == Objective.REACH_GOAL and p.has_goal and p.goal_dx > 150
    assert p.rays[0] == 40 and p.liquid_rays[0] == 20  # mocked hits at 1/4 and 1/8 of range
    assert p.reward == pytest.approx(-0.001) and game.eval("overlay_drawn")
    # Python holds D (right) and J (fire): the mod presses them for the player and aims right.
    game.execute("held_keys = {[7] = true, [13] = true}; frame = 102; noita_editor_pre_update()")
    assert game.eval("enabled") is False  # the real keyboard never moves the agent's player
    assert game.eval("control.mButtonDownRight") is True and game.eval("control.mButtonDownFire") is True
    assert game.eval("control.mButtonDownLeft") is False and game.eval("control.mButtonFrameFire") == 102
    assert tuple(game.eval("control.mAimingVectorNormalized").values()) == (1, 0)
    game.execute("frame = 103; noita_editor_update()")
    p = strip_packet(game)
    assert p.buttons == {"right", "fire"} and (p.aim_x, p.aim_y) == (1, 0)
    # Arrow keys aim: up + left gives a diagonal; letting go of fire keeps the press frame.
    game.execute("held_keys = {[82] = true, [80] = true}; frame = 104; noita_editor_pre_update()")
    ax, ay = game.eval("control.mAimingVectorNormalized").values()
    assert ax == pytest.approx(-0.7071, abs=1e-3) and ay == pytest.approx(-0.7071, abs=1e-3)
    assert game.eval("control.mButtonDownFire") is False
    # W alone jumps and levitates (like vanilla), and the levitation target follows the player.
    game.execute("held_keys = {[26] = true}; py = 100; frame = 105; noita_editor_pre_update()")
    assert game.eval("control.mButtonDownJump") is True and game.eval("control.mButtonDownFly") is True
    assert game.eval("control.mFlyingTargetY") == 100 - 20
    game.execute("py = 60; frame = 106; noita_editor_pre_update()")
    assert game.eval("control.mFlyingTargetY") == 60 - 20  # still climbing: no height cap
    game.execute("held_keys = {}; frame = 107; noita_editor_pre_update()")
    assert game.eval("control.mButtonDownFly") is False and game.eval("control.mFlyingTargetY") == 60
    game.execute("held_keys = {[7] = true}; py = 130")

    game.execute("frame = 130; px, py = 230, 130; noita_editor_update()")  # reach the goal
    p = strip_packet(game)
    assert p.terminal and p.reason == Reason.SUCCESS and p.in_goal
    assert p.reward == pytest.approx(5 - 0.001)
    game.execute("noita_editor_pre_update()")
    assert game.eval("control.mButtonDownRight") is False  # buttons released while the result shows
    game.execute("frame = 145; noita_editor_update()")
    assert strip_packet(game).terminal  # still holding the result
    game.execute("frame = 160; noita_editor_update()")
    p = strip_packet(game)
    assert (p.room_index, p.episode, p.terminal) == (2, 2, False)
    assert game.eval("px") == 512 + 28

    # Python: "1" then Enter -> back to room 1, as a new episode.
    game.execute("keys_down = {[89] = true}; frame = 170; noita_editor_update()")
    game.execute("keys_down = {[88] = true}; frame = 171; noita_editor_update()")
    p = strip_packet(game)
    assert (p.room_index, p.episode, p.cmd_seq, p.attempt) == (1, 3, 1, 1)
    assert game.eval("px") == 28
    # "." restarts the current room; "*" hides the overlay but never the strip.
    game.execute("keys_down = {[99] = true, [85] = true}; frame = 172; noita_editor_update()")
    p = strip_packet(game)
    assert (p.episode, p.attempt, p.overlay) == (4, 2, False)
    assert not game.eval("overlay_drawn")
    game.execute("keys_down = {}; frame = 173; hp = 0; noita_editor_update()")  # dies
    p = strip_packet(game)
    assert p.terminal and p.reason == Reason.DIED and p.reward < -0.2


def test_window_input_posts_key_messages_to_noita_only():
    pytest.importorskip("win32con")
    import win32con

    from noita_rl.platform.windows.input import NoitaWindowInput, key_lparam

    sent = []
    keys = NoitaWindowInput(1234, post=lambda *message: sent.append(message))
    keys.hold({"right", "aim_up"})
    assert {(m[1], m[2]) for m in sent} == {(win32con.WM_KEYDOWN, 0x44), (win32con.WM_KEYDOWN, win32con.VK_UP)}
    assert all(m[0] == 1234 for m in sent)
    up = [m for m in sent if m[2] == win32con.VK_UP][0]
    assert up[3] >> 24 & 1 == 1  # arrows are extended keys, or SDL reads them as numpad keys
    sent.clear()
    keys.hold({"right"})  # held keys are re-sent, released ones get a key-up
    assert (1234, win32con.WM_KEYUP, win32con.VK_UP, key_lparam(win32con.VK_UP, True, True)) in sent
    assert (win32con.WM_KEYDOWN, 0x44) in {(m[1], m[2]) for m in sent}
    with pytest.raises(ValueError):
        keys.hold({"teleport"})


def test_configure_noita_backs_up_and_sets_background_options(tmp_path):
    from noita_rl.noita_config import configure

    config = tmp_path / "config.xml"
    original = '<Config application_pause_when_unfocused="1" backbuffer_width="1280" fullscreen="1" />'
    config.write_text(original, encoding="utf-8")
    before, backup = configure(config)
    assert before == {"application_pause_when_unfocused": "1", "fullscreen": "1"}
    text = config.read_text(encoding="utf-8")
    assert 'application_pause_when_unfocused="0"' in text and 'fullscreen="0"' in text
    assert 'backbuffer_width="1280"' in text and backup.read_text(encoding="utf-8") == original
    assert configure(config)[1] is None  # already set: no change, backup kept


def test_agent_command_keys():
    pytest.importorskip("win32con")
    from noita_rl.platform.windows.input import agent_command_keys

    assert agent_command_keys(12) == [(0x61, False), (0x62, False), (0x0D, True)]
    assert agent_command_keys(None) == [(0x0D, True)]
    with pytest.raises(ValueError):
        agent_command_keys(0)
