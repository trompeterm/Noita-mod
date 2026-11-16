-- Paint the whole world with the empty editor biome (registered in init.lua).
-- The colour must match NOITA_RL_EMPTY_BIOME_COLOR in mod/init.lua.
BiomeMapSetSize(70, 48)
for y = 0, 47 do
    for x = 0, 69 do
        BiomeMapSetPixel(x, y, 0xff0d2b4f)
    end
end
