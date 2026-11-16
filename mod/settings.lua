dofile("data/scripts/lib/mod_settings.lua")

-- Only "mode" is declared here. Blueprints are stored by the editor under private
-- ModSetting keys (noita_rl.editor_*), which mod_settings_update never touches.
local mod_id = "noita_rl"
mod_settings_version = 1
mod_settings = {
	{
		id = "mode",
		ui_name = "Mode",
		ui_description = "Room editor: build and export rooms.\nRL agent: run the active compiled scenario with telemetry.",
		value_default = "editor",
		values = { { "editor", "Room editor" }, { "agent", "RL agent" } },
		scope = MOD_SETTING_SCOPE_NEW_GAME,
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
