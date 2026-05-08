#!/usr/bin/env python3
"""
Warp a static board image using ArUco markers.
Automatically tries multiple dictionaries and detector parameters.

Usage: python3 warp_image.py [input_image]
       python3 warp_image.py              # defaults to spelplan1.png
"""

import sys
import os
import cv2
import numpy as np

OUTPUT_SIZE = (3000, 2200)  # 30:22 aspect ratio to match full board including rails

ARUCO_DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)

# Detector parameter presets from strict → permissive
PARAM_PRESETS = [
    dict(win_min=3,  win_max=23, win_step=10, poly_acc=0.05, min_perim=0.02),
    dict(win_min=3,  win_max=53, win_step=10, poly_acc=0.05, min_perim=0.01),
    dict(win_min=3,  win_max=53, win_step=4,  poly_acc=0.08, min_perim=0.01),
    dict(win_min=5,  win_max=73, win_step=4,  poly_acc=0.10, min_perim=0.005),
    dict(win_min=3,  win_max=99, win_step=4,  poly_acc=0.12, min_perim=0.005),
]


def make_params(win_min, win_max, win_step, poly_acc, min_perim):
    p = cv2.aruco.DetectorParameters()
    p.adaptiveThreshWinSizeMin = win_min
    p.adaptiveThreshWinSizeMax = win_max
    p.adaptiveThreshWinSizeStep = win_step
    p.polygonalApproxAccuracyRate = poly_acc
    p.minMarkerPerimeterRate = min_perim
    return p


def detect_all_four(frame):
    """Try every parameter preset × preprocessing combo; return first hit of 4."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    images = [("original", gray), ("clahe", clahe.apply(gray))]

    best = (0, None, None, "none")  # (count, corners, ids, description)

    for preset in PARAM_PRESETS:
        params = make_params(**preset)
        detector = cv2.aruco.ArucoDetector(ARUCO_DICT, params)
        for img_name, img in images:
            corners, ids, _ = detector.detectMarkers(img)
            count = len(ids) if ids is not None else 0
            if count > best[0]:
                desc = f"win_max={preset['win_max']} / {img_name}"
                best = (count, corners, ids, desc)
            if count == 4:
                return corners, ids, desc

    return best[1], best[2], best[3]


input_path = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.path.join(os.path.dirname(__file__), "spelplannya.jpg")
)

frame = cv2.imread(input_path)
if frame is None:
    print(f"Error: could not load '{input_path}'")
    sys.exit(1)

frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
print(f"Loaded '{input_path}' ({frame.shape[1]}x{frame.shape[0]}) — rotated 90° CCW")
print("Searching for ArUco markers across dictionaries and detector settings…")

corners, ids, config_desc = detect_all_four(frame)

count = len(ids) if ids is not None else 0
print(f"Best result: {count}/4 markers  [{config_desc}]")

if count != 4:
    print(f"Error: need exactly 4 markers to warp — only found {count}.")
    print("Tips:")
    print("  • Make sure all 4 markers are fully visible and not blurry")
    print("  • Try better lighting or a higher-resolution photo")
    sys.exit(1)

marker_data = {}
for mid, corner in zip(ids.flatten(), corners):
    pts = corner[0]
    cx, cy = int(np.mean(pts[:, 0])), int(np.mean(pts[:, 1]))
    marker_data[mid] = {"center": (cx, cy), "corners": pts}
    print(f"  Marker ID {mid}: center ({cx}, {cy})")

sorted_y = sorted(marker_data.items(), key=lambda x: x[1]["center"][1])
tl_id = min(sorted_y[:2], key=lambda x: x[1]["center"][0])[0]
tr_id = max(sorted_y[:2], key=lambda x: x[1]["center"][0])[0]
bl_id = min(sorted_y[2:], key=lambda x: x[1]["center"][0])[0]
br_id = max(sorted_y[2:], key=lambda x: x[1]["center"][0])[0]
print(f"  Assigned: TL={tl_id}  TR={tr_id}  BL={bl_id}  BR={br_id}")

tl = marker_data[tl_id]["corners"][3]  # BR corner of TL marker
tr = marker_data[tr_id]["corners"][0]  # BL corner of TR marker
bl = marker_data[bl_id]["corners"][2]  # TR corner of BL marker
br = marker_data[br_id]["corners"][1]  # TL corner of BR marker

src = np.array([tl, tr, bl, br], dtype=np.float32)
dst = np.array([[0, 0], [OUTPUT_SIZE[0], 0], [0, OUTPUT_SIZE[1]], OUTPUT_SIZE], dtype=np.float32)

M = cv2.getPerspectiveTransform(src, dst)
warped = cv2.warpPerspective(frame, M, OUTPUT_SIZE, flags=cv2.INTER_LANCZOS4)

stem = os.path.splitext(os.path.basename(input_path))[0]
out_path = os.path.join(os.path.dirname(input_path), f"{stem}_warped.jpg")
cv2.imwrite(out_path, warped)
print(f"✓ Saved warped image as '{out_path}'")

cv2.imshow("Warped", warped)
print("Press any key to close.")
cv2.waitKey(0)
cv2.destroyAllWindows()
