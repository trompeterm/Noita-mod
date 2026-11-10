import numpy as np

from noita_rl.actions import encode_action, repeated_action_vector
from noita_rl.contracts import NoitaAction


def test_encode_and_vectorize():
    action = encode_action("jump")
    assert action == NoitaAction.JUMP
    vec = repeated_action_vector(action)
    assert vec[4] == 1.0
    assert np.sum(vec) == 1.0
