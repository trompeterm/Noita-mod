dofile("data/scripts/lib/mod_settings.lua")

-- Declared settings: "mode" and "play_course". Rooms, courses and blueprints are stored
-- by the editor under private ModSetting keys (noita_rl.room_*, noita_rl.course_slot_*,
-- noita_rl.editor_*), which mod_settings_update never touches.
local mod_id = "noita_rl"
local COURSE_SLOTS = 9 -- keep in sync with EditorModel.course_slots

-- The saved course in a slot, as a list of room ids (empty if nothing is saved).
local function course_ids(slot)
	local ids = {}
	local text = ModSettingGet("noita_rl.course_slot_" .. slot)
	if type(text) == "string" then
		for id in string.gmatch(text, "[^,]+") do table.insert(ids, id) end
	end
	return ids
end

local function course_label(slot)
	local ids = course_ids(slot)
	if #ids == 0 then return "empty - save one from the editor's COURSE row" end
	local missing = 0
	for _, id in ipairs(ids) do
		if not ModSettingGet("noita_rl.room_" .. id) then missing = missing + 1 end
	end
	local text = table.concat(ids, " > ")
	if #text > 48 then text = string.sub(text, 1, 45) .. "..." end
	text = #ids .. " rooms: " .. text
	if missing > 0 then text = text .. "  (" .. missing .. " missing, export them again)" end
	return text
end

-- Click: next saved course. Right-click: previous. Empty slots are skipped unless all are empty.
local function course_ui(mod_id, gui, in_main_menu, im_id, setting)
	local key = mod_setting_get_id(mod_id, setting)
	local slot = tonumber(ModSettingGetNextValue(key)) or 1
	local clicked, right_clicked = GuiButton(gui, im_id, mod_setting_group_x_offset, 0,
		setting.ui_name .. ": " .. slot .. "  (" .. course_label(slot) .. ")")
	if clicked or right_clicked then
		local step = clicked and 1 or -1
		local next_slot = slot
		for _ = 1, COURSE_SLOTS do
			next_slot = (next_slot - 1 + step) % COURSE_SLOTS + 1
			if #course_ids(next_slot) > 0 then break end
		end
		ModSettingSetNextValue(key, tostring(next_slot), false)
	end
	mod_setting_tooltip(mod_id, gui, in_main_menu, setting)
end

mod_settings_version = 2
mod_settings = {
	{
		id = "mode",
		ui_name = "Mode",
		ui_description = "Room editor: build rooms and courses.\n"
			.. "Human: play the course chosen below, without the editor.\n"
			.. "RL agent: the Python agent drives the game.",
		value_default = "editor",
		values = { { "editor", "Room editor" }, { "human", "Human" }, { "agent", "RL agent" } },
		scope = MOD_SETTING_SCOPE_NEW_GAME,
	},
	{
		id = "play_course",
		ui_name = "Course to play",
		ui_description = "Saved course for Human and RL agent modes.\n"
			.. "Click for the next saved course, right-click for the previous one.",
		value_default = "1",
		ui_fn = course_ui,
		scope = MOD_SETTING_SCOPE_NEW_GAME,
	},
	{
		id = "agent_overlay",
		ui_name = "Agent overlay",
		ui_description = "RL agent mode: show the sensor readout, ray hits, goal and enemies.\n"
			.. "The telemetry strip Python reads is always drawn. Numpad * toggles this in game.",
		value_default = true,
		scope = MOD_SETTING_SCOPE_RUNTIME,
	},
}

function ModSettingsUpdate(init_scope)
	mod_settings_update(mod_id, mod_settings, init_scope)
end

function ModSettingsGuiCount()
	return mod_settings_gui_count(mod_id, mod_settings)
end

function ModSettingsGui(gui, in_main_menu)
	mod_settings_gui(mod_id, mod_settings, gui, in_main_menu)
end
