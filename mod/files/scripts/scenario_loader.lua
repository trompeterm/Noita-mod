function noita_rl_load_active_scenario()
	local ok, scenario = pcall(function()
		return dofile_once(NOITA_RL_ACTIVE_MANIFEST)
	end)
	if not ok or scenario == nil then
		GamePrintImportant("Noita RL", "Active scenario manifest missing. Run `noita-rl compile --activate`.")
		return nil
	end
	return scenario
end
