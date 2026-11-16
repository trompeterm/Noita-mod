-- Biome script for the empty editor world, structured like vanilla
-- data/scripts/biomes/boss_arena_top.lua. World generation may call any of these
-- spawn functions by name, so they all exist and intentionally spawn nothing.
CHEST_LEVEL = 1
dofile_once("data/scripts/director_helpers.lua")
dofile_once("data/scripts/biome_scripts.lua")

function spawn_small_enemies(x, y) end
function spawn_big_enemies(x, y) end
function spawn_items(x, y) end
function spawn_props(x, y) end
function spawn_props2(x, y) end
function spawn_props3(x, y) end
function spawn_lamp(x, y) end
function spawn_orb(x, y) end
function load_pixel_scene(x, y) end
function load_pixel_scene2(x, y) end
function spawn_unique_enemy(x, y) end
function spawn_ghostlamp(x, y) end
function spawn_candles(x, y) end
function spawn_potions(x, y) end
function spawn_wands(x, y) end
function spawn_portal(x, y) end
function spawn_end_portal(x, y) end
function spawn_vines(x, y) end
function spawn_trapwand(x, y) end
function spawn_bbqbox(x, y) end
function spawn_swing_puzzle_box(x, y) end
function spawn_swing_puzzle_target(x, y) end
function spawn_oiltank_puzzle(x, y) end
function spawn_receptacle(x, y) end
