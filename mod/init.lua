dofile_once("data/scripts/lib/utilities.lua")
dofile_once("mods/noita_rl/files/scripts/constants.lua")
dofile_once("mods/noita_rl/files/scripts/runtime.lua")

function OnMagicNumbersAndWorldSeedInitialized()
	noita_rl_bootstrap_seed()
end

function OnWorldInitialized()
	noita_rl_on_world_initialized()
end

function OnPlayerSpawned(player_entity)
	noita_rl_on_player_spawned(player_entity)
end

function OnWorldPostUpdate()
	noita_rl_on_world_post_update()
end

function OnPlayerDied(player_entity)
	noita_rl_on_player_died(player_entity)
end
