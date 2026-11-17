dofile_once("data/scripts/lib/utilities.lua")
-- Own world generation, rather than stamping rooms into vanilla biomes.
-- Both modes use this empty world so vanilla terrain never interferes with a room.
-- Keep every vanilla biome registered: Noita's own scripts (e.g. biome_modifiers.lua)
-- edit them by filename at startup and crash the game if they are missing.
-- We only add one empty biome and paint the whole biome map with it.
local NOITA_RL_EMPTY_BIOME_COLOR = "ff0d2b4f" -- must match files/editor/biome_map.lua
ModMagicNumbersFileAdd("mods/noita_rl/files/editor/magic_numbers.xml")
local biomes = ModTextFileGetContent("data/biome/_biomes_all.xml")
biomes = string.gsub(biomes, "</BiomesToLoad>",
	'<Biome biome_filename="mods/noita_rl/files/editor/empty.xml" height_index="0" color="'
	.. NOITA_RL_EMPTY_BIOME_COLOR .. '"></Biome>\n</BiomesToLoad>')
ModTextFileSetContent("data/biome/_biomes_all.xml", biomes)
-- Same structure as the vanilla files, just with no scenes in them.
local NO_PIXEL_SCENES = "<PixelScenes>\n<PixelSceneFiles></PixelSceneFiles>\n"
	.. "<BackgroundImages></BackgroundImages>\n<mBufferedPixelScenes></mBufferedPixelScenes>\n</PixelScenes>\n"
ModTextFileSetContent("data/biome/_pixel_scenes.xml", NO_PIXEL_SCENES)
ModTextFileSetContent("data/biome/_pixel_scenes_newgame_plus.xml", NO_PIXEL_SCENES)
-- Crash breadcrumb (see editor.lua trace); cleared here so each run starts fresh.
ModSettingSet("noita_rl.debug_stage", "init")
ModSettingSet("noita_rl.debug_trace", "init")

-- All modes run in editor.lua: "editor" (default) opens the visual room editor, "human"
-- plays the course chosen in Mod settings, and "agent" plays it for the Python env with
-- the telemetry strip and sensors (files/agent/agent.lua).
dofile_once("mods/noita_rl/files/editor/editor.lua")

function OnMagicNumbersAndWorldSeedInitialized()
	SetWorldSeed(1337)
	AutosaveDisable()
end

function OnWorldPreUpdate()
	noita_editor_pre_update()
end

function OnPlayerSpawned(player_entity)
	noita_editor_spawn(player_entity)
end

function OnWorldPostUpdate()
	noita_editor_update()
end
