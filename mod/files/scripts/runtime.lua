dofile_once("mods/noita_rl/files/scripts/scenario_loader.lua")
dofile_once("mods/noita_rl/files/scripts/room.lua")
dofile_once("mods/noita_rl/files/scripts/loadout.lua")
dofile_once("mods/noita_rl/files/scripts/observations.lua")
dofile_once("mods/noita_rl/files/scripts/rewards.lua")
dofile_once("mods/noita_rl/files/scripts/telemetry_draw.lua")

g_noita_rl = {
	scenario = nil,
	player = nil,
	episode = 0,
	step_count = 0,
	terminal = NOITA_RL_TERMINAL_ACTIVE,
	terminal_reason = 0,
	reward_delta = 0,
	event_flags = 0,
	gui = nil,
	spawned = false,
}

function noita_rl_bootstrap_seed()
	g_noita_rl.scenario = noita_rl_load_active_scenario()
	if g_noita_rl.scenario ~= nil then
		SetWorldSeed(g_noita_rl.scenario.seed)
		AutosaveDisable()
	end
end

function noita_rl_on_world_initialized()
	noita_rl_room_load(g_noita_rl.scenario)
end

function noita_rl_on_player_spawned(player_entity)
	if g_noita_rl.spawned then
		return
	end
	g_noita_rl.spawned = true
	g_noita_rl.player = player_entity
	g_noita_rl.episode = g_noita_rl.episode + 1
	g_noita_rl.step_count = 0
	g_noita_rl.terminal = NOITA_RL_TERMINAL_ACTIVE
	g_noita_rl.terminal_reason = 0

	noita_rl_room_place_player(player_entity, g_noita_rl.scenario)
	noita_rl_apply_loadout(player_entity, g_noita_rl.scenario)
	noita_rl_room_spawn_entities(g_noita_rl.scenario)
	noita_rl_rewards_reset(g_noita_rl.scenario, player_entity)
end

function noita_rl_on_world_post_update()
	if g_noita_rl.scenario == nil or g_noita_rl.player == nil then
		return
	end
	if g_noita_rl.terminal ~= NOITA_RL_TERMINAL_ACTIVE then
		noita_rl_draw_telemetry(g_noita_rl)
		return
	end

	g_noita_rl.step_count = g_noita_rl.step_count + 1
	g_noita_rl.reward_delta = noita_rl_rewards_update(g_noita_rl.scenario, g_noita_rl.player, g_noita_rl.step_count)
	g_noita_rl.event_flags = noita_rl_collect_event_flags(g_noita_rl.player)

	if noita_rl_check_timeout(g_noita_rl.scenario, g_noita_rl.step_count) then
		g_noita_rl.terminal = NOITA_RL_TERMINAL_TIMEOUT
		g_noita_rl.terminal_reason = 1
	elseif noita_rl_check_success(g_noita_rl.scenario, g_noita_rl.player, g_noita_rl.step_count) then
		g_noita_rl.terminal = NOITA_RL_TERMINAL_SUCCESS
		g_noita_rl.terminal_reason = 2
	end

	noita_rl_draw_telemetry(g_noita_rl)
end

function noita_rl_on_player_died(player_entity)
	g_noita_rl.terminal = NOITA_RL_TERMINAL_DEATH
	g_noita_rl.terminal_reason = 3
	g_noita_rl.reward_delta = g_noita_rl.reward_delta + (g_noita_rl.scenario.rewards.damage_taken or 0)
end
