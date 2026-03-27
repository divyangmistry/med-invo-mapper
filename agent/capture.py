"""
capture.py — Document capture trigger layer.

Two modes (controlled by CAMERA_MODE env var):

  'folder' (dev / Windows)
    Watches INPUT_DIR for new image files using watchdog.
    When a .jpg / .jpeg / .png is dropped in, it fires the on_image callback,
    then moves the file to inputs/processed/ to avoid re-processing.

  'live' (prod / Linux)
    Opens the USB camera via OpenCV.
    Uses MOG2 background subtraction for motion detection.
    When the frame is still for SETTLE_SECONDS, fires the on_image callback
    with a captured high-res snapshot saved to a temp file.
"""
from __future__ import annotations

import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from config import Config

logger = logging.getLogger(__name__)

# Type alias: callback receives the path to a captured/dropped image
OnImageCallback = Callable[[Path], None]


# ─────────────────────────────────────────────────────────────────────────────
#  DROP-FOLDER MODE (dev)
# ─────────────────────────────────────────────────────────────────────────────

def _start_folder_watcher(on_image: OnImageCallback) -> None:
    """
    Block indefinitely watching INPUT_DIR for new image files.
    Moves processed files to inputs/processed/.
    """
    from watchdog.events import FileCreatedEvent, FileSystemEventHandler
    from watchdog.observers import Observer
    from watchdog.observers.polling import PollingObserver
    import os

    use_polling = os.getenv("WATCHDOG_USE_POLLING", "false").lower() == "true"
    processed_dir = Config.INPUT_DIR / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}

    class _Handler(FileSystemEventHandler):
        def on_created(self, event: FileCreatedEvent) -> None:
            if event.is_directory:
                return
            src = Path(event.src_path)
            # Skip hidden files, temp files, and any internal prefixes
            if src.name.startswith(("_", ".")):
                logger.debug("[FOLDER] Skipping temp/hidden file: %s", src.name)
                return
            if src.suffix.lower() not in valid_exts:
                return

            logger.info("[FOLDER] New file detected: %s", src.name)

            # Short wait to ensure file is fully written
            time.sleep(0.5)

            try:
                on_image(src)
            except Exception as exc:
                logger.error("[FOLDER] Processing failed for %s: %s", src.name, exc)
            finally:
                # Always move to processed/ (even on failure) to prevent loops
                dest = processed_dir / src.name
                try:
                    shutil.move(str(src), dest)
                    logger.info("[FOLDER] Moved to processed/: %s", src.name)
                except Exception as mv_exc:
                    logger.warning("[FOLDER] Could not move file: %s", mv_exc)

    observer = PollingObserver() if use_polling else Observer()
    if use_polling:
        logger.info("[FOLDER] Using POLLING observer (better for Windows Docker volumes)")
    observer.schedule(_Handler(), str(Config.INPUT_DIR), recursive=False)
    observer.start()
    logger.info("[FOLDER] Watching %s for new images …", Config.INPUT_DIR)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


# ─────────────────────────────────────────────────────────────────────────────
#  LIVE CAMERA MODE (prod / Linux)
# ─────────────────────────────────────────────────────────────────────────────

def _start_live_camera(on_image: OnImageCallback) -> None:
    """
    Open the USB camera and use background subtraction to detect when documents
    are placed in the frame. When the scene stays static for SETTLE_SECONDS,
    capture a high-res snapshot and pass it to on_image callback.
    """
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(Config.CAMERA_INDEX)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera index {Config.CAMERA_INDEX}. "
                           "Check CAMERA_INDEX and that the camera is connected.")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, Config.CAPTURE_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.CAPTURE_HEIGHT)
    cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    logger.info("[CAMERA] Opened camera %d at %dx%d", Config.CAMERA_INDEX, actual_w, actual_h)

    fgbg = cv2.createBackgroundSubtractorMOG2(history=200, varThreshold=40, detectShadows=False)

    settle_start: float | None = None
    motion_active = False
    COOLDOWN_SECONDS = 3.0       # Ignore re-triggers for this long after a capture

    last_capture_time = 0.0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                logger.warning("[CAMERA] Frame read failed — retrying …")
                time.sleep(0.1)
                continue

            # Background subtraction to detect motion
            fg_mask = fgbg.apply(frame)
            # Morphological cleanup
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
            motion_pixels = int(np.sum(fg_mask > 0))

            in_cooldown = (time.time() - last_capture_time) < COOLDOWN_SECONDS

            if motion_pixels > Config.MOTION_THRESHOLD:
                # Motion detected — hands placing document
                settle_start = None
                motion_active = True
                logger.debug("[CAMERA] Motion detected: %d px", motion_pixels)

            elif motion_active and not in_cooldown:
                # Scene has gone still after motion
                if settle_start is None:
                    settle_start = time.time()
                    logger.info("[CAMERA] Stillness started — waiting %.1fs to capture …", Config.SETTLE_SECONDS)

                elapsed_still = time.time() - settle_start
                if elapsed_still >= Config.SETTLE_SECONDS:
                    # CAPTURE EVENT
                    logger.info("[CAMERA] Capture triggered after %.1fs stillness", elapsed_still)
                    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                    snap_path = Config.INPUT_DIR / f"capture_{ts}.jpg"
                    cv2.imwrite(str(snap_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 97])
                    logger.info("[CAMERA] Snapshot saved: %s", snap_path.name)

                    try:
                        on_image(snap_path)
                    except Exception as exc:
                        logger.error("[CAMERA] Extraction error: %s", exc)

                    # Reset state
                    last_capture_time = time.time()
                    settle_start = None
                    motion_active = False
                    # Re-seed the background model with the current (document) frame
                    fgbg = cv2.createBackgroundSubtractorMOG2(history=200, varThreshold=40, detectShadows=False)
                    for _ in range(5):
                        cap.read()  # Flush frame buffer

    except KeyboardInterrupt:
        logger.info("[CAMERA] Shutdown requested.")
    finally:
        cap.release()
        logger.info("[CAMERA] Camera released.")


# ─────────────────────────────────────────────────────────────────────────────
#  Public Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def start_capture(on_image: OnImageCallback) -> None:
    """
    Start the capture loop in the configured mode.
    Blocks indefinitely (run in main thread or a dedicated thread).

    Parameters
    ----------
    on_image : callable(Path) → None
        Callback invoked with the Path to the image whenever a new document
        is detected (folder drop or camera capture).
    """
    mode = Config.CAMERA_MODE.lower()
    logger.info("Starting capture in mode: %s", mode.upper())

    if mode == "folder":
        _start_folder_watcher(on_image)
    elif mode == "live":
        _start_live_camera(on_image)
    else:
        raise ValueError(
            f"Unknown CAMERA_MODE={mode!r}. Choose 'folder' (dev) or 'live' (prod)."
        )
