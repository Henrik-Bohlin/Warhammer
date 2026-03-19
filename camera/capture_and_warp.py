#!/usr/bin/env python3
"""
A4 Paper Warping - Capture with RPi Camera, detect ArUco markers, warp to top-down view.
 
Usage: python3 capture_and_warp.py
 
Controls: SPACE=capture & save, q=quit
"""
 
import cv2
import numpy as np
import time
 
# Setup
DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)
DETECTOR = cv2.aruco.ArucoDetector(DICT)
CAPTURE_SIZE = (4608, 2592)  # max resolution of RPi camera 3
OUTPUT_SIZE = (3000, 2200)  # gameboard size 
 
 
class PiCamera2Wrapper:
    """Minimal wrapper to make picamera2 behave like cv2.VideoCapture."""
    def __init__(self, picam2):
        self.picam2 = picam2
 
    def read(self):
        try:
            frame = self.picam2.capture_array()
            if frame is None:
                return False, None
            return True, frame
        except Exception:
            return False, None
 
    def release(self):
        try:
            self.picam2.stop()
            self.picam2.close()
        except Exception:
            pass
 
 
def open_camera():
    """Try to open the camera via picamera2 (preferred) and fallback to OpenCV."""
    try:
        from picamera2 import Picamera2
        print("Trying picamera2...")
        picam2 = Picamera2()
        config = picam2.create_still_configuration(
            main={"format": 'RGB888', "size": CAPTURE_SIZE},
            controls={
                "Sharpness": 2.0,
            }
        )
        picam2.configure(config)
        picam2.start()
        time.sleep(2)
        print("Opened camera via picamera2")
        return PiCamera2Wrapper(picam2)
    except Exception as e:
        print(f"picamera2 unavailable or failed: {e}")
 
    print("Falling back to OpenCV VideoCapture...")
    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
    if not cap.isOpened():
        print("Error: Could not open camera")
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_SIZE[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_SIZE[1])
    return cap
 
 
cap = open_camera()
if cap is None:
    exit(1)
 
warped = None     # Most recent warped frame (updated every frame when markers visible)
captured = None   # Frozen frame set when SPACE is pressed
 
retry_no_frame = 0
printed = False
while True:
    ret, frame = cap.read()
    if not ret or frame is None:
        retry_no_frame += 1
        if retry_no_frame == 1:
            print("Warning: could not read frame from camera, retrying...")
        if retry_no_frame > 30:
            print("Error: camera is not providing frames. Exiting.")
            break
        time.sleep(0.1)
        continue
    retry_no_frame = 0
 
    # Detect markers
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = DETECTOR.detectMarkers(gray)
 
    display = frame.copy()
 
    if ids is not None and len(ids) == 4:
        # Get marker centers
        marker_data = {}
        for mid, corner in zip(ids.flatten(), corners):
            pts = corner[0]
            cx, cy = int(np.mean(pts[:, 0])), int(np.mean(pts[:, 1]))
            marker_data[mid] = {"center": (cx, cy), "corners": pts}

        if not printed:
            for mid, data in marker_data.items():
                pts = data['corners']
                for i, pt in enumerate(pts):
                    print(f"Marker ID {mid}, corner index {i}: ({int(pt[0])}, {int(pt[1])})")
            printed = True

        sorted_y = sorted(marker_data.items(), key=lambda x: x[1]['center'][1])
        tl_id = min(sorted_y[:2], key=lambda x: x[1]['center'][0])[0]
        tr_id = max(sorted_y[:2], key=lambda x: x[1]['center'][0])[0]
        bl_id = min(sorted_y[2:], key=lambda x: x[1]['center'][0])[0]
        br_id = max(sorted_y[2:], key=lambda x: x[1]['center'][0])[0]

        tl = marker_data[tl_id]['corners'][3]  # BR corner of TL marker
        tr = marker_data[tr_id]['corners'][0]  # BL corner of TR marker
        bl = marker_data[bl_id]['corners'][2]  # TR corner of BL marker
        br = marker_data[br_id]['corners'][1]  # TL corner of BR marker
 
        src = np.array([tl, tr, bl, br], dtype=np.float32)
        dst = np.array([[0,0], [OUTPUT_SIZE[0],0], [0,OUTPUT_SIZE[1]], OUTPUT_SIZE], dtype=np.float32)
 
        M = cv2.getPerspectiveTransform(src, dst)
        warped = cv2.warpPerspective(frame, M, OUTPUT_SIZE, flags=cv2.INTER_LANCZOS4)
 
        # Draw markers on display
        for pt in [tl, tr, bl, br]:
            cv2.circle(display, (int(pt[0]), int(pt[1])), 5, (0, 255, 0), -1)

        cv2.putText(display, "✓ Detected - SPACE to capture", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    else:
        count = len(ids) if ids is not None else 0
        cv2.putText(display, f"Found {count}/4 markers", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
 
    cv2.imshow("Camera", display)
 
    if warped is not None:
        cv2.imshow("Warped", warped)
 
    # Keys
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord(' '):  # SPACE - capture, save, and exit
        if warped is not None:
            captured = warped.copy()
            filename = f"warped_{cv2.getTickCount()}.jpg"
            cv2.imwrite(filename, captured)
            print(f"✓ Captured and saved as {filename}")
            break  # Exit the loop after successful save
        else:
            print("No warped image available yet — make sure all 4 markers are visible")
 
cap.release()
cv2.destroyAllWindows()
