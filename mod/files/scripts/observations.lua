function noita_rl_collect_player_state(player_entity)
	local x, y = EntityGetTransform(player_entity)
	local vx, vy = 0, 0
	local vel_comp = EntityGetFirstComponent(player_entity, "VelocityComponent")
	if vel_comp ~= nil then
		vx, vy = ComponentGetValue2(vel_comp, "mVelocity")
	end

	local hp = 0
	local max_hp = 0
	local damagemodels = EntityGetComponent(player_entity, "DamageModelComponent")
	if damagemodels ~= nil then
		hp = ComponentGetValue2(damagemodels[1], "hp")
		max_hp = ComponentGetValue2(damagemodels[1], "max_hp")
	end

	local gold = 0
	edit_component(player_entity, "WalletComponent", function(comp, vars)
		gold = vars.money or 0
	end)

	local active_slot = 0
	edit_component(player_entity, "Inventory2Component", function(comp, vars)
		active_slot = vars.mActiveItem or vars.mSavedActiveItemIndex or 0
	end)

	return {
		x = x,
		y = y,
		vx = vx,
		vy = vy,
		hp = hp,
		max_hp = max_hp,
		gold = gold,
		active_slot = active_slot,
	}
end

function noita_rl_collect_event_flags(player_entity)
	local flags = 0
	local x, y = EntityGetTransform(player_entity)
	local pickups = EntityGetInRadiusWithTag(x, y, 96, "item_pickup")
	if pickups ~= nil and #pickups > 0 then
		flags = flags + 1
	end
	local enemies = EntityGetInRadiusWithTag(x, y, 160, "enemy")
	if enemies ~= nil and #enemies > 0 then
		flags = flags + 2
	end
	return flags
end

function noita_rl_check_timeout(scenario, step_count)
	return step_count >= scenario.termination.max_steps
end

function noita_rl_check_success(scenario, player_entity, step_count)
	for _, condition in ipairs(scenario.termination.success_conditions) do
		if condition.type == "survive_steps" and step_count >= (condition.steps or 0) then
			return true
		end
		if condition.type == "reach_region" then
			local px, py = EntityGetTransform(player_entity)
			local origin = scenario.origin
			local rx, ry, rw, rh = condition.rect[1], condition.rect[2], condition.rect[3], condition.rect[4]
			if px >= origin.x + rx and px <= origin.x + rw and py >= origin.y + ry and py <= origin.y + rh then
				return true
			end
		end
		if condition.type == "collect_gold" then
			local gold = 0
			edit_component(player_entity, "WalletComponent", function(comp, vars)
				gold = vars.money or 0
			end)
			if gold >= (condition.gold or 0) then
				return true
			end
		end
		if condition.type == "kill_tag" then
			local needed = condition.count or 1
			local kills = tonumber(GlobalsGetValue("noita_rl_kill_count")) or 0
			if kills >= needed then
				return true
			end
		end
	end
	return false
end
