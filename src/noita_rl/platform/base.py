from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class WindowInfo:
    hwnd: int
    left: int
    top: int
    width: int
    height: int
    title: str


class ProcessController(ABC):
    @abstractmethod
    def launch(self, executable: str, args: list[str] | None = None) -> None: ...

    @abstractmethod
    def is_running(self) -> bool: ...

    @abstractmethod
    def terminate(self) -> None: ...

    @abstractmethod
    def find_window(self, title_substring: str) -> WindowInfo | None: ...


class FrameCapture(ABC):
    @abstractmethod
    def capture(self, window: WindowInfo) -> np.ndarray: ...


class InputController(ABC):
    @abstractmethod
    def reset(self) -> None: ...

    @abstractmethod
    def apply_action(self, action_vector: np.ndarray, taps: list[str] | None = None) -> None: ...
