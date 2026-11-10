dofile_once("data/scripts/gun/procedural/gun_action_utils.lua")

local function noita_rl_clear_inventory(player_entity, inventory)
	local inventory_items = EntityGetAllChildren(inventory)
	if inventory_items == nil then
		return
	end
	for _, item_entity in ipairs(inventory_items) do
		GameKillInventoryItem(player_entity, item_entity)
	end
end

local function noita_rl_find_quick_inventory(player_entity)
	local children = EntityGetAllChildren(player_entity)
	if children == nil then
		return nil
	end
	for _, child in ipairs(children) do
		if EntityGetName(child) == "inventory_quick" then
			return child
		end
	end
	return nil
end

local function noita_rl_hash_string(value)
	local hash = 0
	for i = 1, #value do
		hash = (hash * 131 + string.byte(value, i)) % 4294967296
	end
	return hash
end

local function noita_rl_add_spells_to_wand(wand_entity, spells)
	if spells == nil or #spells == 0 then
		return
	end
	for _, action_id in ipairs(spells) do
		AddGunAction(wand_entity, action_id)
	end
end

function noita_rl_apply_loadout(player_entity, scenario)
	if scenario == nil then
		return
	end

	local wallet = 0
	edit_component(player_entity, "WalletComponent", function(comp, vars)
		vars.money = scenario.player.gold
		wallet = vars.money
	end)

	edit_component(player_entity, "DamageModelComponent", function(comp, vars)
		vars.max_hp = scenario.player.hp
		vars.hp = scenario.player.hp
	end)

	local inventory = noita_rl_find_quick_inventory(player_entity)
	if inventory == nil then
		return
	end
	noita_rl_clear_inventory(player_entity, inventory)

	for _, item in ipairs(scenario.player.inventory) do
		local ent = EntityLoad(item.entity, 0, 0)
		if ent ~= nil then
			noita_rl_add_spells_to_wand(ent, item.spells)
			GamePickUpInventoryItem(player_entity, ent, false)
		end
	end
end

function noita_rl_collect_inventory_slots(player_entity)
	local slots = {}
	for i = 1, 10 do
		slots[i] = { occupied = 0, item_kind = 0, filename_hash = 0, wand_capacity = 0, spell_count = 0, spell0_id = 0 }
	end

	local inventory = noita_rl_find_quick_inventory(player_entity)
	if inventory == nil then
		return slots
	end
	local items = EntityGetAllChildren(inventory)
	if items == nil then
		return slots
	end

	for index, item in ipairs(items) do
		if index > 10 then
			break
		end
		local filename = EntityGetFilename(item) or ""
		local kind = 0
		if EntityHasTag(item, "wand") then
			kind = 1
		elseif EntityHasTag(item, "item_pickup") then
			kind = 2
		end
		local spell_count = 0
		local spell0_id = 0
		local capacity = 0
		local ability = EntityGetFirstComponentIncludingDisabled(item, "AbilityComponent")
		if ability ~= nil then
			capacity = ComponentGetValue2(ability, "slot_count") or 0
			local actions = EntityGetComponent(item, "ItemActionComponent")
			if actions ~= nil then
				spell_count = #actions
				if spell_count > 0 then
					spell0_id = ComponentGetValue2(actions[1], "mActionId") or 0
				end
			end
		end
		slots[index] = {
			occupied = 1,
			item_kind = kind,
			filename_hash = noita_rl_hash_string(filename),
			wand_capacity = capacity,
			spell_count = spell_count,
			spell0_id = spell0_id,
		}
	end
	return slots
end
