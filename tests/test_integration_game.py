import pytest

from noita_rl.cli import cmd_smoke_test


@pytest.mark.game
def test_smoke_test_against_local_noita():
    code = cmd_smoke_test(argparse_namespace())
    assert code == 0


def argparse_namespace():
    import argparse

    return argparse.Namespace(scenario=None)
