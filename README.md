# Noita Room Editor

An in-game visual room editor for Noita. Paint a room, place the player and enemies,
save a blueprint, and play-test it without editing JSON or running a compiler.

## Install and start

Requires Noita on Windows. For the installation CLI and development tools, use Python
3.12+ and uv:

```powershell
cd C:\git\ai_club\Noita-mod
uv sync
uv run noita-rl install-mod
```

For a different Steam library:

```powershell
uv run noita-rl install-mod --dest "D:\SteamLibrary\steamapps\common\Noita\mods\noita_rl"
```

Alternatively, copy the contents of `mod/` into Noita's `mods/noita_rl/` directory.
Keep that folder name: the scripts use it to locate their assets. No Python process
is needed while playing. The CLI installer replaces the destination mod folder.

1. Close and reopen Noita after installing this update.
2. In **Mods**, enable **Noita Room Editor**. Disable other world-generation mods.
   You don't need to allow unsafe mods.
3. Click **Restart with enabled mods active**.
4. In **New Game**, use the arrows to select **Room Editor**, then start a fresh run.
   An existing run still has its previously generated terrain.

## Editing

The canvas is a 32 x 20 grid of 8-pixel tiles (256 x 160 world pixels).
It starts with a steel enclosure and an air interior.

- Select a material on the left, then click or drag on the canvas to paint.
- Right-click or right-drag to erase terrain and objects.
- Select **Player spawn**, then click a cell to move the **P** marker. Leave air in
  that cell and the cell above it so the player can fit.
- Select **Slime shooter**, **Zombie**, or **Gold pickup**, then click to place a
  spawn. Markers are S, Z, and $. **Remove spawn** removes an object without
  changing the terrain. Each cell holds at most one object.
- **Undo / Redo** restores changes, including New room and Load. A drag is one undo
  operation. Up to 50 undo operations are kept during a run.
- **New room** creates a fresh enclosure. Undo can recover the previous blueprint.
- **Slot 1/2/3** selects a slot; **Save** writes it and **Load** restores it.
  Saving replaces the selected slot. Slots and the autosaved working draft persist
  in Noita's mod settings across new games and mod reinstalls. They are local to
  your Noita settings, not files inside this repository. A completed paint stroke,
  loading, undoing, and entering play-test save the working draft.

### The task: what the agent must learn

Each room is a curriculum lesson, so it carries a task, not just terrain:

- **Goal zone**: select it, then drag a rectangle on the canvas (cells marked **G**).
  Right-click with this tool to remove the zone.
- **Objective** (click to cycle): *Reach goal zone*, *Kill all enemies*,
  *Collect all gold*, or *Survive until time runs out*.
- **Time limit** (click to cycle): 10, 20, 30, 60, or 120 seconds. This becomes the
  episode's `max_steps` (60 steps per second).
- **Scenario id** (the **<** and **>** buttons): `lesson_01` to `lesson_99`. This is the file name
  and the curriculum id. (There is no text box: Noita warns that its text input can
  break outside the mod settings menu.)

Play test and Export refuse rooms that can't be scored. For example, a goal
objective needs a goal zone that doesn't contain the spawn, and kill-all needs an enemy.

## Play testing

**Play test** reconstructs the terrain from your blueprint, spawns the objects,
places the player, and supplies a starting wand. Normal game controls work here.
The editor protects the player and disables their controls while the canvas is open.

A play test is scored the same way an agent episode is. The HUD shows the time left.
The test ends with **SUCCESS** when the objective is met, **TIMEOUT** when the limit
runs out, or **FAILED** if you die or leave the room. Use this to check that a lesson
is solvable before an agent trains on it.

Click **Return to editor** to edit again. Each new test rebuilds the room and removes
tracked spawns plus nearby enemies, projectiles and loose pickups. Terrain damage
and liquid movement during a test never change the blueprint.

The world generator uses a custom air-only biome across the biome map and removes
vanilla fixed pixel scenes. There are no procedural jungle rooms, terrain
vegetation, or biome enemy spawns around the room. This replaces the previous
approach of stamping a small cage into the regular game world.

## Courses: several rooms in one map

A course is an ordered list of exported rooms, up to 12. **Play course** places every
room in the world in a row, 512 pixels apart: room 1 sits where the editor canvas is,
room 2 starts at x = 512, and so on. You start in room 1. Each room is scored like a
play test:

