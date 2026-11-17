from __future__ import annotations

import ctypes
import subprocess
import time
from dataclasses import dataclass
from pathlib import PureWindowsPath

import win32api
import win32con
import win32gui
import win32process

from noita_rl.platform.base import ProcessController, WindowInfo

NOITA_EXE = "noita.exe"


def make_dpi_aware() -> None:
    """Use physical pixels for window rectangles, matching what screen capture sees.

    Without this, display scaling (e.g. 125%) makes window coordinates and screenshots
    disagree, so the capture lands in the wrong place.
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor aware
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def window_exe(hwnd: int) -> str:
    """Executable file name (lower case) of the process that owns a window, or ""."""
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        try:
            return PureWindowsPath(win32process.GetModuleFileNameEx(handle, 0)).name.lower()
        finally:
            win32api.CloseHandle(handle)
    except Exception:  # noqa: BLE001 - access denied, process gone, ...
        return ""


def client_area(hwnd: int, title: str = "") -> WindowInfo:
    """The window's drawable area (no title bar or borders) in screen pixels."""
    _, _, width, height = win32gui.GetClientRect(hwnd)
    left, top = win32gui.ClientToScreen(hwnd, (0, 0))
    return WindowInfo(hwnd=hwnd, left=left, top=top, width=width, height=height, title=title)


def focus_window(hwnd: int, settle_s: float = 0.4) -> None:
    """Restore the window if minimized and bring it to the front (it then gets key presses)."""
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except win32gui.error:
        # Windows only lets the foreground process hand over focus; a tap of Alt
        # counts as user input and lifts that restriction.
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32gui.SetForegroundWindow(hwnd)
    time.sleep(settle_s)


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
        """Noita's game window: owned by noita.exe, never just any window whose title
        mentions Noita (a terminal or editor open in the Noita-mod folder would match)."""
        matches: list[tuple[int, str]] = []

        def callback(hwnd: int, _: int) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if title_substring.lower() in title.lower() and window_exe(hwnd) == NOITA_EXE:
                matches.append((hwnd, title))

        win32gui.EnumWindows(callback, 0)
        if not matches:
            return None
        hwnd, title = matches[0]
        return client_area(hwnd, title)

    def wait_for_window(self, title_substring: str, timeout_s: float = 60.0) -> WindowInfo:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            window = self.find_window(title_substring)
            if window is not None:
                return window
            time.sleep(0.25)
        raise TimeoutError(f"Timed out waiting for window containing '{title_substring}'")
