dofile("data/scripts/lib/mod_settings.lua")

local mod_id = "noita_rl"
mod_settings_version = 1

function ModSettingsUpdate(_init_scope)
end

function ModSettingsGuiCount()
	return 0
end

mod_settings =
{
	{
		category_id = "telemetry",
		friendly_name = "Telemetry",
		description = "Debug options for the RL bridge.",
		settings = {
			{
				id = "draw_overlay",
				ui_name = "Draw telemetry overlay",
				ui_description = "Render the machine-readable telemetry strip in the top-left corner.",
				value_default = true,
				scope = MOD_SETTING_SCOPE_RUNTIME,
			},
		},
	},
}
