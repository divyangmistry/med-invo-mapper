"""
test_camera.py — Standalone camera integration test.

Run this NATIVELY on Windows (not inside Docker) to verify OpenCV can
access the USB camera BEFORE integrating it into the Docker live mode.

Usage
-----
    # Install deps first (in your local venv or system Python):
    pip install opencv-python numpy

    # Run:
    python tests/test_camera.py

    # With a specific camera index:
    python tests/test_camera.py --index 1

What it tests
-------------
  ✓ OpenCV can open the camera at the given index
  ✓ Camera reports the configured resolution
  ✓ A live frame can be read without error
  ✓ Motion detection (MOG2) produces a valid mask
  ✓ A snapshot can be saved to disk

The script will open a LIVE PREVIEW WINDOW for 10 seconds so you can
visually verify the camera feed and framing. Press 'q' to quit early.
"""
import argparse
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser(description="Camera integration test")
parser.add_argument("--index", type=int, default=0, help="Camera index (default: 0)")
parser.add_argument("--width", type=int, default=1920, help="Capture width (default: 1920)")
parser.add_argument("--height", type=int, default=1080, help="Capture height (default: 1080)")
parser.add_argument("--no-preview", action="store_true", help="Skip live preview window")
args = parser.parse_args()

PASS = "✅"
FAIL = "❌"
results = []


def check(name: str, condition: bool, detail: str = "") -> None:
    icon = PASS if condition else FAIL
    msg = f"  {icon}  {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    results.append(condition)


print("\n" + "=" * 60)
print("  Med-Invo Mapper — Camera Integration Test")
print(f"  Camera Index : {args.index}")
print(f"  Resolution   : {args.width}x{args.height}")
print("=" * 60)

# ── Import OpenCV ─────────────────────────────────────────────
print("\n[1/6] OpenCV import")
try:
    import cv2
    import numpy as np
    check(f"OpenCV imported successfully", True, f"version={cv2.__version__}")
except ImportError as e:
    check("OpenCV imported", False, str(e))
    print("  ⚠️  Install: pip install opencv-python numpy")
    sys.exit(1)

# ── Open camera ───────────────────────────────────────────────
print("\n[2/6] Camera open")
cap = cv2.VideoCapture(args.index)
try:
    check("Camera opened", cap.isOpened(),
          "Try a different --index value" if not cap.isOpened() else f"index={args.index}")
    if not cap.isOpened():
        print("  ⚠️  Camera not found. Possible fixes:")
        print("     - Check that the USB camera is plugged in")
        print("     - Try --index 1 or --index 2")
        print("     - Check Device Manager (Windows) for camera status")
        sys.exit(1)
except Exception as e:
    check("Camera opened", False, str(e))
    sys.exit(1)

# ── Set resolution ────────────────────────────────────────────
print("\n[3/6] Resolution configuration")
cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
check("Resolution set", actual_w > 0 and actual_h > 0, f"actual={actual_w}x{actual_h}")
if actual_w != args.width or actual_h != args.height:
    print(f"  ⚠️  Camera doesn't support {args.width}x{args.height}, "
          f"using {actual_w}x{actual_h} instead. Update CAPTURE_WIDTH/HEIGHT in .env.dev")

# ── Read a frame ──────────────────────────────────────────────
print("\n[4/6] Frame capture")
ret, frame = cap.read()
check("Frame read succeeds", ret)
if ret:
    check("Frame has expected shape", len(frame.shape) == 3,
          f"shape={frame.shape}")
    check("Frame is not black", frame.mean() > 5.0,
          f"mean_brightness={frame.mean():.1f}")
else:
    print("  ⚠️  Could not read frame. Camera may need a moment — retrying …")
    time.sleep(1)
    ret, frame = cap.read()
    check("Frame read on retry", ret)

# ── Motion detection smoke test ───────────────────────────────
print("\n[5/6] Motion detection (MOG2 background subtractor)")
try:
    fgbg = cv2.createBackgroundSubtractorMOG2(history=50, varThreshold=40, detectShadows=False)
    # Feed 5 frames to seed the background model
    for _ in range(5):
        ret2, f = cap.read()
        if ret2:
            fgbg.apply(f)
    ret3, test_frame = cap.read()
    if ret3:
        mask = fgbg.apply(test_frame)
        check("MOG2 mask is a valid numpy array", isinstance(mask, np.ndarray),
              f"dtype={mask.dtype} shape={mask.shape}")
        check("Mask pixels are binary (0 or 255)", set(np.unique(mask)).issubset({0, 255}))
except Exception as e:
    check("MOG2 smoke test", False, str(e))

# ── Save snapshot ─────────────────────────────────────────────
print("\n[6/6] Snapshot save")
snap_path = Path(__file__).parent / "sample_images" / "camera_test_snapshot.jpg"
snap_path.parent.mkdir(parents=True, exist_ok=True)
try:
    ret4, snap_frame = cap.read()
    if ret4:
        saved = cv2.imwrite(str(snap_path), snap_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        check("Snapshot saved", saved, str(snap_path))
        if saved:
            size_kb = snap_path.stat().st_size // 1024
            check("Snapshot file size > 10 KB", size_kb > 10, f"{size_kb} KB")
except Exception as e:
    check("Snapshot saved", False, str(e))

# ── Live preview ──────────────────────────────────────────────
if not args.no_preview:
    print("\n  📷  Opening live preview for 10 seconds… (press 'q' to quit early)")
    deadline = time.time() + 10
    while time.time() < deadline:
        ret5, frame5 = cap.read()
        if not ret5:
            break
        # Overlay info text
        cv2.putText(frame5, f"Camera {args.index} | {actual_w}x{actual_h} | Press Q to quit",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imshow("Med-Invo Camera Test", frame5)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cv2.destroyAllWindows()
    print("  Preview closed.")

cap.release()

# ── Summary ───────────────────────────────────────────────────
passed = sum(results)
total = len(results)
print("\n" + "=" * 60)
if passed == total:
    print(f"  ✅  ALL {total} CAMERA TESTS PASSED")
    print(f"\n  📌  Next step: Update .env.prod with:")
    print(f"          CAMERA_MODE=live")
    print(f"          CAMERA_INDEX={args.index}")
    print(f"          CAPTURE_WIDTH={actual_w}")
    print(f"          CAPTURE_HEIGHT={actual_h}")
else:
    print(f"  ❌  {total - passed} / {total} TESTS FAILED")
    print("  ⚠️  Resolve camera issues before enabling live mode in Docker.")
print("=" * 60 + "\n")
sys.exit(0 if passed == total else 1)
