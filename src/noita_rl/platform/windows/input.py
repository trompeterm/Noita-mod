from __future__ import annotations

import time

import numpy as np
import win32api
import win32con

from noita_rl.contracts import NoitaAction
from noita_rl.platform.base import InputController

VK_MAP = {
    "left": 0x41,  # A
    "right": 0x44,  # D
    "up": 0x57,  # W
    "down": 0x53,  # S
    "jump": 0x20,  # Space
    "fire": 0x01,  # mouse left via special handling
    "kick": 0x46,  # F
    "use": 0x45,  # E
}

TAP_ACTIONS = {
    NoitaAction.THROW: [0x71],  # V key rough stand-in, mapped below
    NoitaAction.NEXT_ITEM: [0x31],
    NoitaAction.PREV_ITEM: [0x32],
}


def agent_command_keys(room: int | None) -> list[tuple[int, bool]]:
    """Numpad key presses for an RL-agent-mode command: (virtual key, extended).

    ``room`` N restarts the episode in course room N (1-based); None restarts the current
    room. See mod/files/agent/agent.lua (read_commands).
    """
    keys: list[tuple[int, bool]] = []
    if room is not None:
        if not 1 <= room <= 999:
            raise ValueError(f"Room number out of range: {room}")
        keys += [(win32con.VK_NUMPAD0 + int(digit), False) for digit in str(room)]
    keys.append((win32con.VK_RETURN, True))  # numpad Enter is the extended Return key
    return keys


def tap_key(vk: int, extended: bool = False, hold_s: float = 0.035) -> None:
    """Press and release one key with its hardware scan code, which SDL (Noita) reads.

    Held for about two frames so the mod's once-per-frame check can't miss it.
    """
    scan = win32api.MapVirtualKey(vk, 0)
    flags = win32con.KEYEVENTF_EXTENDEDKEY if extended else 0
    win32api.keybd_event(vk, scan, flags, 0)
    time.sleep(hold_s)
    win32api.keybd_event(vk, scan, flags | win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(hold_s)


# Action keys for RL agent mode, by the names in agent_packet.BUTTONS: (virtual key, extended).
# Keep in sync with A.BUTTONS in mod/files/agent/agent.lua.
AGENT_KEYS = {
    "left": (0x41, False),  # A
    "right": (0x44, False),  # D
    "up": (0x57, False),  # W
    "down": (0x53, False),  # S
    "jump": (win32con.VK_SPACE, False),
    "fire": (0x4A, False),  # J
    "kick": (0x4B, False),  # K
    "interact": (0x45, False),  # E
    "aim_left": (win32con.VK_LEFT, True),
    "aim_right": (win32con.VK_RIGHT, True),
    "aim_up": (win32con.VK_UP, True),
    "aim_down": (win32con.VK_DOWN, True),
}


def key_lparam(vk: int, extended: bool, up: bool) -> int:
    """lParam of a WM_KEYDOWN / WM_KEYUP message: repeat 1, scan code, flags."""
    scan = win32api.MapVirtualKey(vk, 0)
    value = 1 | (scan << 16) | (int(extended) << 24)
    if up:
        value |= (1 << 30) | (1 << 31)
    return value


class NoitaWindowInput:
    """Send keys to Noita's window only, with window messages instead of real key presses.

    This works while Noita is in the background, and the keys never reach the app you are
    using. The mod reads them (RL agent mode) and moves the player itself.
    """

    def __init__(self, hwnd: int, post=None) -> None:
        import win32gui

        self.hwnd = hwnd
        self._post = post or win32gui.PostMessage
        self._held: set[str] = set()

    def _send(self, vk: int, extended: bool, up: bool) -> None:
        message = win32con.WM_KEYUP if up else win32con.WM_KEYDOWN
        self._post(self.hwnd, message, vk, key_lparam(vk, extended, up))

    def hold(self, buttons: set[str] | frozenset[str]) -> None:
        """Hold exactly these action keys until the next call.

        Held keys are re-sent every call, so a focus change in Noita (which resets its
        keyboard state) can't drop them for more than one step.
        """
        unknown = set(buttons) - AGENT_KEYS.keys()
        if unknown:
            raise ValueError(f"Unknown action keys: {sorted(unknown)}")
        for name in self._held - set(buttons):
            self._send(*AGENT_KEYS[name], up=True)
        for name in sorted(buttons):
            self._send(*AGENT_KEYS[name], up=False)
        self._held = set(buttons)

    def release_all(self) -> None:
        self.hold(set())

    def tap(self, vk: int, extended: bool = False, hold_s: float = 0.035) -> None:
        """Press and release a key, held for about two frames so the mod sees it."""
        self._send(vk, extended, up=False)
        time.sleep(hold_s)
        self._send(vk, extended, up=True)
        time.sleep(hold_s)

    def send_agent_command(self, room: int | None = None) -> None:
        for vk, extended in agent_command_keys(room):
            self.tap(vk, extended)


class WindowsInputController(InputController):
    def send_agent_command(self, room: int | None = None) -> None:
        for vk, extended in agent_command_keys(room):
            tap_key(vk, extended)

    def __init__(self) -> None:
        self._held: set[int] = set()

    def reset(self) -> None:
        for vk in list(self._held):
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
        self._held.clear()
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def apply_action(self, action_vector: np.ndarray, taps: list[str] | None = None) -> None:
        desired: set[int] = set()
        if action_vector[0]:
            desired.add(VK_MAP["left"])
        if action_vector[1]:
            desired.add(VK_MAP["right"])
        if action_vector[2]:
            desired.add(VK_MAP["up"])
        if action_vector[3]:
            desired.add(VK_MAP["down"])
        if action_vector[4]:
            desired.add(VK_MAP["jump"])
        if action_vector[6]:
            desired.add(VK_MAP["kick"])
        if action_vector[7]:
            desired.add(VK_MAP["use"])

        for vk in self._held - desired:
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
        for vk in desired - self._held:
            win32api.keybd_event(vk, 0, 0, 0)
        self._held = desired

        if action_vector[5]:
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        else:
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

        if taps:
            for vk in taps:
                win32api.keybd_event(vk, 0, 0, 0)
                time.sleep(0.01)
                win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
