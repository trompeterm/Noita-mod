-- Pure blueprint operations; no game API or executable save-file contents.
EditorModel = {}
local M = EditorModel
M.width, M.height, M.cell = 32, 20, 8
M.materials = {"air", "rock_static", "wood_static", "steel_static", "water", "lava", "snow_static", "gold_static"}
M.labels = {"Air / erase", "Rock", "Wood", "Steel", "Water", "Lava", "Snow", "Gold"}
M.entities = {
    {label = "Slime shooter", path = "data/entities/animals/slimeshooter_weak.xml", marker = "S", enemy = true},
    {label = "Zombie", path = "data/entities/animals/zombie.xml", marker = "Z", enemy = true},
    {label = "Gold pickup", path = "data/entities/items/pickup/goldnugget_50.xml", marker = "$", gold = 50},
}
-- What the agent must do to end an episode successfully.
M.objectives = {
    {id = "reach_goal", label = "Reach goal zone"},
    {id = "kill_all", label = "Kill all enemies"},
    {id = "collect_gold", label = "Collect all gold"},
    {id = "survive", label = "Survive until time runs out"},
}
M.time_limits = {10, 20, 30, 60, 120} -- seconds; 60 frames each
M.id_chars = "abcdefghijklmnopqrstuvwxyz0123456789_"
M.seed = 1337
M.origin = {x = 0, y = 0}

function M.new()
    local room = {tiles = {}, objects = {}, spawn = 3 + 16 * M.width + 1,
        goal = {x0 = 27, y0 = 14, x1 = 30, y1 = 17}, objective = 1, time = 3, name = "my_room"}
    for y = 0, M.height - 1 do
        for x = 0, M.width - 1 do
            room.tiles[y * M.width + x + 1] =
                (x == 0 or y == 0 or x == M.width - 1 or y >= M.height - 2) and 4 or 1
        end
    end
    return room
end

local function goal_text(goal)
    if not goal then return "-" end
    return goal.x0 .. "," .. goal.y0 .. "," .. goal.x1 .. "," .. goal.y1
end

function M.encode(room)
    local tiles, objects = {}, {}
    for i = 1, M.width * M.height do
        tiles[i] = tostring(room.tiles[i])
        objects[i] = tostring(room.objects[i] or 0)
    end
    return "NRE2:" .. room.spawn .. ":" .. table.concat(tiles) .. ":" .. table.concat(objects) ..
        ":" .. goal_text(room.goal) .. ":" .. room.objective .. ":" .. room.time .. ":" .. room.name
end

local function decode_grid(spawn, tiles, objects)
    spawn = tonumber(spawn)
    if not spawn or spawn < 1 or spawn > M.width * M.height or
        #tiles ~= M.width * M.height or #objects ~= #tiles then return nil end
    local room = {spawn = spawn, tiles = {}, objects = {}}
    for i = 1, #tiles do
        room.tiles[i] = tonumber(string.sub(tiles, i, i))
        local object = tonumber(string.sub(objects, i, i))
        if object ~= 0 then room.objects[i] = object end
    end
    return room
end

function M.decode(text)
    if type(text) ~= "string" then return nil end
    -- Version 1 saves (before goals and objectives) still load with defaults.
    local spawn, tiles, objects = string.match(text, "^NRE1:(%d+):([1-8]+):([0-3]+)$")
    if spawn then
        local room = decode_grid(spawn, tiles, objects)
        if not room then return nil end
        local defaults = M.new()
        room.goal, room.objective, room.time, room.name = defaults.goal, 1, defaults.time, defaults.name
        return room
    end
    local goal, objective, time, name
    spawn, tiles, objects, goal, objective, time, name = string.match(text,
        "^NRE2:(%d+):([1-8]+):([0-3]+):([%d,%-]+):(%d):(%d):([a-z][a-z0-9_]*)$")
    local room = decode_grid(spawn, tiles, objects)
    objective, time = tonumber(objective), tonumber(time)
    if not room or not M.objectives[objective or 0] or not M.time_limits[time or 0] or #name > 32 then
        return nil
    end
    if goal ~= "-" then
        local x0, y0, x1, y1 = string.match(goal, "^(%d+),(%d+),(%d+),(%d+)$")
        x0, y0, x1, y1 = tonumber(x0), tonumber(y0), tonumber(x1), tonumber(y1)
        if not x0 or x1 < x0 or y1 < y0 or x1 >= M.width or y1 >= M.height then return nil end
        room.goal = {x0 = x0, y0 = y0, x1 = x1, y1 = y1}
    end
    room.objective, room.time, room.name = objective, time, name
    return room
end

