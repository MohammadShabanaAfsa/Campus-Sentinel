"""
CameraManager — centralized video capture with automatic reconnect, shared
by every module that opens a camera stream.

Each camera opens its OWN configured source (its `rtsp_url` in the DB) and
stays on it: a failed read retries that same source after a short delay.
Silently swapping to a different physical device on failure is disabled by
default (`enable_fallback=False`) — for a multi-camera deployment, showing
one camera's label over a different camera's footage is actively misleading,
not a helpful recovery. Pass `enable_fallback=True` to opt a specific camera
back into "fall back to the local webcam" behavior if that's genuinely
wanted for it.
"""
import time
import threading
from typing import Optional, Union

import cv2
from loguru import logger


def _parse_video_source(url: str) -> Union[str, int]:
    """Return a path string for file:// URLs, an int for local device indices, else the URL unchanged."""
    if url.startswith("file://"):
        return url[7:]
    if url.isdigit():
        return int(url)
    return url


class CameraManager:
    """
    Opens and maintains a single camera's video source with automatic
    reconnect. One instance per camera_id.
    """

    def __init__(
        self,
        camera_id: str,
        primary_source: Union[str, int],
        enable_fallback: bool = False,
        fallback_index: Optional[int] = None,
        reconnect_delay: Optional[float] = None,
    ):
        self.camera_id = camera_id
        self.primary_source = primary_source
        self.enable_fallback = enable_fallback

        if enable_fallback and fallback_index is None:
            from app.core.config import settings
            fallback_index = settings.CAMERA_FALLBACK_INDEX
        self.fallback_index = fallback_index

        if reconnect_delay is None:
            from app.core.config import settings
            reconnect_delay = settings.CAMERA_RECONNECT_DELAY_SECS
        self.reconnect_delay = reconnect_delay

        self._cap: Optional[cv2.VideoCapture] = None
        self._active_source: Optional[Union[str, int]] = None
        self._using_fallback: bool = False
        self._lock = threading.Lock()

    # ─── Public API ──────────────────────────────────────────────────────────

    @property
    def using_fallback(self) -> bool:
        return self._using_fallback

    @property
    def active_source(self) -> Optional[Union[str, int]]:
        return self._active_source

    def open(self) -> bool:
        """Open this camera's configured source. Only falls back to the local
        webcam if enable_fallback=True was set for this instance."""
        with self._lock:
            if self._try_open(self.primary_source, is_fallback=False):
                return True

            if not self.enable_fallback:
                logger.error(f"[{self.camera_id}] Cannot open configured source ({self.primary_source})")
                return False

            logger.warning(
                f"[{self.camera_id}] Configured source unreachable ({self.primary_source}); "
                f"falling back to local webcam (index {self.fallback_index})"
            )
            if self._try_open(self.fallback_index, is_fallback=True):
                return True

            logger.error(f"[{self.camera_id}] Both configured source and local webcam failed to open")
            return False

    def read(self):
        """Read a frame. Returns (ret, frame) — same contract as cv2.VideoCapture.read()."""
        if self._cap is None:
            return False, None
        return self._cap.read()

    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def reconnect(self) -> bool:
        """Call after a failed read. Retries this camera's own source after a
        short delay (and the local webcam too, only if enable_fallback=True)."""
        self._release_current()
        time.sleep(self.reconnect_delay)
        return self.open()

    def release(self):
        with self._lock:
            self._release_current()

    # ─── Internal ────────────────────────────────────────────────────────────

    def _try_open(self, source: Union[str, int], is_fallback: bool) -> bool:
        parsed = _parse_video_source(source) if isinstance(source, str) else source
        cap = cv2.VideoCapture(parsed)
        if cap.isOpened():
            self._release_current()
            self._cap = cap
            self._active_source = parsed
            self._using_fallback = is_fallback
            logger.info(f"[{self.camera_id}] Camera source opened: {parsed}")
            return True
        cap.release()
        return False

    def _release_current(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None
