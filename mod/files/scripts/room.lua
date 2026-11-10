function noita_rl_room_load(scenario)
	if scenario == nil then
		return
	end
	local origin = scenario.origin
	local room = scenario.room
	LoadPixelScene(
		room.materials,
		room.colors,
		origin.x,
		origin.y,
		"",
		true,
		true,
		room.color_to_material
	)
end

function noita_rl_room_place_player(player_entity, scenario)
	if scenario == nil then
		return
	end
	local origin = scenario.origin
	local spawn = scenario.player.spawn
	local x = origin.x + spawn.x
	local y = origin.y + spawn.y
	EntitySetTransform(player_entity, x, y)
end

function noita_rl_room_spawn_entities(scenario)
	if scenario == nil or scenario.entities == nil then
		return
	end
	local origin = scenario.origin
	for _, entity_data in ipairs(scenario.entities) do
		local x = origin.x + entity_data.x
		local y = origin.y + entity_data.y
		local ent = EntityLoad(entity_data.entity, x, y)
		if ent ~= nil and entity_data.tags ~= nil then
			for _, tag in ipairs(entity_data.tags) do
				EntityAddTag(ent, tag)
			end
		end
	end
end
