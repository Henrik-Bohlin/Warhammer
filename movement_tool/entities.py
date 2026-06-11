from shapely.geometry import Point, box
from shapely.ops import unary_union

# Physical Tomb World grid constants (match maps.py)
_TW_CELL_IN = 97.0 / 25.4
_TW_BOARD_W_IN = 27.68
_TW_BOARD_H_IN = 23.868
_TW_COLS = 7
_TW_ROWS = 6
_TW_MARGIN_X_IN = (_TW_BOARD_W_IN - _TW_COLS * _TW_CELL_IN) / 2
_TW_MARGIN_Y_IN = (_TW_BOARD_H_IN - _TW_ROWS * _TW_CELL_IN) / 2


class Terrain:
    def __init__(self, width=32, height=20, thickness=0.5):
        self.board_width = width
        self.board_height = height
        self.linethickness = thickness

        self.walls_list = self.walls()
        self.combined_walls = unary_union(self.walls_list)

        self.wall_points = [
            Point(c)
            for wall in self.walls_list
            for c in list(wall.exterior.coords)[:-1]
        ]

    def walls(self):
        lt = self.linethickness
        w = self.board_width
        h = self.board_height
        walls_list = []

        # Border walls
        walls_list.append(box(0, 0, w, lt))
        walls_list.append(box(0, h - lt, w, h))
        walls_list.append(box(0, 0, lt, h))
        walls_list.append(box(w - lt, 0, w, h))

        return walls_list


class TombWorldTerrain(Terrain):
    """Walls centred on the 9.7 cm grid lines per the physical Tomb World board."""

    def walls(self):
        lt = self.linethickness
        w = self.board_width
        h = self.board_height
        C = _TW_CELL_IN
        MX = _TW_MARGIN_X_IN
        MY = _TW_MARGIN_Y_IN
        HT = lt / 2

        def gx(c):
            return MX + c * C

        def gy(r):
            return MY + r * C

        return [
            # Border walls
            box(0, 0, w, lt),
            box(0, h - lt, w, h),
            box(0, 0, lt, h),
            box(w - lt, 0, w, h),
            # Two vertical walls from horizontal bar (row 3) up to top board edge (cols 3 & 4)
            box(gx(3) - HT, gy(3), gx(3) + HT, h - lt),
            box(gx(4) - HT, gy(3), gx(4) + HT, h - lt),
            # Main horizontal wall at row 3, spanning cols 1–6 (extended ±HT at ends to meet vertical walls flush)
            box(gx(1) - HT, gy(3) - HT, gx(6) + HT, gy(3) + HT),
            # Left stub at col 1: from bottom board edge up to horizontal bar
            box(gx(1) - HT, lt, gx(1) + HT, gy(3)),
            # Right wall at col 6: from bottom board edge up to row 5 (top row left open)
            box(gx(6) - HT, lt, gx(6) + HT, gy(5)),
            # Short horizontal at row 1, half a cell wider on each side of cols 3–4
            box(gx(3) - C / 2, gy(1) - HT, gx(4) + C / 2, gy(1) + HT),
        ]


class VolkusTerrain(Terrain):
    """Volkus map walls. Board 30"×22", 1"×1" grid, no margins.
    Rows are counted 1–22 from the top; rb(n) = h - n in board coords."""

    def walls(self):
        lt = self.linethickness
        blt = self.board_height / 1080  # ≈ 1 screen pixel at WIN_H=1080
        w = self.board_width   # 30
        h = self.board_height  # 22

        def rb(n):
            return h - n

        return [
            # Border walls – 1 pixel thin
            box(0,       0,       w,       blt),
            box(0,       h - blt, w,       h),
            box(0,       0,       blt,     h),
            box(w - blt, 0,       w,       h),
            # F – col 6 / row 7 from top: L-shape at left spawn-zone boundary
            box(4.7,       rb(7),        6.0,        rb(7) + lt),   # horizontal T
            box(6.0,       rb(7),        6.0 + lt,   rb(7) + 4.6),  # vertical R

            # Small box – 8×6, R at col 9, T at y=14
            box(9.0,           14.0,          9.0 + lt,   20.0),         # left vertical,  R at col 9
            box(9.0,           14.0,          17.0,       14.0 + lt),    # bottom horiz,   T at y=14
            box(17.0 - lt,     14.0,          17.0,       20.0),         # right vertical, L at col 17
            box(9.0,           20.0 - lt,     17.0,       20.0),         # top horiz,      B at y=20

            # J – Γ shape (upside-down L): T at y=3, horizontal 0.3 below y=10 gridline
            box(14.0,       3.0,         14.0 + lt,  8.7),    # vertical,   R at col 14, 5.7" tall
            box(14.0,       8.7 - lt,    18.8,       8.7),    # horizontal, top at y=8.7 (0.3 off y=9)

            # E – ⌐ shape: corner at (col 24, y=10) — 1 row below centre, 6" from right edge
            box(24.0 - lt,  4.5,         24.0,   10.0),    # vertical,   L at col 24, 5.5" tall
            box(21.1,       10.0 - lt,   24.0,   10.0),    # horizontal, B at y=10,   2.9" wide

            # C-area Γ-shape – right spawn boundary, L at col 24, B at y=19
            box(24.0 - lt,  12.5,        24.0,   19.0),    # vertical,   L at col 24, 6.5" tall
            box(19.6,       19.0 - lt,   24.0,   19.0),    # horizontal, B at y=19,   4.4" wide

            # Main outer box (lower-left) – 8×8, shifted 2 right, rows from bottom
            box(3.0,        3.0,         3.0 + lt,   11.0),    # left vertical,    R at col 3
            box(3.0,        3.0,         11.0,        3.0 + lt), # bottom horizontal, T at y=3
            box(11.0 - lt,  3.0,         11.0,        11.0),    # right vertical,   L at col 11
            box(3.0,        11.0 - lt,   11.0,        11.0),    # top horizontal,   B at y=11
        ]


class Model:
    def __init__(self, x, y, name="Model", base_size_mm=32):
        self.name = name
        self.x = x
        self.y = y
        self.base_radius = (base_size_mm / 25.4) / 2  # Convert mm to inches

    def position(self):
        return Point(self.x, self.y)

    def draw(self, axes):
        base_circle = self.position().buffer(self.base_radius)
        bx, by = base_circle.exterior.xy

        # Draw the base
        axes.fill(bx, by, color="#d31c2b", alpha=1, zorder=10)
