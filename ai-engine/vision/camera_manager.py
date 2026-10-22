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
from urllib.parse import urlsplit, urlunsplit
from typing import Optional, Union

import cv2
from loguru import logger


def safe_source(source) -> str:
    """Never expose camera passwords, query tokens, or URL fragments in logs."""
    value = str(source)
    try:
        parts = urlsplit(value)
        if parts.scheme and parts.netloc:
            host = parts.hostname or ""
            if ":" in host:
                host = f"[{host}]"
            authority = host + (f":{parts.port}" if parts.port else "")
            return urlunsplit((parts.scheme, authority, parts.path, "", ""))
        return value if value.isdigit() else "<local video source>"
    except ValueError:
        return "<invalid camera URL>"


def check_http_source(source: str) -> Optional[str]:
    """Connect and read response headers without downloading an endless MJPEG body."""
    import httpx
    try:
        with httpx.Client(timeout=1.5, trust_env=False, follow_redirects=True) as client:
            with client.stream("GET", source) as response:
                if response.status_code in (401, 403):
                    return "Authentication required"
                if response.status_code >= 400:
                    return f"Video source returned HTTP {response.status_code}"
        return None
    except httpx.TimeoutException:
        return "Camera source unreachable: connection timed out"
    except httpx.ConnectError as exc:
        reason = str(exc).lower()
        if "refused" in reason or "10061" in reason:
            return "Camera source unreachable: connection refused"
        if "timed out" in reason or "10060" in reason:
            return "Camera source unreachable: connection timed out"
        return "Camera source unreachable: host unreachable"
    except httpx.HTTPError:
        return "Failed to connect to video stream"


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
        self.last_error: Optional[str] = None
        self.reachable = False
        self.opened = False
        self._first_frame = None

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
                logger.warning(f"[Camera] {self.camera_id}: {self.last_error}")
                return False

            logger.warning(
                f"[{self.camera_id}] Configured source unreachable ({safe_source(self.primary_source)}); "
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
        if self._first_frame is not None:
            frame, self._first_frame = self._first_frame, None
            return True, frame
        ret, frame = self._cap.read()
        if not ret or frame is None:
            self.last_error = "No frames received"
        return ret, frame

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
        self.last_error = None
        self.reachable = False
        self.opened = False
        logger.info(f"[Camera] {self.camera_id}: attempting connection to {safe_source(source)}")
        network = isinstance(parsed, str) and parsed.startswith(("http://", "https://", "rtsp://"))
        if isinstance(parsed, str) and parsed.startswith(("http://", "https://")):
            self.last_error = check_http_source(parsed)
            if self.last_error:
                return False
            self.reachable = True
        # Network sources use FFmpeg with bounded open/read calls. Device 0
        # keeps its existing backend/driver behavior and never serves as fallback.
        cap = cv2.VideoCapture(
            parsed, cv2.CAP_FFMPEG,
            [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 1500, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 1500],
        ) if network else cv2.VideoCapture(parsed)
        if cap.isOpened():
            self.opened = True
            self.reachable = True
            first_frame = None
            if network:
                ret, first_frame = cap.read()
                if not ret or first_frame is None:
                    cap.release()
                    self.last_error = "No frames received"
                    return False
            self._release_current()
            self._cap = cap
            self._first_frame = first_frame
            self._active_source = parsed
            self._using_fallback = is_fallback
            self.reachable = True
            logger.info(f"[Camera] {self.camera_id}: source opened: {safe_source(parsed)}")
            return True
        cap.release()
        self.last_error = "Failed to open video stream"
        return False

    def _release_current(self):
        self._first_frame = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
