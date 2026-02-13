from entities import Terrain, Model
from navigation import PathFinder
import matplotlib.pyplot as plt
import math
import numpy as np
from shapely.geometry import Point, Polygon, box
from shapely.ops import nearest_points, unary_union


class Board:
    def __init__(self):
        # --- 1. Dimensions & Unit Constants ---
        self.board_width = 32
        self.board_height = 20
        self.linethickness = 0.5  # Matches Terrain defaults
        self.max_move = 6
        self.base_radius = (32 / 25.4) / 2  # 32mm base radius in inches
        self.visual_padding = 0.05

        # --- 2. Entity & Terrain Logic ---
        # We pass dimensions so Terrain knows where to draw the rails
        self.entities = Terrain(self.board_width, self.board_height, self.linethickness)
        self.combined_walls = self.entities.combined_walls

        # --- 3. Navigation & State Management ---
        self.current_model = None
        self.model_pos = None
        self.navigator = PathFinder(self)
        self.navigator.path_elements = []  # For Ctrl+Click lines
        self.navigator.reach_segments = []  # For fluid reach logic

        # --- 4. Pre-Calculated Geometry (RPi 5 Performance) ---
        # Defining the safe zone once prevents lag during clicks
        self.board_boundary = box(0, 0, self.board_width, self.board_height)
        self.legal_area = self.board_boundary.difference(
            self.combined_walls.buffer(self.base_radius + self.visual_padding)
        )

        # --- 5. GUI & Event Configuration ---
        self.window_frame, self.axes = plt.subplots(figsize=(16, 10))
        self.window_frame.canvas.manager.set_window_title("Movement measurement tool")

        # Connect listeners to the methods below
        self.window_frame.canvas.mpl_connect("button_press_event", self.on_click)
        self.window_frame.canvas.mpl_connect("key_press_event", self.on_key)

        self.setup_plot()
        plt.tight_layout()

    def setup_plot(self):

        self.axes.clear()

        # 2. Board coordinate (1 unit = 1 inch)
        self.axes.set_aspect("equal")
        self.axes.set_xlim(0, self.board_width)
        self.axes.set_ylim(0, self.board_height)

        # 3. Grid system
        self.axes.set_xticks(np.arange(0, self.board_width + 1, 1))
        self.axes.set_yticks(np.arange(0, self.board_height + 1, 1))
        self.axes.grid(True, linestyle=":", color="gray", alpha=0.15)

        # 4. Render the terrain
        for wall in self.entities.walls_list:
            wx, wy = wall.exterior.xy
            self.axes.fill(wx, wy, color="#1e272e", zorder=5)

        # 5. Render the reach field
        if self.navigator.reach_poly:

            # if a wall splits the vision into separate islands.
            if isinstance(self.navigator.reach_poly, Polygon):
                polys = [self.navigator.reach_poly]
            else:
                # Extract individual polygons from the MultiPolygon collection
                polys = list(self.navigator.reach_poly.geoms)

            for p in polys:
                px, py = p.exterior.xy
                self.axes.fill(px, py, color="#70a1ff", alpha=0.5, zorder=2)

        # 6. Render the Model
        if hasattr(self, "current_model") and self.current_model:
            self.current_model.draw(self.axes)

    from shapely.geometry import Point, box  # Ensure 'box' is imported

    def on_click(self, event):
        if event.xdata is None or event.ydata is None:
            return

        raw_pos = Point(event.xdata, event.ydata)

        # --- PATH LABELING (Ctrl + Click) ---
        if event.key == "control" and self.current_model:
            target = raw_pos
            # If target is outside the blue zone, snap to nearest legal edge
            if self.navigator.reach_poly and not self.navigator.reach_poly.contains(
                target
            ):
                target, _ = nearest_points(self.navigator.reach_poly, target)

            self.trace_and_label_path(target)
            return  # Exit early so we don't move the model base

        # --- MODEL PLACEMENT (Standard Click) ---
        # (Your existing snap/placement logic here)
        board_limit = box(0, 0, self.board_width, self.board_height)
        forbidden_zone = self.entities.combined_walls.buffer(self.base_radius + 0.05)
        legal_area = board_limit.difference(forbidden_zone)

        if not legal_area.contains(raw_pos):
            final_pos, _ = nearest_points(legal_area, raw_pos)
        else:
            final_pos = raw_pos

        self.model_pos = final_pos
        self.current_model = Model(final_pos.x, final_pos.y)

        # Recalculate the complex reach zone
        self.navigator.calculate_total_reach(self.model_pos, self.max_move)

        self.update_window()

    def update_window(self):
        self.setup_plot()
        self.window_frame.canvas.draw()

    def on_key(self, event):
        # We only care about the Escape key
        if event.key == "escape":
            # If a model exists, just clear the board (Reset)
            if self.current_model is not None:
                print("Resetting board state...")
                self.current_model = None
                self.model_pos = None
                self.navigator.reach_poly = None
                self.update_window()
            else:
                # If board is already empty, close the app (Close)
                print("Exiting application...")
                plt.close(self.window_frame)

    def trace_and_label_path(self, target):
        # 1. Clear previous path UI elements
        for e in self.navigator.path_elements:
            try:
                e.remove()
            except:
                pass
        self.navigator.path_elements = []

        # 2. Reconstruct path from target to model
        curr_pt = target
        pts_in_order = [target]
        while curr_pt.distance(self.model_pos) > 0.01:
            found = False
            for s in self.navigator.reach_segments:
                if s["poly"].buffer(0.01).contains(curr_pt):
                    pts_in_order.append(s["origin"])
                    curr_pt = s["origin"]
                    found = True
                    break
            if not found:
                break

        pts_in_order.reverse()
        total_dist = 0

        # 3. Draw on the board
        for i in range(len(pts_in_order) - 1):
            p_start, p_end = pts_in_order[i], pts_in_order[i + 1]
            vec = np.array([p_end.x - p_start.x, p_end.y - p_start.y])
            seg_len = np.linalg.norm(vec)
            if seg_len < 0.01:
                continue
            u_vec = vec / seg_len

            # Use self.axes (not self.ax)
            (line,) = self.axes.plot(
                [p_start.x, p_end.x],
                [p_start.y, p_end.y],
                color="yellow",
                lw=2,
                zorder=12,
            )
            self.navigator.path_elements.append(line)

            # Labels and markers
            for inch in range(1, int(seg_len) + 1):
                m_pos = np.array([p_start.x, p_start.y]) + u_vec * inch
                (dot,) = self.axes.plot(m_pos[0], m_pos[1], "wo", ms=4, zorder=20)
                lbl = self.axes.text(
                    m_pos[0],
                    m_pos[1] + 0.4,
                    f'{inch}"',
                    color="white",
                    fontsize=8,
                    weight="bold",
                    zorder=25,
                    ha="center",
                    bbox=dict(facecolor="black", alpha=0.7, lw=0),
                )
                self.navigator.path_elements.extend([dot, lbl])

            total_dist += math.ceil(seg_len)

        # 4. Refresh display
        self.axes.set_title(f'Movement used: {total_dist}" / {self.max_move}"')
        self.window_frame.canvas.draw()
