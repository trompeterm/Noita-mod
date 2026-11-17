from __future__ import annotations

import ctypes

import numpy as np

from noita_rl.platform.base import FrameCapture, WindowInfo

PW_CLIENTONLY = 1
PW_RENDERFULLCONTENT = 2  # Windows 8.1+: also captures DirectX/OpenGL content


class MssFrameCapture(FrameCapture):
    """Copy the window's area of the screen. Only works while Noita is in front."""

    def capture(self, window: WindowInfo) -> np.ndarray:
        import mss

        region = {
            "left": window.left,
            "top": window.top,
            "width": window.width,
            "height": window.height,
        }
        with mss.mss() as grabber:
            shot = grabber.grab(region)
            frame = np.asarray(shot)
            return frame[:, :, 2::-1].copy()  # BGRA -> RGB


class PrintWindowCapture(FrameCapture):
    """Ask Windows for the window's own contents, even when other windows cover it.

    A minimized window draws nothing, so Noita must stay open (it may be behind other
    windows). Returns RGB, H x W x 3, of the client area.
    """

    def capture(self, window: WindowInfo) -> np.ndarray:
        import win32gui
        import win32ui

        hwnd = window.hwnd
        _, _, width, height = win32gui.GetClientRect(hwnd)
        if width <= 0 or height <= 0:
            raise ValueError("Noita's window is minimized: it must stay open (behind other windows is fine)")
        window_dc = win32gui.GetWindowDC(hwnd)
        source = win32ui.CreateDCFromHandle(window_dc)
        memory = source.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        try:
            bitmap.CreateCompatibleBitmap(source, width, height)
            memory.SelectObject(bitmap)
            ok = ctypes.windll.user32.PrintWindow(hwnd, memory.GetSafeHdc(), PW_CLIENTONLY | PW_RENDERFULLCONTENT)
            if not ok:
                raise ValueError("PrintWindow failed for Noita's window")
            raw = np.frombuffer(bitmap.GetBitmapBits(True), dtype=np.uint8).reshape(height, width, 4)
            return raw[:, :, 2::-1].copy()  # BGRA -> RGB
        finally:
            win32gui.DeleteObject(bitmap.GetHandle())
            memory.DeleteDC()
            source.DeleteDC()
            win32gui.ReleaseDC(hwnd, window_dc)
