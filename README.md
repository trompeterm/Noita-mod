# Noita RL

Windows-first toolkit for training agents in configurable Noita rooms:

- JSON scenario and curriculum schemas with validation
- Scenario compiler that emits Noita pixel scenes and Lua manifests
- `noita_rl` game mode mod with structured telemetry overlay
- Gymnasium environment with external capture/input bridge

## Quick start

```powershell
cd C:\Users\kwaterskip\Research\Noita\Noita-mod
uv sync
uv run noita-rl validate examples/scenarios/movement_basics.json
uv run noita-rl compile examples/scenarios/movement_basics.json --activate
uv run noita-rl install-mod
```

### Enable the game mode in Noita

Game modes only appear after the mod is **enabled** and the game has restarted with that mod active:

1. From the title screen, open **Mods** and check **Noita RL**.
2. Click **Restart with enabled mods active** (do not only back out to the main menu).
3. Open **New Game** and use **left / right** (or the on-screen arrows) to cycle game modes until **Noita RL** appears. It is a carousel slot beside the default new game, not a separate menu.

If you still only see the mod in the Mods list, confirm `mods/noita_rl/mod.xml` contains `is_game_mode="1"` and rerun `uv run noita-rl install-mod`.

Launch Noita with the mode above selected, then run training:

```python
from pathlib import Path
from noita_rl.env import NoitaRLEnv

env = NoitaRLEnv(
    curriculum_path=Path("examples/curricula/starter.json"),
    auto_launch=False,  # set True to let Python launch Noita
)
obs, info = env.reset()
obs, reward, terminated, truncated, info = env.step(1)
env.close()
```

## Scenario authoring

Scenarios live in [`examples/scenarios/`](examples/scenarios/). Each file defines:

- room geometry (`tiles`, dimensions, origin)
- spawn points for player and entities
- player loadout (HP, gold, wand entities, spell actions)
- reward terms and termination conditions

Validate and compile:

```powershell
uv run noita-rl validate examples/scenarios/combat_arena.json
uv run noita-rl compile examples/scenarios/combat_arena.json --activate
uv run noita-rl preview examples/scenarios/combat_arena.json
```

`--activate` copies the compiled manifest into `mod/files/build/active/` for the game mode to load.

## Curriculum

Curricula in [`examples/curricula/`](examples/curricula/) sequence weighted scenario pools by stage. Stages advance or regress using rolling success rates.

## Observation and control bridge

The mod renders a machine-readable grayscale strip in the top-left corner each frame. Python captures the client window, decodes the strip, and exposes:

- `pixels`: RGB framebuffer (`expected_width` x `expected_height`)
- structured player state, inventory/wand summaries, events, reward deltas, terminal flags

Actions are discrete (move, jump, fire, kick, use, item swap). The Windows input adapter holds movement/fire keys across `action_repeat` frames.

## Environment variables

| Variable | Default |
|----------|---------|
| `NOITA_RL_NOITA_EXE` | Steam `noita.exe` path |
| `NOITA_RL_MOD_INSTALL` | `Noita/mods/noita_rl` |
| `NOITA_RL_ACTION_REPEAT` | `4` |

## Tests

```powershell
uv run pytest
```

Opt-in game integration (launches Noita):

```powershell
uv run pytest -m game
```

## Limitations

- Windows-first capture/input adapters (`mss`, `pywin32`)
- No in-engine frame stepping; Python synchronizes on `GameGetFrameNum()`
- Start the **Noita RL** game mode manually unless `auto_launch=True`
- Workshop uploads cannot rely on unrestricted Lua filesystem APIs
