dofile_once("mods/noita_rl/files/editor/model.lua")
dofile_once("mods/noita_rl/files/scripts/loadout.lua")
local M = EditorModel
local ROOT = "mods/noita_rl/files/editor/"
-- Exported rooms are stored as mod settings: noita_rl.export_<id> holds the scenario JSON
-- that `noita-rl pull-rooms` reads; noita_rl.room_<id> holds the editable blueprint that
-- courses are built from. noita_rl.course is the ordered, comma-separated list of ids.
local EXPORT_PREFIX = "noita_rl.export_"
local ROOM_PREFIX = "noita_rl.room_"
local COURSE_KEY = "noita_rl.course"
local E = {
    room = M.decode(ModSettingGet("noita_rl.editor_draft")) or M.new(),
    editing = true, tool = "material", value = 2, slot = 1,
    undo = {}, redo = {}, stroke = false, anchor = nil, player = nil, spawned = {},
    library = {}, pick = 1, course = M.parse_course(ModSettingGet(COURSE_KEY)),
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
    E.play_frame = GameGetFrameNum()
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

local function play_course()
    if #E.course == 0 then E.message = "The course is empty: pick an exported room and click Add."; return end
    local rooms = {}
    for _, id in ipairs(E.course) do
        local room = M.decode(ModSettingGet(ROOM_PREFIX .. id))
        if not room then E.message = "Course room " .. id .. " is missing. Export it again."; return end
        local problem = M.problem(room)
        if problem then E.message = "Course room " .. id .. ": " .. problem; return end
        table.insert(rooms, room)
    end
    persist()
    start_run(rooms, E.course, true)
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
    if damage and ComponentGetValue2(damage, "hp") <= 0.04 then return false, "died" end
    if M.outside(ox, oy, x, y) then return false, "left the room" end
    if objective == "reach_goal" then
        if M.in_goal_world(room, ox, oy, x, y) then return true, "reached goal in " .. seconds end
    elseif objective == "kill_all" then
        local alive = 0
        for _, spawned in ipairs(E.spawned) do
            if M.entities[spawned.kind].enemy and EntityGetIsAlive(spawned.entity) then alive = alive + 1 end
        end
        if alive == 0 then return true, "all enemies killed in " .. seconds end
    elseif objective == "collect_gold" then
        local _, gold = M.counts(room)
        local wallet = component("WalletComponent")
        if wallet and ComponentGetValue2(wallet, "money") >= gold then return true, "collected all gold in " .. seconds end
    end
    if steps >= M.max_steps(room) then
        if objective == "survive" then return true, "survived " .. seconds end
        return false, "timed out after " .. seconds
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
        enter_editor("COURSE COMPLETE: " .. #run.rooms .. " rooms in " .. total .. ".")
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
    {"setup_editor", function() enter_editor() end},
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
    if GuiButton(gui, 64, 318, y + 12, "Play course") then play_course() end
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
    GuiText(gui, 6, 260, E.message)
    trace("draw_done")
end

function noita_editor_update()
    if not E.player or not EntityGetIsAlive(E.player) or E.setup then return end
    if not E.gui then E.gui = GuiCreate() end
    trace("update")
    GuiStartFrame(E.gui)
    if E.editing then
        GuiBeginAutoBox(E.gui)
        draw_editor(E.gui)
        GuiEndAutoBoxNinePiece(E.gui, 4)
        if traced["first_frame_done"] then trace("second_frame_done") end
        trace("first_frame_done")
        return
    end
    if GuiButton(E.gui, 10, 6, 6, "Return to editor") then enter_editor(); return end
    if E.run.course and GuiButton(E.gui, 11, 100, 6, "Skip room") then
        if E.run.index < #E.run.rooms then
            E.run.index, E.run.attempts, E.run.note = E.run.index + 1, 0, "Skipped to the next room."
            start_room()
        else enter_editor("Course ended (skipped the last room).") end
        return
    end
    update_run(E.gui)
end
