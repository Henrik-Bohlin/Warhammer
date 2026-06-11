import os
import sys
from dataclasses import dataclass, field
from typing import Callable, Optional

WIN_W, WIN_H = 1920, 1080
BASE_RADIUS = (32 / 25.4) / 2  # 32mm base in inches

_HERE = os.path.dirname(os.path.abspath(__file__))

_MOVEMENT_TOOL = os.path.join(_HERE, "..", "movement_tool")
if _MOVEMENT_TOOL not in sys.path:
    sys.path.insert(0, _MOVEMENT_TOOL)
from entities import TombWorldTerrain, VolkusTerrain

# Tombworld grid constants — 6×7 grid of 9.7 cm cells, equal margins derived from measured board dims.
_TW_CELL_MM = 97.0
_TW_COLS = 7
_TW_ROWS = 6
_TW_CELL_IN = _TW_CELL_MM / 25.4
_TW_BOARD_W_IN = 27.68      # measured physical board width in inches
_TW_BOARD_H_IN = 23.868     # measured physical board height in inches


@dataclass
class MapLayout:
    name: str
    width: float
    height: float
    line_thickness: float = 0.5
    terrain_factory: Optional[Callable] = None  # None = default Terrain class
    background_image: Optional[str] = None
    # Optional fixed grid (tombworld-style). None = fall back to 1" default grid.
    grid_cell_size: Optional[float] = None   # cell width/height in inches
    grid_cols: Optional[int] = None
    grid_rows: Optional[int] = None
    grid_color: tuple = (255, 255, 255, 130)  # RGBA


def display_config(layout: MapLayout):
    """Derive pixel-space constants from a MapLayout.
    Returns (scale, board_px_w, board_px_h, offset_x, offset_y).
    """
    scale = WIN_H / layout.height
    board_px_w = int(layout.width * scale)
    board_px_h = int(layout.height * scale)
    offset_x = (WIN_W - board_px_w) // 2
    offset_y = (WIN_H - board_px_h) // 2
    return scale, board_px_w, board_px_h, offset_x, offset_y


MAPS = {
    "tombworld1": MapLayout(
        name="Tomb World Map 1",
        width=_TW_BOARD_W_IN,
        height=_TW_BOARD_H_IN,
        line_thickness=0.2,
        terrain_factory=TombWorldTerrain,
        background_image=os.path.join(_HERE, "..", "camera", "TombWorldMap1.jpg"),
        grid_cell_size=_TW_CELL_IN,
        grid_cols=_TW_COLS,
        grid_rows=_TW_ROWS,
        grid_color=(0, 0, 0, 150),
    ),
    "volkus1": MapLayout(
        name="Volkus Map 1",
        width=30.0,
        height=22.0,
        line_thickness=0.2,
        terrain_factory=VolkusTerrain,
        background_image=os.path.join(_HERE, "..", "camera", "VolkusMap1.jpg"),
        grid_cell_size=1.0,
        grid_cols=30,
        grid_rows=22,
        grid_color=(0, 0, 0, 150),
    ),
}

MAP_ORDER = ["tombworld1", "volkus1"]
