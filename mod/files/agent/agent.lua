-- RL agent mode: sensors, the telemetry strip the Python env reads from the screen,
-- a human-readable overlay, and the numpad command channel Python uses to reset rooms.
--
-- The mod is sandboxed (no files or sockets), so the only live channel to Python is the
-- screen. Every frame the packet below is drawn as a strip of solid-colour cells in the
-- top-left corner, 3 bytes per cell (R, G, B). Keep the layout in sync with
-- src/noita_rl/telemetry/agent_packet.py (test_agent.py checks both sides agree).
NoitaAgent = {}
local A = NoitaAgent
local bit = bit

A.VERSION = 3
A.CELL = 2          -- GUI units per cell (about 4 screen pixels at 1280x720)
A.COLS = 96         -- cells per strip row
A.ORIGIN_X, A.ORIGIN_Y = 1, 1
A.RAYS = 16
A.RAY_RANGE = 160   -- world pixels
A.ENEMY_SLOTS = 8
A.GOLD_SLOTS = 4
A.FLY_LEAD = 20     -- world pixels above the player that levitation aims for
A.HOLD_FRAMES = 30  -- a finished episode stays on screen this long before it continues
A.PIXEL = "mods/noita_rl/files/agent/pixel.png"

-- Terminal reasons (also in agent_packet.py).
A.REASON = {none = 0, success = 1, died = 2, left_room = 3, timeout = 4}

-- SDL key codes from data/scripts/debug/keycodes.lua.
local KEY_DIGITS = {[98] = 0, [89] = 1, [90] = 2, [91] = 3, [92] = 4, [93] = 5, [94] = 6, [95] = 7, [96] = 8, [97] = 9}
local KEY_ENTER, KEY_PERIOD, KEY_MULTIPLY = 88, 99, 85

-- Action keys. Python posts these straight to Noita's window (so they work while Noita is in
-- the background and never type into other apps); the mod reads them and drives the player
-- through its ControlsComponent. Bit order = the "buttons" field in the packet.
A.BUTTONS = {
    {name = "left", key = 4},   -- A
    {name = "right", key = 7},  -- D
    {name = "up", key = 26},    -- W (also jumps / levitates, like Space)
    {name = "down", key = 22},  -- S
    {name = "jump", key = 44},  -- Space (held: levitate)
    {name = "fire", key = 13},  -- J
    {name = "kick", key = 14},  -- K
    {name = "interact", key = 8}, -- E
    {name = "aim_left", key = 80}, {name = "aim_right", key = 79}, -- arrow keys aim;
    {name = "aim_up", key = 82}, {name = "aim_down", key = 81},    -- none = face forward
}

---------------------------------------------------------------------------
-- Packing

local function clamp(v, lo, hi)
    if v ~= v then return 0 end -- NaN
    if v < lo then return lo elseif v > hi then return hi end
    return v
end

local function round(v) return math.floor(v + 0.5) end

local Writer = {}
Writer.__index = Writer

local function writer() return setmetatable({bytes = {}}, Writer) end

function Writer:u8(v)
    table.insert(self.bytes, clamp(round(v), 0, 255))
end

function Writer:u16(v)
    v = clamp(round(v), 0, 65535)
    self:u8(v % 256); self:u8(math.floor(v / 256))
end

function Writer:i16(v)
    v = clamp(round(v), -32768, 32767)
    if v < 0 then v = v + 65536 end
    self:u16(v)
end

function Writer:u32(v)
    v = clamp(round(v), 0, 4294967295)
    for _ = 1, 4 do self:u8(v % 256); v = math.floor(v / 256) end
end

function Writer:i32(v)
    v = clamp(round(v), -2147483648, 2147483647)
    if v < 0 then v = v + 4294967296 end
    self:u32(v)
end

-- XOR of little-endian 4-byte words, zero padded (same as protocol.checksum in Python).
function A.checksum(bytes, count)
    local value = 0
    for i = 1, count, 4 do
        local word = (bytes[i] or 0) + (bytes[i + 1] or 0) * 256 + (bytes[i + 2] or 0) * 65536
            + (bytes[i + 3] or 0) * 16777216
        value = bit.bxor(value, word)
    end
    if value < 0 then value = value + 4294967296 end
    return value
