from noita_rl.contracts import TerminalState
from noita_rl.telemetry.protocol import TelemetryPacket, pack_row0, unpack_row0


def test_row0_roundtrip():
    packet = TelemetryPacket(
        frame=120,
        episode=3,
        player_x=256.9,
        player_y=512.2,
        vel_x=1.25,
        vel_y=-0.5,
        hp=0.75,
        max_hp=1.25,
        gold=150,
        active_slot=2,
        terminal=TerminalState.ACTIVE,
        terminal_reason=0,
        reward=0.125,
        event_flags=3,
        inventory_slots=4,
        inventory=[],
    )
    row = pack_row0(packet)
    decoded = unpack_row0(row)
    assert decoded.frame == packet.frame
    assert decoded.episode == packet.episode
    assert abs(decoded.player_x - packet.player_x) < 1.0
    assert abs(decoded.reward - packet.reward) < 0.01
    assert decoded.inventory_slots == packet.inventory_slots
