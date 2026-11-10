from __future__ import annotations

import numpy as np

from noita_rl.contracts import ACTION_NAMES, DISCRETE_ACTION_COUNT, NoitaAction


def action_space():
    import gymnasium as gym

    return gym.spaces.Discrete(DISCRETE_ACTION_COUNT)


def encode_action(action: int | str | NoitaAction) -> NoitaAction:
    if isinstance(action, NoitaAction):
        return action
    if isinstance(action, str):
        normalized = action.strip().lower()
        if normalized not in ACTION_NAMES:
            raise ValueError(f"Unknown action '{action}'")
        return NoitaAction(ACTION_NAMES[normalized])
    value = int(action)
    if value < 0 or value >= DISCRETE_ACTION_COUNT:
        raise ValueError(f"Action index out of range: {value}")
    return NoitaAction(value)


def action_to_label(action: NoitaAction) -> str:
    return action.name.lower()


def repeated_action_vector(action: NoitaAction) -> np.ndarray:
    """Map semantic actions to held keyboard keys for the Windows input adapter."""

    vec = np.zeros(8, dtype=np.float32)
    if action == NoitaAction.LEFT:
        vec[0] = 1.0
    elif action == NoitaAction.RIGHT:
        vec[1] = 1.0
    elif action == NoitaAction.UP:
        vec[2] = 1.0
    elif action == NoitaAction.DOWN:
        vec[3] = 1.0
    elif action == NoitaAction.JUMP:
        vec[4] = 1.0
    elif action == NoitaAction.FIRE:
        vec[5] = 1.0
    elif action == NoitaAction.KICK:
        vec[6] = 1.0
    elif action == NoitaAction.USE:
        vec[7] = 1.0
    return vec