end

-- s: the sensor table from A.sense (plus run state). Returns a list of bytes.
function A.pack(s)
    local w = writer()
    w:u8(78); w:u8(82); w:u8(A.VERSION) -- "NR", version: the first cell is the locator
    w:u16(0)                              -- payload length, patched below
    w:u32(s.frame); w:u32(s.episode); w:u8(s.cmd_seq % 256)
    w:u8(s.room_index); w:u8(s.room_count); w:u16(s.attempt); w:u8(s.objective)
    w:u8(s.terminal and 1 or 0); w:u8(s.reason)
    w:u32(s.steps); w:u32(s.max_steps)
    w:i32(s.reward * 1000); w:i32(s.episode_return * 1000)
    w:i16(s.x * 10); w:i16(s.y * 10); w:i16(s.vx * 10); w:i16(s.vy * 10)
    w:u16(s.hp * 100); w:u16(s.max_hp * 100); w:u32(s.gold)
    local flags = (s.on_ground and 1 or 0) + (s.has_goal and 2 or 0) + (s.in_goal and 4 or 0)
        + (s.overlay and 8 or 0)
    w:u8(flags)
    w:u16(s.buttons or 0); w:i16((s.aim_x or 0) * 1000); w:i16((s.aim_y or 0) * 1000)
    w:u16(s.mana); w:u16(s.mana_max)
    w:i16(s.goal_dx * 10); w:i16(s.goal_dy * 10); w:u16(s.goal_dist * 10)
    w:u8(s.enemies_alive); w:u8(s.gold_left)
    for i = 1, A.ENEMY_SLOTS do
        local e = s.enemies[i]
        w:i16(e and e.dx * 10 or 0); w:i16(e and e.dy * 10 or 0); w:u16(e and e.hp * 100 or 0)
    end
    for i = 1, A.GOLD_SLOTS do
        local g = s.golds[i]
        w:i16(g and g.dx * 10 or 0); w:i16(g and g.dy * 10 or 0)
    end
    w:u8(A.RAYS)
    for i = 1, A.RAYS do w:u16(s.rays[i] * 10) end
    for i = 1, A.RAYS do w:u16(s.liquid_rays[i] * 10) end
    local length = #w.bytes
    w.bytes[4], w.bytes[5] = length % 256, math.floor(length / 256)
    w:u32(A.checksum(w.bytes, length))
    while #w.bytes % 3 ~= 0 do w:u8(0) end
    return w.bytes
end

---------------------------------------------------------------------------
-- Sensors

local function first(entity, kind)
    return EntityGetFirstComponentIncludingDisabled(entity, kind)
end

local function entity_hp(entity)
    local damage = first(entity, "DamageModelComponent")
    if damage then return ComponentGetValue2(damage, "hp") or 0, ComponentGetValue2(damage, "max_hp") or 0 end
    return 0, 0
end

-- Ray i points at angle (i-1)/RAYS of a full turn, starting to the right (+x) and going
-- clockwise on screen (y grows downwards). Distance = RAY_RANGE when nothing is hit.
function A.ray_direction(i)
    local angle = (i - 1) * 2 * math.pi / A.RAYS
    return math.cos(angle), math.sin(angle)
end

local function cast(fn, x, y, dx, dy)
    local ex, ey = x + dx * A.RAY_RANGE, y + dy * A.RAY_RANGE
    local hit, hx, hy = fn(x, y, ex, ey)
    if not hit then return A.RAY_RANGE end
    return math.min(A.RAY_RANGE, math.sqrt((hx - x) ^ 2 + (hy - y) ^ 2))
end

local function active_wand_mana(player)
    local inventory = first(player, "Inventory2Component")
    local wand = inventory and ComponentGetValue2(inventory, "mActiveItem")
    if not wand or wand == 0 then return 0, 0 end
    local ability = first(wand, "AbilityComponent")
    if not ability then return 0, 0 end
    return ComponentGetValue2(ability, "mana") or 0, ComponentGetValue2(ability, "mana_max") or 0