function M.paint(room, index, tool, value)
    if index < 1 or index > M.width * M.height then return end
    if tool == "spawn" then
        room.spawn = index
        room.tiles[index] = 1
        room.objects[index] = nil
    elseif tool == "entity" then
        if index == room.spawn then return end
        room.objects[index] = value
        room.tiles[index] = 1
    elseif tool == "remove" then
        room.objects[index] = nil
    else
        if index == room.spawn and value ~= 1 then return end
        room.tiles[index] = value
        room.objects[index] = nil
    end
end

function M.cell_xy(index)
    return (index - 1) % M.width, math.floor((index - 1) / M.width)
end

-- Goal zone is the rectangle spanned by two cells (drag start and current cell).
function M.set_goal(room, anchor, index)
    local ax, ay = M.cell_xy(anchor)
    local bx, by = M.cell_xy(index)
    room.goal = {x0 = math.min(ax, bx), y0 = math.min(ay, by), x1 = math.max(ax, bx), y1 = math.max(ay, by)}
end

function M.in_goal(room, index)
    local g = room.goal
    if not g then return false end
    local x, y = M.cell_xy(index)
    return x >= g.x0 and x <= g.x1 and y >= g.y0 and y <= g.y1
end

-- Goal rectangle in room pixels as {x0, y0, x1, y1}, inclusive of whole cells.
function M.goal_rect(room)
    local g = room.goal
    return {g.x0 * M.cell, g.y0 * M.cell, (g.x1 + 1) * M.cell, (g.y1 + 1) * M.cell}
end

function M.position(index)
    return ((index - 1) % M.width) * M.cell + M.cell / 2,
        math.floor((index - 1) / M.width) * M.cell + M.cell / 2
end

-- Courses: exported rooms laid out left to right in the world, played in order.
M.room_spacing = 512 -- world pixels between room origins (room is 256 wide)
M.max_course = 12
-- Saved courses live in numbered slots (noita_rl.course_slot_<n>); settings.lua lists them.
M.course_slots = 9

function M.room_origin(position)
    return (position - 1) * M.room_spacing, 0
end

function M.parse_course(text)
    local ids = {}
    if type(text) ~= "string" then return ids end
    for id in string.gmatch(text, "[^,]+") do
        if string.match(id, "^[a-z][a-z0-9_]*$") and #ids < M.max_course then table.insert(ids, id) end
    end
    return ids
end

function M.course_text(ids)
    return table.concat(ids, ",")
end

-- Is the player (world x, y) inside the goal of a room placed at origin (ox, oy)?
function M.in_goal_world(room, ox, oy, x, y)
    if not room.goal then return false end
    local r = M.goal_rect(room)
    return x >= ox + r[1] and x <= ox + r[3] and y >= oy + r[2] and y <= oy + r[4]
end

function M.outside(ox, oy, x, y)
    return x < ox - 32 or x > ox + M.width * M.cell + 32 or y < oy - 32 or y > oy + M.height * M.cell + 32
end

-- Scenario ids chosen in-game: lesson_01 .. lesson_99, wrapping around.
function M.step_name(name, delta)
    local n = tonumber(string.match(name, "^lesson_(%d%d)$"))
    if not n then return "lesson_01" end
    return string.format("lesson_%02d", (n - 1 + delta) % 99 + 1)
end

function M.max_steps(room)
    return M.time_limits[room.time] * 60
end

function M.counts(room)
    local enemies, gold = 0, 0
    for _, kind in pairs(room.objects) do
        if M.entities[kind].enemy then enemies = enemies + 1 end
        gold = gold + (M.entities[kind].gold or 0)
    end
    return enemies, gold
end

-- Returns nil when the room is a playable, scoreable task; otherwise a message.
function M.problem(room)
    local spawn = room.spawn
    if room.tiles[spawn] ~= 1 or spawn <= M.width or room.tiles[spawn - M.width] ~= 1 then
        return "Player spawn needs air in its cell and the cell above."
    end
    local enemies, gold = M.counts(room)
    local objective = M.objectives[room.objective].id
    if objective == "reach_goal" then
        if not room.goal then return "Reach goal needs a goal zone (use the Goal zone tool)." end
        if M.in_goal(room, spawn) then return "Player spawn is inside the goal zone." end
    elseif objective == "kill_all" and enemies == 0 then
        return "Kill all enemies needs at least one enemy."
    elseif objective == "collect_gold" and gold == 0 then
        return "Collect all gold needs at least one gold pickup."
    end
    return nil
end

