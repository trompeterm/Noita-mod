local bit = bit

local function noita_rl_put_u8(buffer, index, value)
	buffer[index] = bit.band(value, 0xFF)
	return index + 1
end

local function noita_rl_put_u16(buffer, index, value)
	buffer[index] = bit.band(value, 0xFF)
	buffer[index + 1] = bit.band(bit.rshift(value, 8), 0xFF)
	return index + 2
end

local function noita_rl_put_u32(buffer, index, value)
	buffer[index] = bit.band(value, 0xFF)
	buffer[index + 1] = bit.band(bit.rshift(value, 8), 0xFF)
	buffer[index + 2] = bit.band(bit.rshift(value, 16), 0xFF)
	buffer[index + 3] = bit.band(bit.rshift(value, 24), 0xFF)
	return index + 4
end

local function noita_rl_put_i32(buffer, index, value)
	if value < 0 then
		value = 4294967296 + value
	end
	return noita_rl_put_u32(buffer, index, value)
end

local function noita_rl_checksum(buffer, length_without_crc)
	local checksum = 0
	local i = 1
	while i <= length_without_crc do
		local b0 = buffer[i] or 0
		local b1 = buffer[i + 1] or 0
		local b2 = buffer[i + 2] or 0
		local b3 = buffer[i + 3] or 0
		local chunk = b0 + b1 * 256 + b2 * 65536 + b3 * 16777216
		checksum = bit.bxor(checksum, chunk)
		i = i + 4
	end
	return checksum
end

local function noita_rl_pack_row0(state, player_state, inventory_slots)
	local buffer = {}
	local index = 1
	index = noita_rl_put_u8(buffer, index, string.byte("N"))
	index = noita_rl_put_u8(buffer, index, string.byte("R"))
	index = noita_rl_put_u8(buffer, index, NOITA_RL_PROTOCOL_VERSION)
	index = noita_rl_put_u32(buffer, index, GameGetFrameNum())
	index = noita_rl_put_u32(buffer, index, state.episode)
	index = noita_rl_put_i32(buffer, index, math.floor(player_state.x))
	index = noita_rl_put_i32(buffer, index, math.floor(player_state.y))
	index = noita_rl_put_u16(buffer, index, math.floor(player_state.vx * 100))
	index = noita_rl_put_u16(buffer, index, math.floor(player_state.vy * 100))
	index = noita_rl_put_u16(buffer, index, math.floor(player_state.hp * 1000))
	index = noita_rl_put_u16(buffer, index, math.floor(player_state.max_hp * 1000))
	index = noita_rl_put_u32(buffer, index, player_state.gold)
	index = noita_rl_put_u8(buffer, index, player_state.active_slot)
	index = noita_rl_put_u8(buffer, index, state.terminal)
	index = noita_rl_put_u8(buffer, index, state.terminal_reason)
	index = noita_rl_put_i32(buffer, index, math.floor(state.reward_delta * 1000))
	index = noita_rl_put_u32(buffer, index, state.event_flags)
	index = noita_rl_put_u8(buffer, index, #inventory_slots)
	local checksum = noita_rl_checksum(buffer, 43)
	index = noita_rl_put_u32(buffer, index, checksum)
	return buffer
end

local function noita_rl_pack_inventory_row(inventory_slots)
	local buffer = {}
	local index = 1
	for i = 1, 10 do
		local slot = inventory_slots[i]
		if slot == nil then
			slot = { occupied = 0, item_kind = 0, filename_hash = 0, wand_capacity = 0, spell_count = 0, spell0_id = 0 }
		end
		index = noita_rl_put_u8(buffer, index, slot.occupied)
		index = noita_rl_put_u16(buffer, index, slot.item_kind)
		index = noita_rl_put_u16(buffer, index, slot.filename_hash % 65536)
		index = noita_rl_put_u16(buffer, index, slot.wand_capacity)
		index = noita_rl_put_u16(buffer, index, slot.spell_count)
		index = noita_rl_put_u16(buffer, index, slot.spell0_id)
	end
	return buffer
end

local function noita_rl_draw_rows(rows)
	if ModSettingGet("noita_rl.draw_overlay") == false then
		return
	end
	if g_noita_rl.gui == nil then
		g_noita_rl.gui = GuiCreate()
	end
	GuiStartFrame(g_noita_rl.gui)
	GuiZSet(g_noita_rl.gui, 1000)

	for row_index, row in ipairs(rows) do
		for col_index, value in ipairs(row) do
			local shade = (value % 256) / 255.0
			GuiColorSetForNextWidget(g_noita_rl.gui, shade, shade, shade, 1.0)
			GuiImageNinePiece(
				g_noita_rl.gui,
				row_index * 1000 + col_index,
				NOITA_RL_TELEMETRY_ORIGIN_X + (col_index - 1) * NOITA_RL_TELEMETRY_CELL,
				NOITA_RL_TELEMETRY_ORIGIN_Y + (row_index - 1) * NOITA_RL_TELEMETRY_CELL,
				NOITA_RL_TELEMETRY_CELL,
				NOITA_RL_TELEMETRY_CELL
			)
		end
	end
end

function noita_rl_draw_telemetry(state)
	if state.player == nil then
		return
	end
	local player_state = noita_rl_collect_player_state(state.player)
	local inventory_slots = noita_rl_collect_inventory_slots(state.player)
	local rows = {
		noita_rl_pack_row0(state, player_state, inventory_slots),
		noita_rl_pack_inventory_row(inventory_slots),
		{},
		{},
	}
	noita_rl_draw_rows(rows)
end
