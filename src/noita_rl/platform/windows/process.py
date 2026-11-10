from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass

import win32gui

from noita_rl.platform.base import ProcessController, WindowInfo


@dataclass(slots=True)
class WindowsProcessController(ProcessController):
    executable: str
    args: list[str]
    _process: subprocess.Popen | None = None

    def launch(self, executable: str | None = None, args: list[str] | None = None) -> None:
        if self._process and self.is_running():
            return
        cmd = [executable or self.executable, *(args or self.args)]
        self._process = subprocess.Popen(cmd)

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def terminate(self) -> None:
        if self._process and self.is_running():
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None

    def find_window(self, title_substring: str) -> WindowInfo | None:
        matches: list[tuple[int, str]] = []

        def callback(hwnd: int, _: int) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if title_substring.lower() in title.lower():
                matches.append((hwnd, title))

        win32gui.EnumWindows(callback, 0)
        if not matches:
            return None
        hwnd, title = matches[0]
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        return WindowInfo(
            hwnd=hwnd,
            left=left,
            top=top,
            width=right - left,
            height=bottom - top,
            title=title,
        )

    def wait_for_window(self, title_substring: str, timeout_s: float = 60.0) -> WindowInfo:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            window = self.find_window(title_substring)
            if window is not None:
                return window
            time.sleep(0.25)
        raise TimeoutError(f"Timed out waiting for window containing '{title_substring}'")