function M.success_conditions(room)
    local enemies, gold = M.counts(room)
    local objective = M.objectives[room.objective].id
    if objective == "reach_goal" then
        return {{type = "reach_region", rect = M.goal_rect(room)}}
    elseif objective == "kill_all" then
        return {{type = "kill_tag", tag = "enemy", count = enemies}}
    elseif objective == "collect_gold" then
        return {{type = "collect_gold", gold = gold}}
    end
    -- The runtime checks timeout before success, so succeed one step earlier.
    return {{type = "survive_steps", steps = M.max_steps(room) - 1}}
end

-- Merge equal-material cells into rectangles: horizontal runs, then stack identical runs.
local function tile_rects(room)
    local rects, open = {}, {}
    for y = 0, M.height - 1 do
        local runs, x = {}, 0
        while x < M.width do
            local material = room.tiles[y * M.width + x + 1]
            local start = x
            while x < M.width and room.tiles[y * M.width + x + 1] == material do x = x + 1 end
            if material ~= 1 then
                local key = start .. ":" .. x .. ":" .. material
                local rect = open[key]
                if rect and rect[4] == y then rect[4] = y + 1
                else rect = {start, y, x, y + 1, material}; table.insert(rects, rect) end
                runs[key] = rect
            end
        end
        open = runs
    end
    local tiles = {{material = "air", rect = {0, 0, M.width * M.cell, M.height * M.cell}}}
    for _, r in ipairs(rects) do
        table.insert(tiles, {material = M.materials[r[5]],
            rect = {r[1] * M.cell, r[2] * M.cell, r[3] * M.cell, r[4] * M.cell}})
    end
    return tiles
end

M.rewards = {
    reach_goal = {per_step = -0.001, pickup_gold = 0.0, enemy_kill = 0.0, damage_taken = -0.2, goal_reached = 5.0},
    kill_all = {per_step = -0.001, pickup_gold = 0.0, enemy_kill = 1.0, damage_taken = -0.2, goal_reached = 3.0},
    collect_gold = {per_step = -0.001, pickup_gold = 0.02, enemy_kill = 0.0, damage_taken = -0.2, goal_reached = 3.0},
    survive = {per_step = 0.001, pickup_gold = 0.0, enemy_kill = 0.0, damage_taken = -0.5, goal_reached = 1.0},
}

-- Build a document matching schemas/scenario.schema.json.
function M.to_scenario(room)
    local objective = M.objectives[room.objective]
    local sx, sy = M.position(room.spawn)
    local entities = {}
    for index = 1, M.width * M.height do
        local kind = room.objects[index]
        if kind then
            local x, y = M.position(index)
            local entity = M.entities[kind]
            table.insert(entities, {entity = entity.path, x = x, y = y,
                tags = {entity.enemy and "rl_target" or "rl_pickup"}})
        end
    end
    return {
        schema_version = 1,
        id = room.name,
        name = room.name,
        description = "Made in the Room Editor. Objective: " .. objective.label .. ".",
        seed = M.seed,
        room = {
            width = M.width * M.cell, height = M.height * M.cell,
            origin = {x = M.origin.x, y = M.origin.y},
            tiles = tile_rects(room),
            spawns = {player = {x = sx, y = sy}, entities = entities},
        },
        player = {hp = 4, gold = 0, inventory = {
            {entity = "data/entities/items/wand_level_01.xml", spells = {"LIGHT_BULLET"}},
        }},
        rewards = M.rewards[objective.id],
        termination = {max_steps = M.max_steps(room), success_conditions = M.success_conditions(room)},
    }
end

-- Minimal deterministic JSON writer for the scenario document (sorted keys).
local function is_array(value)
    if next(value) == nil then return true end
    return value[1] ~= nil
end

function M.json(value, indent)
    indent = indent or ""
    local kind = type(value)
    if kind == "string" then
        return '"' .. string.gsub(value, '[%c"\\]', function(c)
            return string.format("\\u%04x", string.byte(c))
        end) .. '"'
    elseif kind == "number" then
        if value == math.floor(value) then return string.format("%d", value) end
        return string.format("%.6g", value)
    elseif kind == "boolean" then
        return tostring(value)
    end
    local inner, parts = indent .. "  ", {}
    if is_array(value) then
        if #value == 0 then return "[]" end
        local simple = type(value[1]) ~= "table"
        for _, item in ipairs(value) do table.insert(parts, M.json(item, inner)) end
        if simple then return "[" .. table.concat(parts, ", ") .. "]" end
        return "[\n" .. inner .. table.concat(parts, ",\n" .. inner) .. "\n" .. indent .. "]"
    end
    local keys = {}
    for key in pairs(value) do table.insert(keys, key) end
    table.sort(keys)
    for _, key in ipairs(keys) do
        table.insert(parts, '"' .. key .. '": ' .. M.json(value[key], inner))
    end
    return "{\n" .. inner .. table.concat(parts, ",\n" .. inner) .. "\n" .. indent .. "}"
end
