dofile_once("mods/noita_rl/files/editor/model.lua")
dofile_once("mods/noita_rl/files/scripts/loadout.lua")
dofile_once("mods/noita_rl/files/agent/agent.lua")
local M = EditorModel
local ROOT = "mods/noita_rl/files/editor/"
-- Exported rooms are stored as mod settings: noita_rl.export_<id> holds the scenario JSON
-- that `noita-rl pull-rooms` reads; noita_rl.room_<id> holds the editable blueprint that
-- courses are built from. noita_rl.course is the ordered, comma-separated list of ids.
local EXPORT_PREFIX = "noita_rl.export_"
local ROOM_PREFIX = "noita_rl.room_"
local COURSE_KEY = "noita_rl.course"
-- Saved courses: noita_rl.course_slot_<n>. "Course to play" in Mod settings (noita_rl.play_course)
-- picks the slot that Human mode starts.
local COURSE_SLOT_PREFIX = "noita_rl.course_slot_"
local PLAY_COURSE_KEY = "noita_rl.play_course"
local function chosen_slot()
    local slot = tonumber(ModSettingGet(PLAY_COURSE_KEY))
    if slot and slot >= 1 and slot <= M.course_slots then return math.floor(slot) end
    return 1
end
local E = {
    room = M.decode(ModSettingGet("noita_rl.editor_draft")) or M.new(),
    editing = true, tool = "material", value = 2, slot = 1,
    undo = {}, redo = {}, stroke = false, anchor = nil, player = nil, spawned = {},
    library = {}, pick = 1, course = M.parse_course(ModSettingGet(COURSE_KEY)),
    course_slot = chosen_slot(),
    human = false, -- Mode "human" or "agent": play the chosen course only, no editor
    agent = false, -- Mode "agent": Python drives; telemetry strip, overlay, numpad commands
    episode = 0, cmd_seq = 0, overlay = ModSettingGet("noita_rl.agent_overlay") ~= false,
    run = nil, -- active play test or course: {rooms, ids, index, attempts, course, started}
    message = "Paint your room, place P (player), set the objective, then Play test.",
}

-- Crash breadcrumbs: print() never reaches logger.txt in release Noita, but mod
-- settings are flushed to save00/mod_settings.bin. Each stage is recorded once;
-- `uv run noita-rl debug-status` shows how far the editor got before a crash.
local traced, trace_log = {}, {"init"}
local function trace(stage)
    if traced[stage] then return end
    traced[stage] = true
    table.insert(trace_log, stage)
    ModSettingSet("noita_rl.debug_stage", stage)
    ModSettingSet("noita_rl.debug_trace", table.concat(trace_log, " > "))
end

local function persist()
    ModSettingSet("noita_rl.editor_draft", M.encode(E.room))
end

local function checkpoint()
    table.insert(E.undo, M.encode(E.room))
    if #E.undo > 50 then table.remove(E.undo, 1) end
    E.redo = {}
end

local function history(from, to)
    if #from == 0 then return end
    table.insert(to, M.encode(E.room))
    E.room = M.decode(table.remove(from))
    persist()
end

local function scenario_text(room)
    return (string.gsub(M.json(M.to_scenario(room)), "\n%s*", ""))
end

