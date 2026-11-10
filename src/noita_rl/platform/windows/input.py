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


class WindowsInputController(InputController):
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