end

local function nearest(list, count)
    table.sort(list, function(a, b) return a.dist < b.dist end)
    local out = {}
    for i = 1, math.min(count, #list) do out[i] = list[i] end
    return out
end

-- ctx: {player, room, ox, oy, spawned, model}. Positions are relative to the room origin,
-- offsets (dx, dy) are target minus player, in world pixels.
function A.sense(ctx)
    local M, player, room = ctx.model, ctx.player, ctx.room
    local wx, wy = EntityGetTransform(player)
    -- Sensors are measured from the body, not the feet (the transform is at the feet).
    local cx, cy = wx, wy - 4
    local s = {x = wx - ctx.ox, y = wy - ctx.oy, vx = 0, vy = 0, on_ground = false}
    local character = first(player, "CharacterDataComponent")
    if character then
        s.vx, s.vy = ComponentGetValue2(character, "mVelocity")
        s.vx, s.vy = s.vx or 0, s.vy or 0
        s.on_ground = ComponentGetValue2(character, "is_on_ground") and true or false
    end
    s.hp, s.max_hp = entity_hp(player)
    local wallet = first(player, "WalletComponent")
    s.gold = wallet and ComponentGetValue2(wallet, "money") or 0
    s.mana, s.mana_max = active_wand_mana(player)

    s.has_goal = room.goal ~= nil
    s.in_goal = s.has_goal and M.in_goal_world(room, ctx.ox, ctx.oy, wx, wy) or false
    s.goal_dx, s.goal_dy, s.goal_dist = 0, 0, 0
    if s.has_goal then
        local r = M.goal_rect(room)
        local gx = ctx.ox + (r[1] + r[3]) / 2
        local gy = ctx.oy + (r[2] + r[4]) / 2
        s.goal_dx, s.goal_dy = gx - wx, gy - wy
        s.goal_dist = math.sqrt(s.goal_dx ^ 2 + s.goal_dy ^ 2)
    end

    local enemies, golds = {}, {}
    for _, spawned in ipairs(ctx.spawned) do
        if EntityGetIsAlive(spawned.entity) then
            local ex, ey = EntityGetTransform(spawned.entity)
            local entry = {dx = ex - wx, dy = ey - wy}
            entry.dist = math.sqrt(entry.dx ^ 2 + entry.dy ^ 2)
            local info = M.entities[spawned.kind]
            if info.enemy then
                entry.hp = entity_hp(spawned.entity)
                table.insert(enemies, entry)
            elseif info.gold then
                table.insert(golds, entry)
            end
        end
    end
    s.enemies_alive, s.gold_left = #enemies, #golds
    s.enemies, s.golds = nearest(enemies, A.ENEMY_SLOTS), nearest(golds, A.GOLD_SLOTS)

    s.rays, s.liquid_rays = {}, {}
    for i = 1, A.RAYS do
        local dx, dy = A.ray_direction(i)
        s.rays[i] = cast(RaytraceSurfaces, cx, cy, dx, dy)
        s.liquid_rays[i] = cast(RaytraceSurfacesAndLiquiform, cx, cy, dx, dy)
    end
    return s
end

---------------------------------------------------------------------------
-- Player control from action keys

-- Which action keys are held: a table name -> true, and the packed bit mask.
function A.read_buttons()
    local held, mask = {}, 0
    for i, button in ipairs(A.BUTTONS) do
        if InputIsKeyDown(button.key) then
            held[button.name] = true
            mask = mask + 2 ^ (i - 1)
        end
    end
    return held, mask
end

-- Aim: arrow keys give 8 directions; without them, aim the way the player last moved.
function A.aim(held, state)
    local x = (held.aim_right and 1 or 0) - (held.aim_left and 1 or 0)
    local y = (held.aim_down and 1 or 0) - (held.aim_up and 1 or 0)
    if x == 0 and y == 0 then
        if held.right then state.facing = 1 elseif held.left then state.facing = -1 end
        x = state.facing or 1
    end
    local length = math.sqrt(x * x + y * y)
    return x / length, y / length
end

local PRESS_FRAME = {fire = "mButtonFrameFire", jump = "mButtonFrameJump", kick = "mButtonFrameKick"}

-- Drive the player for this frame. The ControlsComponent must be disabled ("enabled" =
-- false) so Noita doesn't overwrite these fields from the real keyboard and mouse.
-- state remembers presses between frames. Returns the button mask and the aim.
function A.apply_controls(player, controls, state)
    local held, mask = A.read_buttons()
    local frame = GameGetFrameNum()
    state.down = state.down or {}
    local function set(field, name, down)
        ComponentSetValue2(controls, field, down)
        local frame_field = PRESS_FRAME[name]
        if frame_field and down and not state.down[name] then ComponentSetValue2(controls, frame_field, frame) end
        state.down[name] = down
    end
    set("mButtonDownLeft", "left", held.left == true)
    set("mButtonDownRight", "right", held.right == true)
    set("mButtonDownUp", "up", held.up == true)
    set("mButtonDownDown", "down", held.down == true)
    -- As in vanilla, W (up) also jumps and levitates, not only Space.
    local rise = held.jump == true or held.up == true
    set("mButtonDownJump", "jump", rise)
    set("mButtonDownFly", "fly", rise)
    set("mButtonDownFire", "fire", held.fire == true)
    set("mButtonDownKick", "kick", held.kick == true)
    set("mButtonDownInteract", "interact", held.interact == true)
    local ax, ay = A.aim(held, state)
    local x, y = EntityGetTransform(player)
    -- Levitation climbs toward mFlyingTargetY. Noita's own input moves that target up while
    -- the key is held; nothing does that once the mod drives the controls, so the player
    -- would stall at a stale height. Keep it just above the player while rising.
    ComponentSetValue2(controls, "mFlyingTargetY", rise and y - A.FLY_LEAD or y)
    ComponentSetValue2(controls, "mAimingVector", ax * 100, ay * 100)
    ComponentSetValue2(controls, "mAimingVectorNormalized", ax, ay)
    ComponentSetValue2(controls, "mAimingVectorNonZeroLatest", ax * 100, ay * 100)
    ComponentSetValue2(controls, "mMousePosition", x + ax * 100, y - 4 + ay * 100)
    return mask, ax, ay
end

-- Release every button (episode over, or between rooms).
function A.release_controls(controls, state)
    for _, field in ipairs({"mButtonDownLeft", "mButtonDownRight", "mButtonDownUp", "mButtonDownDown",
        "mButtonDownJump", "mButtonDownFly", "mButtonDownFire", "mButtonDownKick", "mButtonDownInteract"}) do
        ComponentSetValue2(controls, field, false)
    end
    state.down = {}
end

---------------------------------------------------------------------------
-- Commands from Python (numpad keys, sent as real key presses to the Noita window)
--   digits then Enter : start an episode in that course room (1-based), e.g. "3" Enter
--   Enter alone / "."  : restart the current room
--   "*"                : toggle the overlay
-- Returns {room = n or nil} when an episode should (re)start, or nil.

function A.new_input() return {digits = ""} end

function A.read_commands(input)
    if InputIsKeyJustDown(KEY_MULTIPLY) then input.toggle_overlay = true end
    for key, digit in pairs(KEY_DIGITS) do
        if InputIsKeyJustDown(key) and #input.digits < 3 then input.digits = input.digits .. digit end
    end
    if InputIsKeyJustDown(KEY_PERIOD) then input.digits = ""; return {} end
    if InputIsKeyJustDown(KEY_ENTER) then
        local room = tonumber(input.digits)
        input.digits = ""
        return {room = room}
    end
    return nil
end

---------------------------------------------------------------------------
-- Drawing

function A.draw_strip(gui, bytes)
    local id = 3000
    for cell = 0, #bytes / 3 - 1 do
        local col, row = cell % A.COLS, math.floor(cell / A.COLS)
        local r, g, b = bytes[cell * 3 + 1], bytes[cell * 3 + 2], bytes[cell * 3 + 3]
        GuiZSetForNextWidget(gui, -1000)
        GuiColorSetForNextWidget(gui, r / 255, g / 255, b / 255, 1)
        GuiImage(gui, id + cell, A.ORIGIN_X + col * A.CELL, A.ORIGIN_Y + row * A.CELL, A.PIXEL, 1, A.CELL, A.CELL)
    end
    return A.ORIGIN_Y + math.ceil(#bytes / 3 / A.COLS) * A.CELL
end

-- World position to GUI coordinates (the camera is centred on the screen).
local function to_gui(gui, wx, wy)
    local sw, sh = GuiGetScreenDimensions(gui)
    local cx, cy = GameGetCameraPos()
    local vw = tonumber(MagicNumbersGetValue("VIRTUAL_RESOLUTION_X")) or 427
    local vh = tonumber(MagicNumbersGetValue("VIRTUAL_RESOLUTION_Y")) or 242
    return (wx - cx) * sw / vw + sw / 2, (wy - cy) * sh / vh + sh / 2
end

local function dot(gui, id, wx, wy, r, g, b, size)
    local x, y = to_gui(gui, wx, wy)
    GuiColorSetForNextWidget(gui, r, g, b, 0.9)
    GuiImage(gui, id, x - size / 2, y - size / 2, A.PIXEL, 1, size, size)
end

-- Overlay for people watching: ray hits, goal, enemies, and a sensor readout.
-- It is drawn below the strip, so it never covers the cells Python reads.
function A.draw_overlay(gui, s, wx, wy, top, labels)
    local id = 5000
    local cx, cy = wx, wy - 4
    for i = 1, A.RAYS do
        local dx, dy = A.ray_direction(i)
        local d = s.rays[i]
        if d < A.RAY_RANGE then dot(gui, id + i, cx + dx * d, cy + dy * d, 1, 1, 0.2, 2) end
        local l = s.liquid_rays[i]
        if l < d - 1 then dot(gui, id + 20 + i, cx + dx * l, cy + dy * l, 0.2, 0.6, 1, 2) end
    end
    if s.has_goal then dot(gui, id + 40, wx + s.goal_dx, wy + s.goal_dy, 0.3, 1, 0.3, 4) end
    for i, e in ipairs(s.enemies) do dot(gui, id + 50 + i, wx + e.dx, wy + e.dy, 1, 0.25, 0.25, 4) end
    for i, g in ipairs(s.golds) do dot(gui, id + 60 + i, wx + g.dx, wy + g.dy, 1, 0.85, 0.2, 3) end

    local lines = {
        string.format("RL AGENT  room %d/%d %s  attempt %d  episode %d  %s",
            s.room_index, s.room_count, labels.room, s.attempt, s.episode, labels.objective),
        string.format("time %.1f / %.1f s   reward %+.3f   return %+.3f%s",
            s.steps / 60, s.max_steps / 60, s.reward, s.episode_return,
            s.terminal and ("   DONE: " .. labels.reason) or ""),
        string.format("pos %.0f,%.0f  vel %.0f,%.0f  %s  hp %.2f/%.2f  gold %d  mana %.0f/%.0f",
            s.x, s.y, s.vx, s.vy, s.on_ground and "ground" or "air", s.hp, s.max_hp, s.gold, s.mana, s.mana_max),
        string.format("goal %s  enemies %d  gold left %d   keys %s   [numpad: N Enter = room, . = restart, * = overlay]",
            s.has_goal and string.format("%.0f px (%+.0f,%+.0f)%s", s.goal_dist, s.goal_dx, s.goal_dy,
                s.in_goal and " IN" or "") or "none", s.enemies_alive, s.gold_left, labels.buttons or ""),
    }
    for i, line in ipairs(lines) do GuiText(gui, 4, top + 2 + (i - 1) * 10, line) end
end