-- Rooms available for courses: every noita_rl.room_<id> mod setting.
local function refresh_library()
    local ids = {}
    for i = 0, ModSettingGetCount() - 1 do
        local name = ModSettingGetAtIndex(i)
        if name and string.sub(name, 1, #ROOM_PREFIX) == ROOM_PREFIX then
            table.insert(ids, string.sub(name, #ROOM_PREFIX + 1))
        end
    end
    table.sort(ids)
    E.library = ids
    if E.pick > #ids then E.pick = 1 end
end

-- Rooms exported before courses existed have JSON but no blueprint. Recover the
-- blueprint from the draft or a slot, but only if it reproduces that export exactly.
local function recover_blueprints()
    for _, key in ipairs({"noita_rl.editor_draft", "noita_rl.editor_slot_1",
                          "noita_rl.editor_slot_2", "noita_rl.editor_slot_3"}) do
        local room = M.decode(ModSettingGet(key))
        if room and not ModSettingGet(ROOM_PREFIX .. room.name) and
            ModSettingGet(EXPORT_PREFIX .. room.name) == scenario_text(room) then
            ModSettingSet(ROOM_PREFIX .. room.name, M.encode(room))
        end
    end
    E.course = M.parse_course(ModSettingGet(COURSE_KEY))
    refresh_library()
end

local function component(kind)
    return EntityGetFirstComponentIncludingDisabled(E.player, kind)
end

local function teleport(room, ox, oy)
    local x, y = M.position(room.spawn)
    EntitySetTransform(E.player, ox + x, oy + y)
    local character = component("CharacterDataComponent")
    if character then ComponentSetValue2(character, "mVelocity", 0, 0) end
end

local function controls(enabled)
    -- Use the component's own "enabled" field. Vanilla never disables the player's
    -- ControlsComponent itself (EntitySetComponentIsEnabled), which can crash the engine.
    local control = component("ControlsComponent")
    if control then ComponentSetValue2(control, "enabled", enabled) end
end

local function heal(frames)
    local damage = component("DamageModelComponent")
    if damage then
        ComponentSetValue2(damage, "hp", 4)
        ComponentSetValue2(damage, "invincibility_frames", frames)
    end
end

local function clear_entities_near(ox, oy)
    -- Include projectiles and dropped loot, but never the player or their inventory.
    for _, tag in ipairs({"enemy", "projectile", "item_pickup"}) do
        for _, entity in ipairs(EntityGetInRadiusWithTag(ox + 128, oy + 80, 256, tag) or {}) do
            if EntityGetRootEntity(entity) ~= E.player then EntityKill(entity) end
        end
    end
end

local function clear_spawned()
    for _, spawned in ipairs(E.spawned) do
        if EntityGetIsAlive(spawned.entity) then EntityKill(spawned.entity) end
    end
    E.spawned = {}
end

local function stamp(filename, x, y)
    LoadPixelScene(ROOT .. "terrain/" .. filename .. ".png", "", x, y, "", true, true, {}, 50, true)
end

-- Stamp a room's terrain with its top-left corner at world (ox, oy).
local function build_room(room, ox, oy)
    clear_entities_near(ox, oy)
    -- Clear simulated liquids and damaged terrain as well as the original tiles.
    stamp("clear", ox - 32, oy - 32)
    for index, material in ipairs(room.tiles) do
        if material ~= 1 then
            local x, y = M.position(index)
            stamp(M.materials[material], ox + x - 4, oy + y - 4)
        end
    end
end

local function enter_editor(message)
    E.editing = true
    E.run = nil
    E.stroke = false
    controls(false)
    clear_spawned()
    clear_entities_near(0, 0)
    build_room(E.room, 0, 0)
    heal(120)
    teleport(E.room, 0, 0)
    GameSetCameraFree(true)
    GameSetCameraPos(128, 80)
    E.message = message or "Editing blueprint. Play test rebuilds the room."
    refresh_library()
    persist()
end

-- (Re)start the current room of the active run: fresh terrain, spawns, loadout, timer.
local function start_room()
    local run = E.run
    local room = run.rooms[run.index]
    local ox, oy = M.room_origin(run.index)
    clear_spawned()
    build_room(room, ox, oy)
    noita_rl_apply_loadout(E.player, {player = {
        hp = 4, gold = 0,
        inventory = {{entity = "data/entities/items/wand_level_01.xml", spells = {"LIGHT_BULLET"}}},
    }})
    local wallet = component("WalletComponent")
    if wallet then ComponentSetValue2(wallet, "money", 0) end
    teleport(room, ox, oy)
    for index, kind in pairs(room.objects) do
        local x, y = M.position(index)
        local entity = EntityLoad(M.entities[kind].path, ox + x, oy + y)
        if entity and entity ~= 0 then table.insert(E.spawned, {entity = entity, kind = kind}) end
    end
    run.attempts = run.attempts + 1
    run.done = nil
    E.episode = E.episode + 1
    E.play_frame = GameGetFrameNum()
    -- Reward bookkeeping for agent episodes (same terms as the exported scenario rewards).
    run.last_hp = 4 -- heal() below restores 4 HP
    run.last_gold, run.kills, run.episode_return = 0, 0, 0
    -- Keep controls disabled until the GUI mouse click has been released.
    controls(false)
    heal(60)
    GameSetCameraFree(false)
end

local function start_run(rooms, ids, course)
    E.editing = false
    E.run = {rooms = rooms, ids = ids, index = 1, attempts = 0, course = course,
             started = GameGetFrameNum(), note = ""}
    if course then
        -- Lay the whole course out in the world first, so it exists as one map.
        for position, room in ipairs(rooms) do
            local ox, oy = M.room_origin(position)
            build_room(room, ox, oy)
        end
    end
    start_room()
    persist()
end

local function play()
    local problem = M.problem(E.room)
    if problem then E.message = problem; return end
    start_run({E.room}, {E.room.name}, false)
end

-- Decode every room of a course; returns the rooms, or nil and the reason.
local function course_rooms(ids)
    if #ids == 0 then return nil, "The course is empty: pick an exported room and click Add." end
    local rooms = {}
    for _, id in ipairs(ids) do
        local room = M.decode(ModSettingGet(ROOM_PREFIX .. id))
        if not room then return nil, "Course room " .. id .. " is missing. Export it again." end
        local problem = M.problem(room)
        if problem then return nil, "Course room " .. id .. ": " .. problem end
        table.insert(rooms, room)
    end
    return rooms
end

local function play_course()
    local rooms, problem = course_rooms(E.course)
    if not rooms then E.message = problem; return end
    persist()
    start_run(rooms, E.course, true)
end

-- Human mode: start the course chosen in Mod settings. If it can't be played, stay
-- frozen in the editor room and show why (draw_human_error), never the canvas.
local function start_human()
    local slot = chosen_slot()
    local ids = M.parse_course(ModSettingGet(COURSE_SLOT_PREFIX .. slot))
    local rooms, problem = course_rooms(ids)
    if not rooms then
        enter_editor("Can't start course " .. slot .. ": " .. problem ..
            " Set Mode to Room editor, build the course and click Save course in slot " .. slot .. ".")
        return
    end
    start_run(rooms, ids, true)
end

local function restart_course(note)
    local run = E.run
    run.index, run.attempts, run.started, run.note = 1, 0, GameGetFrameNum(), note
    start_room()
end

local function save_course_slot()
    if #E.course == 0 then E.message = "The course is empty: nothing to save."; return end
    local key = COURSE_SLOT_PREFIX .. E.course_slot
    local replaced = ModSettingGet(key) and " (replaced the previous one)" or ""
    ModSettingSet(key, M.course_text(E.course))
    E.message = "Saved the course in course slot " .. E.course_slot .. replaced ..
        ". Pick it under Mod settings > Course to play."
end

local function load_course_slot()
    local ids = M.parse_course(ModSettingGet(COURSE_SLOT_PREFIX .. E.course_slot))
    if #ids == 0 then E.message = "Course slot " .. E.course_slot .. " is empty."; return end
    E.course = ids
    ModSettingSet(COURSE_KEY, M.course_text(ids))
    E.message = "Loaded course slot " .. E.course_slot .. " (" .. #ids .. " rooms)."
end

local function export()
    local problem = M.problem(E.room)
    if problem then E.message = "Not exported: " .. problem; return end
    -- Mods are sandboxed (no file access), but mod settings are saved to
    -- save00/mod_settings.bin, which `noita-rl pull-rooms` reads. One compact line each.
    ModSettingSet(EXPORT_PREFIX .. E.room.name, scenario_text(E.room))
    ModSettingSet(ROOM_PREFIX .. E.room.name, M.encode(E.room))
    refresh_library()
    E.message = "Exported " .. E.room.name .. " (now available for courses). Next: uv run noita-rl pull-rooms"
end

local function save_course()
    ModSettingSet(COURSE_KEY, M.course_text(E.course))
end

-- Score the current room exactly as an agent episode would be scored.
local function room_result()
    local run = E.run
    local room = run.rooms[run.index]
    local ox, oy = M.room_origin(run.index)
    local steps = GameGetFrameNum() - E.play_frame
    local objective = M.objectives[room.objective].id
    local seconds = string.format("%.1f s", steps / 60)
    local damage = component("DamageModelComponent")
    local x, y = EntityGetTransform(E.player)
    -- Third value: the terminal reason code reported to the agent (NoitaAgent.REASON).
    if damage and ComponentGetValue2(damage, "hp") <= 0.04 then return false, "died", 2 end
    if M.outside(ox, oy, x, y) then return false, "left the room", 3 end
    if objective == "reach_goal" then
        if M.in_goal_world(room, ox, oy, x, y) then return true, "reached goal in " .. seconds, 1 end
    elseif objective == "kill_all" then
        local alive = 0
        for _, spawned in ipairs(E.spawned) do
            if M.entities[spawned.kind].enemy and EntityGetIsAlive(spawned.entity) then alive = alive + 1 end
        end
        if alive == 0 then return true, "all enemies killed in " .. seconds, 1 end
    elseif objective == "collect_gold" then
        local _, gold = M.counts(room)
        local wallet = component("WalletComponent")
        if wallet and ComponentGetValue2(wallet, "money") >= gold then
            return true, "collected all gold in " .. seconds, 1
        end
    end
    if steps >= M.max_steps(room) then
        if objective == "survive" then return true, "survived " .. seconds, 1 end
        return false, "timed out after " .. seconds, 4
    end
    return nil, M.time_limits[room.time] - math.floor(steps / 60)
end

local function update_run(gui)
    local run = E.run
    local success, detail = room_result()
    if success == nil then
        local label = run.course and string.format("Course room %d/%d: %s   Attempt %d   ", run.index, #run.rooms,
            run.ids[run.index], run.attempts) or ""
        GuiText(gui, 6, 20, label .. "Objective: " .. M.objectives[run.rooms[run.index].objective].label ..
            "   Time left: " .. detail .. " s")
        if run.note ~= "" then GuiText(gui, 6, 32, run.note) end
        return
    end
    if not run.course then
        enter_editor((success and "SUCCESS: " or "FAILED: ") .. detail ..
            (success and ". Edit, Play test again, or Export for RL." or ". Your blueprint is intact."))
    elseif not success then
        run.note = "Room " .. run.index .. " failed (" .. detail .. "): restarting it."
        start_room()
    elseif run.index < #run.rooms then
        run.note = "Room " .. run.index .. " cleared: " .. detail .. ". Teleported to the next room."
        run.index, run.attempts = run.index + 1, 0
        start_room()
    else
        local total = string.format("%.1f s", (GameGetFrameNum() - run.started) / 60)
        local done = "COURSE COMPLETE: " .. #run.rooms .. " rooms in " .. total .. "."
        if E.human then restart_course(done .. " Starting again from room 1.")
        else enter_editor(done) end
    end
end

-- First-time setup runs one step per frame, each followed by a breadcrumb, so a crash
-- in the engine (no Lua error) still shows which step caused it.
local SETUP = {
    {"setup_damage", function()
        local damage = component("DamageModelComponent")
        if damage then
            -- Fatal damage returns to the editor instead of opening the death screen.
            ComponentSetValue2(damage, "wait_for_kill_flag_on_death", true)
            ComponentSetValue2(damage, "max_hp", 4)
        end
    end},
    {"setup_room", function() build_room(E.room, 0, 0) end},
    {"setup_controls", function() controls(false) end},
    {"setup_position", function() teleport(E.room, 0, 0) end},
    {"setup_camera", function() GameSetCameraFree(true); GameSetCameraPos(128, 80) end},
    {"setup_library", function() recover_blueprints() end},
    {"setup_editor", function()
        local mode = ModSettingGet("noita_rl.mode")
        E.agent = mode == "agent"
        E.human = mode == "human" or E.agent
        if E.agent then E.input, E.control_state = NoitaAgent.new_input(), {} end
        if E.human then start_human() else enter_editor() end
    end},
}

function noita_editor_spawn(player)
    if E.player == player then return end
    trace("spawn")
    E.player = player
    E.setup = 1
end

function noita_editor_pre_update()
    if not E.player or not EntityGetIsAlive(E.player) then return end
    if E.setup then
        local step = SETUP[E.setup]
        trace(step[1] .. "_begin")
        step[2]()
        trace(step[1] .. "_done")
        E.setup = E.setup < #SETUP and E.setup + 1 or nil
        return
    end
    trace("pre_update")
    if E.editing then
        controls(false)
        teleport(E.room, 0, 0)
        heal(120)
    elseif E.agent then
        -- The real keyboard and mouse never move the agent's player: its ControlsComponent
        -- stays disabled and the mod writes the buttons from the action keys Python posts.
        controls(false)
        local control = component("ControlsComponent")
        if not control then return end
        if E.run and not E.run.done and GameGetFrameNum() > E.play_frame + 1 then
            E.buttons, E.aim_x, E.aim_y = NoitaAgent.apply_controls(E.player, control, E.control_state)
        else
            NoitaAgent.release_controls(control, E.control_state) -- frozen while a result is shown
            E.buttons, E.aim_x, E.aim_y = 0, 0, 0
        end
    elseif E.run and E.run.done then
        controls(false)
    elseif not InputIsMouseButtonDown(1) and GameGetFrameNum() > E.play_frame + 1 then
        controls(true)
    end
end

local function tool_button(gui, id, y, tool, label)
    if GuiButton(gui, id, 6, y, (E.tool == tool and "> " or "") .. label) then E.tool = tool end
end

local function draw_course(gui, y)
    local picked = E.library[E.pick]
    GuiText(gui, 6, y, "COURSE  (" .. #E.course .. "/" .. M.max_course .. "):  " ..
        (#E.course > 0 and table.concat(E.course, "  >  ") or "empty"))
    GuiText(gui, 6, y + 12, "Exported room: " .. (picked or "none yet - use Export for RL"))
    if GuiButton(gui, 60, 150, y + 12, "<") and #E.library > 0 then E.pick = (E.pick - 2) % #E.library + 1 end
    if GuiButton(gui, 61, 162, y + 12, ">") and #E.library > 0 then E.pick = E.pick % #E.library + 1 end
    if GuiButton(gui, 62, 180, y + 12, "Add to course") and picked then
        if #E.course >= M.max_course then E.message = "A course holds at most " .. M.max_course .. " rooms."
        else table.insert(E.course, picked); save_course(); E.message = "Added " .. picked .. " to the course." end
    end
    if GuiButton(gui, 63, 252, y + 12, "Remove last") and #E.course > 0 then
        E.message = "Removed " .. table.remove(E.course) .. " from the course."; save_course()
    end
    if GuiButton(gui, 65, 318, y + 12, "Clear") and #E.course > 0 then
        E.course = {}; save_course(); E.message = "Cleared the course. Load restores a saved one."
    end
    if GuiButton(gui, 64, 350, y + 12, "Play course") then play_course() end
    -- Saved courses: Human mode and (later) the RL agent play the slot chosen in Mod settings.
    local saved = M.parse_course(ModSettingGet(COURSE_SLOT_PREFIX .. E.course_slot))
    if GuiButton(gui, 66, 6, y + 24, "Course slot " .. E.course_slot) then
        E.course_slot = E.course_slot % M.course_slots + 1
    end
    if GuiButton(gui, 67, 80, y + 24, "Save course") then save_course_slot() end
    if GuiButton(gui, 68, 140, y + 24, "Load course") then load_course_slot() end
    GuiText(gui, 200, y + 24, #saved > 0 and ("Slot holds: " .. table.concat(saved, " > ")) or "Slot is empty")
end

local function draw_human_error(gui)
    GuiText(gui, 6, 4, "NOITA ROOM EDITOR  |  " .. (E.agent and "RL agent" or "Human") .. " mode")
    GuiText(gui, 6, 18, E.message)
end

local REASON_LABELS = {[0] = "", "success", "died", "left the room", "timed out"}

local function held_names(mask)
    local names = {}
    for i, button in ipairs(NoitaAgent.BUTTONS) do
        if math.floor(mask / 2 ^ (i - 1)) % 2 == 1 then table.insert(names, button.name) end
    end
    return #names > 0 and table.concat(names, "+") or "none"
end

-- This frame's reward, from the room's objective rewards (as in the exported scenario).
local function agent_reward(run, room, success)
    local rewards = M.rewards[M.objectives[room.objective].id]
    local reward = rewards.per_step
    local damage = component("DamageModelComponent")
    local hp = damage and ComponentGetValue2(damage, "hp") or 0
    if hp < run.last_hp - 0.0001 then reward = reward + rewards.damage_taken end
    run.last_hp = hp
    local wallet = component("WalletComponent")
    local gold = wallet and ComponentGetValue2(wallet, "money") or 0
    if gold > run.last_gold then reward = reward + rewards.pickup_gold * (gold - run.last_gold) end
    run.last_gold = gold
    local alive_now = 0
    for _, spawned in ipairs(E.spawned) do
        if M.entities[spawned.kind].enemy and EntityGetIsAlive(spawned.entity) then alive_now = alive_now + 1 end
    end
    local enemies = M.counts(room)
    local kills = enemies - alive_now
    if kills > run.kills then reward = reward + rewards.enemy_kill * (kills - run.kills) end
    run.kills = kills
    if success then reward = reward + rewards.goal_reached end
    return reward
end

-- One agent frame: commands, scoring, sensors, strip and overlay. A finished episode is
-- held for HOLD_FRAMES (so Python sees it), then continues on its own: the next room after
-- a success, the same room after a failure. Python can restart any room at any time.
local function update_agent(gui)
    local A, run = NoitaAgent, E.run
    local command = A.read_commands(E.input)
    if E.input.toggle_overlay then E.input.toggle_overlay = nil; E.overlay = not E.overlay end
    if command then
        E.cmd_seq = E.cmd_seq + 1
        if command.room and command.room >= 1 and command.room <= #run.rooms then
            run.index = command.room
            run.attempts = 0
        end
        start_room()
    end
    local room = run.rooms[run.index]
    local now = GameGetFrameNum()
    local reward = 0
    if not run.done then
        local success, _, reason = room_result()
        reward = agent_reward(run, room, success == true)
        run.episode_return = run.episode_return + reward
        if success ~= nil then run.done = {reason = reason, frame = now, steps = now - E.play_frame} end
    elseif now - run.done.frame >= A.HOLD_FRAMES then
        if run.done.reason == A.REASON.success then
            run.index, run.attempts = run.index % #run.rooms + 1, 0
        end
        start_room()
        room, run.done = run.rooms[run.index], nil
    end

    local ox, oy = M.room_origin(run.index)
    local s = A.sense({player = E.player, room = room, ox = ox, oy = oy, spawned = E.spawned, model = M})
    s.frame, s.episode, s.cmd_seq = now, E.episode, E.cmd_seq
    s.room_index, s.room_count, s.attempt, s.objective = run.index, #run.rooms, run.attempts, room.objective
    s.terminal, s.reason = run.done ~= nil, run.done and run.done.reason or 0
    s.steps = run.done and run.done.steps or (now - E.play_frame)
    s.max_steps = M.max_steps(room)
    s.reward, s.episode_return, s.overlay = reward, run.episode_return, E.overlay
    s.buttons, s.aim_x, s.aim_y = E.buttons or 0, E.aim_x or 0, E.aim_y or 0
    local top = A.draw_strip(gui, A.pack(s))
    if E.overlay then
        local wx, wy = EntityGetTransform(E.player)
        A.draw_overlay(gui, s, wx, wy, top, {room = run.ids[run.index],
            objective = M.objectives[room.objective].label, reason = REASON_LABELS[s.reason],
            buttons = held_names(s.buttons)})
    end
end

local function draw_editor(gui)
    trace("draw_start")
    GuiText(gui, 6, 4, "NOITA ROOM EDITOR  |  256 x 160 pixels / 8px tiles")
    if GuiButton(gui, 1, 6, 18, "Play test") then play(); return end
    if GuiButton(gui, 2, 64, 18, "Undo") then history(E.undo, E.redo) end
    if GuiButton(gui, 3, 100, 18, "Redo") then history(E.redo, E.undo) end
    if GuiButton(gui, 4, 136, 18, "New room") then
        checkpoint(); E.room = M.new(); persist(); E.message = "New room. Undo restores the previous design."
    end
    if GuiButton(gui, 5, 200, 18, "Slot " .. E.slot) then E.slot = E.slot % 3 + 1 end
    if GuiButton(gui, 6, 245, 18, "Save") then
        ModSettingSet("noita_rl.editor_slot_" .. E.slot, M.encode(E.room))
        E.message = "Saved blueprint in slot " .. E.slot
    end
    if GuiButton(gui, 7, 282, 18, "Load") then
        local room = M.decode(ModSettingGet("noita_rl.editor_slot_" .. E.slot))
        if room then
            checkpoint(); E.room = room; persist(); E.message = "Loaded slot " .. E.slot .. ". Undo restores previous design."
        else E.message = "Slot " .. E.slot .. " is empty or invalid." end
    end
    if GuiButton(gui, 8, 318, 18, "Export for RL") then export() end
    trace("draw_toolbar_done")
    GuiText(gui, 6, 34, "Left drag: paint   Right drag: erase   P: player   S/Z/$: spawns   G: goal zone")
    for i, label in ipairs(M.labels) do
        local selected = E.tool == "material" and E.value == i
        if GuiButton(gui, 20 + i, 6, 52 + (i - 1) * 11, (selected and "> " or "") .. label) then
            E.tool, E.value = "material", i
        end
    end
    tool_button(gui, 40, 143, "spawn", "Player spawn")
    for i, object in ipairs(M.entities) do
        local selected = E.tool == "entity" and E.value == i
        if GuiButton(gui, 40 + i, 6, 143 + i * 11, (selected and "> " or "") .. object.label) then
            E.tool, E.value = "entity", i
        end
    end
    tool_button(gui, 45, 187, "remove", "Remove spawn")
    tool_button(gui, 46, 198, "goal", "Goal zone")

    local left, right = InputIsMouseButtonDown(1), InputIsMouseButtonDown(2)
    if not left and not right and E.stroke then E.stroke = false; E.anchor = nil; persist() end
    for index, material in ipairs(E.room.tiles) do
        local x = 100 + ((index - 1) % M.width) * 8
        local y = 52 + math.floor((index - 1) / M.width) * 8
        local clicked, right_clicked = GuiImageButton(gui, 1000 + index, x, y, "", ROOT .. "ui/" .. M.materials[material] .. ".png")
        local _, _, hovered = GuiGetPreviousWidgetInfo(gui)
        if clicked or right_clicked or (hovered and (left or right)) then
            if not E.stroke then checkpoint(); E.stroke = true; E.anchor = index end
            if E.tool == "goal" then
                if right or right_clicked then E.room.goal = nil
                else M.set_goal(E.room, E.anchor, index) end
            elseif right or right_clicked then M.paint(E.room, index, "material", 1)
            else M.paint(E.room, index, E.tool, E.value) end
        end
        local marker = index == E.room.spawn and "P" or
            (E.room.objects[index] and M.entities[E.room.objects[index]].marker)
        if marker then
            GuiOptionsAddForNextWidget(gui, GUI_OPTION.NonInteractive)
            GuiColorSetForNextWidget(gui, 1, 1, 1, 1)
            GuiText(gui, x, y - 1, marker)
        elseif M.in_goal(E.room, index) then
            GuiOptionsAddForNextWidget(gui, GUI_OPTION.NonInteractive)
            GuiColorSetForNextWidget(gui, 0.3, 1, 0.3, 1)
            GuiText(gui, x + 1, y - 1, "G")
        end
    end

    trace("draw_grid_done")
    -- Task settings: what counts as success for the agent, and how long it has.
    local objective = M.objectives[E.room.objective]
    if GuiButton(gui, 50, 6, 218, "Objective: " .. objective.label) then
        checkpoint(); E.room.objective = E.room.objective % #M.objectives + 1; persist()
    end
    if GuiButton(gui, 51, 190, 218, "Time limit: " .. M.time_limits[E.room.time] .. " s") then
        checkpoint(); E.room.time = E.room.time % #M.time_limits + 1; persist()
    end
    -- Pick the id with buttons: Noita's docs warn GuiTextInput "might bug" outside the
    -- mod settings menu, and it is the prime suspect for an in-game crash.
    GuiText(gui, 270, 218, "Scenario id: " .. E.room.name)
    if GuiButton(gui, 52, 372, 218, "<") then E.room.name = M.step_name(E.room.name, -1); persist() end
    if GuiButton(gui, 53, 384, 218, ">") then E.room.name = M.step_name(E.room.name, 1); persist() end
    draw_course(gui, 232)
    GuiText(gui, 6, 272, E.message)
    trace("draw_done")
end

function noita_editor_update()
    if not E.player or not EntityGetIsAlive(E.player) or E.setup then return end
    if not E.gui then E.gui = GuiCreate() end
    trace("update")
    GuiStartFrame(E.gui)
    if E.editing then
        GuiBeginAutoBox(E.gui)
        if E.human then draw_human_error(E.gui) else draw_editor(E.gui) end
        GuiEndAutoBoxNinePiece(E.gui, 4)
        if traced["first_frame_done"] then trace("second_frame_done") end
        trace("first_frame_done")
        return
    end
    if E.agent then update_agent(E.gui); return end
    if E.human then
        if GuiButton(E.gui, 10, 6, 6, "Restart course") then restart_course("Restarted the course."); return end
    elseif GuiButton(E.gui, 10, 6, 6, "Return to editor") then enter_editor(); return end
    if E.run.course and GuiButton(E.gui, 11, 100, 6, "Skip room") then
        if E.run.index < #E.run.rooms then
            E.run.index, E.run.attempts, E.run.note = E.run.index + 1, 0, "Skipped to the next room."
            start_room()
        elseif E.human then restart_course("Skipped the last room. Starting again from room 1.")
        else enter_editor("Course ended (skipped the last room).") end
        return
    end
    update_run(E.gui)
end
