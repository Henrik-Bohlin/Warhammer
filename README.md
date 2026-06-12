# Warhammer Movement Tool

A digital tool for tracking model movement and reachable areas on a
Warhammer Kill Team board. The project consists of two parts:

- **`gui/`** – the Pygame app used during play. Lets you pick a map, place
  models, and see their reachable movement area (including dash/charge).
- **`camera/`** – scripts for turning a photo of the physical board into a
  flat, top-down image (using ArUco markers) that can be used as the map
  background in the GUI.

## Requirements

- Python 3.10+
- [Pygame](https://www.pygame.org/)
- [Shapely](https://shapely.readthedocs.io/)
- [NumPy](https://numpy.org/)
- [OpenCV](https://opencv.org/) (`opencv-contrib-python`, needed for the
  ArUco marker detection in `camera/`)

Install everything with:

```bash
pip install pygame shapely numpy opencv-contrib-python
```

## Running the movement tool

From the project root, run:

```bash
python3 gui/gui.py
```

1. Select a map layout (e.g. Tomb World, Volkus).
2. Select your model's movement distance (in inches).
3. Click on the board to place a model and see its reach area.
4. Controls:
   - **Click** – place/move the model
   - **Ctrl+Click** – measure and draw a path to a point within reach
   - **D** – toggle Dash
   - **C** – toggle Charge
   - **M** – change the movement budget
   - **L** – change the map
   - **ESC** – reset the current model's position
   - **Q** – quit

## Capturing a board map (`camera/`)

These scripts warp a photo of the physical board into a flat top-down image
using the four ArUco markers placed at its corners. The resulting image can
be used as a `background_image` for a map layout in `gui/maps.py`.

- **`warp_image.py`** – for photos taken with a **mobile phone camera**
  (or any existing image file). It tries multiple detector settings to find
  the four markers and saves a warped output image.

  ```bash
  python3 camera/warp_image.py path/to/photo.jpg
  ```

  If no path is given, it defaults to `volkov.jpg` in the `camera/` folder.
  The result is saved alongside the input as `<name>_warped.jpg`.

- **`capture_and_warp.py`** – for a **Raspberry Pi camera module** (via
  `picamera2`, falling back to a regular OpenCV-compatible webcam). It shows
  a live preview, continuously detects the markers, and lets you capture a
  warped snapshot.

  ```bash
  python3 camera/capture_and_warp.py
  ```

  Controls:
  - **SPACE** – capture and save the current warped view, then exit
  - **Q** – quit without saving

Captured/warped images (`.png`, `.jpg`, `.jpeg`) saved in `camera/` are
ignored by Git, since they are generated locally and tend to be large.
