from __future__ import annotations

import numpy as np

from noita_rl.platform.base import FrameCapture, WindowInfo


class MssFrameCapture(FrameCapture):
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
            return frame[:, :, :3].copy()