- **Success** teleports you to the next room with a fresh loadout, full HP and its own timer.
- **Failure** (death, timeout or leaving the room) rebuilds that room and restarts it.
  The HUD counts your attempts.
- After the last room you see **COURSE COMPLETE** with the total time. **Skip room**
  and **Return to editor** are always available.

To build one, use the **COURSE** row at the bottom of the editor:

1. **Export for RL** makes a room available to courses. Exporting again updates it.
2. Pick an exported room with **<** / **>** and click **Add to course**.
   **Remove last** removes the last room. The same room can appear more than once.
3. Click **Play course**.

The course is saved as the `noita_rl.course` mod setting. Each room's editable layout is
saved as `noita_rl.room_<id>`, next to its scenario export. Rooms exported before
courses existed are recovered automatically, if the draft or a save slot still matches
the export exactly. Otherwise, load the room and export it again.

## From the editor to a curriculum

1. Pick the room's **Scenario id** with **<** / **>**, then click **Export for RL**.
   The mod is sandboxed and can't write files, so it saves the room as a mod setting,
   `noita_rl.export_<id>`. Noita stores mod settings in
   `%USERPROFILE%\AppData\LocalLow\Nolla_Games_Noita\save00\mod_settings.bin`, the
   same file that holds your draft and slots. The saved value is a scenario that
   matches `schemas/scenario.schema.json`. You don't need to hand-write any JSON.
   Exporting the same id again replaces the earlier export.
2. Copy the exported rooms into the repo. Each one is validated first:

   ```powershell
   uv run noita-rl pull-rooms              # -> examples/scenarios/<id>.json
   uv run noita-rl pull-rooms --overwrite  # replace an existing id after edits
   ```

   If `pull-rooms` doesn't see a room you just exported, close Noita (it saves mod
   settings on exit) and run it again. Exports persist across runs and reinstalls.
   `uv run noita-rl debug-status` lists everything the mod has saved.
3. Reference the ids from a curriculum such as `examples/curricula/starter.json`.
   Order lessons from easy to hard: walk to a goal, then jump a lava pit, then kill
   one zombie, and so on.
4. To run a room for the agent, open **Mods > Noita Room Editor > Mod settings**,
   set **Mode** to **RL agent**, and start a new game. The mod then loads the active
   compiled scenario (`noita-rl compile --activate`) and emits telemetry. It uses
   the same empty world as the editor, so vanilla terrain, vegetation and biome
   enemies can't interfere. Switch **Mode** back to **Room editor** to edit.

Exported rooms use origin (0, 0), seed 1337, a 4 HP player with a starter wand, and
default rewards for each objective. To tune rewards or the loadout for a lesson, edit
the pulled JSON in `examples/scenarios/`.

## Scope and limitations

This version is a bounded room editor, not an infinite-world paint tool. It offers
eight materials, three entity types and one goal rectangle per room. Editing happens
on a blueprint canvas; liquids and combat simulate when testing. There is no
in-game import of JSON, and no reward or loadout editor yet. The blueprint is
durable, but undo history is per run. Other mods that replace world generation or
player behavior may interfere.

## Implementation and verification

- `mod/init.lua`: world-generation overrides; picks editor or RL-agent mode.
- `mod/settings.lua`: the **Mode** setting.
- `mod/files/editor/model.lua`: blueprint operations, validated save format (`NRE2`,
  still reads `NRE1`), task validation and scenario JSON export.
- `mod/files/editor/editor.lua`: GUI, persistence, controls, scored play tests and export.
- `mod/files/editor/biome_map.lua`, `biomes.xml`, `empty.xml`: isolated empty world.
- `mod/files/editor/terrain/`: native Noita material-color tile scenes.
- `mod/files/editor/ui/`: canvas swatches.

```powershell
uv run pytest
uv run ruff check src tests
```

Editor tests run the Lua 5.1 code with mocked Noita APIs to verify blueprint
round-trips, invalid saves, painting, player spawn protection, play/reset, save/load,
fatal-damage recovery, goal zones, scored play tests, and export. Exported rooms are
checked against the JSON schema and compiled to verify the materials pixel by pixel.
`pull-rooms` and export-preserving `install-mod` are tested too. They also check Lua syntax and terrain asset colors.
These tests do not replace an in-game check of rendering, biome generation,
physics, and input on your Noita build.
