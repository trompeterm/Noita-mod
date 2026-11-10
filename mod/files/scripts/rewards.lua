g_noita_rl_reward_state = {
	last_hp = nil,
	last_gold = 0,
	alive_enemies = 0,
	kill_total = 0,
}

function noita_rl_rewards_reset(scenario, player_entity)
	g_noita_rl_reward_state.last_hp = nil
	g_noita_rl_reward_state.last_gold = 0
	g_noita_rl_reward_state.kill_total = 0
	GlobalsSetValue("noita_rl_kill_count", "0")
	local alive = 0
	local enemies = EntityGetWithTag("enemy")
	if enemies ~= nil then
		for _, ent in ipairs(enemies) do
			if EntityGetHealth(ent) > 0 then
				alive = alive + 1
			end
		end
	end
	g_noita_rl_reward_state.alive_enemies = alive
	local state = noita_rl_collect_player_state(player_entity)
	g_noita_rl_reward_state.last_hp = state.hp
	g_noita_rl_reward_state.last_gold = state.gold
end

function noita_rl_rewards_update(scenario, player_entity, step_count)
	local rewards = scenario.rewards
	local total = rewards.per_step or 0
	local state = noita_rl_collect_player_state(player_entity)

	if g_noita_rl_reward_state.last_hp ~= nil and state.hp < g_noita_rl_reward_state.last_hp then
		total = total + (rewards.damage_taken or 0)
	end
	if state.gold > g_noita_rl_reward_state.last_gold then
		total = total + (rewards.pickup_gold or 0) * (state.gold - g_noita_rl_reward_state.last_gold)
	end

	local enemies = EntityGetWithTag("enemy")
	local alive = 0
	if enemies ~= nil then
		for _, ent in ipairs(enemies) do
			if EntityGetHealth(ent) > 0 then
				alive = alive + 1
			end
		end
	end
	if alive < g_noita_rl_reward_state.alive_enemies then
		local kills = g_noita_rl_reward_state.alive_enemies - alive
		total = total + (rewards.enemy_kill or 0) * kills
		g_noita_rl_reward_state.kill_total = g_noita_rl_reward_state.kill_total + kills
		GlobalsSetValue("noita_rl_kill_count", tostring(g_noita_rl_reward_state.kill_total))
	end
	g_noita_rl_reward_state.alive_enemies = alive

	g_noita_rl_reward_state.last_hp = state.hp
	g_noita_rl_reward_state.last_gold = state.gold

	return total
end
