from entities import Terrain, Model
from navigation import PathFinder
import matplotlib.pyplot as plt
import math
import numpy as np
from shapely.geometry import Point, Polygon, box, LineString
from shapely.ops import nearest_points, unary_union
from shapely.prepared import prep


class Board:
    def __init__(self):
        # --- 1. Dimensions & Unit Constants ---
        self.board_width = 30
        self.board_height = 22
        self.linethickness = 0.2
        self.max_move = 6
        self.base_radius = (32 / 25.4) / 2  # 32mm base radius in inches
        self.visual_padding = 0.05

        # --- 2. Entity & Terrain Logic ---
        # We pass dimensions so Terrain knows where to draw the rails
        self.entities = Terrain(self.board_width, self.board_height, self.linethickness)
        self.combined_walls = self.entities.combined_walls

        # Permanent collision layer: walls expanded by base_radius (half model size)
        # Round join with quad_segs=3 keeps corners within 2mm of base_radius
        self.collision_walls_list = [
            w.buffer(self.base_radius, quad_segs=3) for w in self.entities.walls_list
        ]
        self.collision_walls = unary_union(self.collision_walls_list)

        # Decompose merged geometry once for reuse
        self._cw_geoms = (
            list(self.collision_walls.geoms)
            if self.collision_walls.geom_type == "MultiPolygon"
            else [self.collision_walls]
        )

        # Extract nav points from merged geometry (skips redundant interior points)
        _wp_list = []
        for _g in self._cw_geoms:
            for c in list(_g.exterior.coords)[:-1]:
                _wp_list.append(c)
            for _hole in _g.interiors:
                for c in list(_hole.coords)[:-1]:
                    _wp_list.append(c)
        self.collision_wall_points = [Point(c) for c in _wp_list]
        # Numpy coords array for vectorised distance checks in BFS
        self.wall_points_xy = np.array(_wp_list)

        # Pre-extract edge segments as numpy arrays from individual walls
        # (individual buffered walls are convex, enabling back-face culling)
        self.collision_edges = []
        for wall in self.collision_walls_list:
            coords = list(wall.exterior.coords)
            for i in range(len(coords) - 1):
                self.collision_edges.append(
                    (np.array(coords[i]), np.array(coords[i + 1]))
                )

        # Prepared geometry for fast spatial predicates
        self.prepped_collision_walls = prep(self.collision_walls)

        # Pre-compute buffered collision walls for rendering (avoid per-redraw buffer calls)
        self._collision_walls_render_buf = self.collision_walls.buffer(0.01)

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
            self.collision_walls.buffer(self.visual_padding)
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

        x_ticks = np.arange(self.linethickness, self.board_width, 1)
        y_ticks = np.arange(self.linethickness, self.board_height, 1)
        self.axes.set_xticks(x_ticks)
        self.axes.set_xticklabels([str(i) for i in range(len(x_ticks))])
        self.axes.set_yticks(y_ticks)
        self.axes.set_yticklabels([str(i) for i in range(len(y_ticks))])
        self.axes.grid(True, linestyle=":", color="gray", alpha=0.15)

        # 4. Render the collision layer (individual walls) then raw walls on top
        for cwall in self.collision_walls_list:
            cx, cy = cwall.exterior.xy
            self.axes.fill(cx, cy, color="#3d3d3d", alpha=0.5, zorder=4)
        for wall in self.entities.walls_list:
            wx, wy = wall.exterior.xy
            self.axes.fill(wx, wy, color="#1e272e", zorder=5)

        # 5. Render the reach field
        if self.navigator.reach_poly:
            wall_overlay = self.collision_walls.intersection(self.navigator.reach_poly)

            # Blue fill: reach area with yellow zones cut out
            blue_area = self.navigator.reach_poly.difference(wall_overlay)
            blue_polys = (
                list(blue_area.geoms)
                if blue_area.geom_type == "MultiPolygon"
                else [blue_area] if not blue_area.is_empty else []
            )

            for p in blue_polys:
                px, py = p.exterior.xy
                self.axes.fill(px, py, color="#70a1ff", alpha=0.5, zorder=2)
                # Green outline on the blue exterior only (remove wall-face segments)
                outer_line = p.exterior.difference(
                    wall_overlay.buffer(0.001)
                ).difference(self._collision_walls_render_buf)
                if not outer_line.is_empty:
                    segs = (
                        list(outer_line.geoms)
                        if hasattr(outer_line, "geoms")
                        else [outer_line]
                    )
                    for seg in segs:
                        sx, sy = seg.xy
                        self.axes.plot(sx, sy, color="#00ff88", lw=1.5, zorder=3)

        # 6. Render yellow offset zone around walls
        if self.navigator.reach_poly:
            if not wall_overlay.is_empty:
                overlay_polys = (
                    list(wall_overlay.geoms)
                    if wall_overlay.geom_type == "MultiPolygon"
                    else [wall_overlay]
                )

                for p in overlay_polys:
                    try:
                        px, py = p.exterior.xy
                        self.axes.fill(px, py, color="yellow", alpha=1, zorder=4)
                        for interior in p.interiors:
                            ix, iy = interior.xy
                            self.axes.fill(ix, iy, color="#70a1ff", alpha=0.5, zorder=4)
                    except Exception as e:
                        pass

                # Green outline on the arc facing the blue area
                wb = wall_overlay.boundary
                if wb is not None and not wb.is_empty:
                    facing_boundary = wb.difference(self._collision_walls_render_buf)
                    if not facing_boundary.is_empty:
                        geoms = (
                            list(facing_boundary.geoms)
                            if hasattr(facing_boundary, "geoms")
                            else [facing_boundary]
                        )
                        for geom in geoms:
                            gx, gy = geom.xy
                            self.axes.plot(gx, gy, color="#00ff88", lw=1.5, zorder=6)

        # 7. Render the Model
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
        if not self.legal_area.contains(raw_pos):
            final_pos, _ = nearest_points(self.legal_area, raw_pos)
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
        visited = set()
        while curr_pt.distance(self.model_pos) > 0.01:
            found = False
            ck = (round(curr_pt.x, 4), round(curr_pt.y, 4))
            visited.add(ck)
            for s in self.navigator.reach_segments:
                sk = (round(s["origin"].x, 4), round(s["origin"].y, 4))
                if sk in visited:
                    continue
                # distance check avoids creating a buffered geometry per segment
                if s["poly"].distance(curr_pt) < 0.01:
                    pts_in_order.append(s["origin"])
                    curr_pt = s["origin"]
                    found = True
                    break
            if not found:
                break

        pts_in_order.reverse()
        total_dist = 0

        # 3. Draw on the board (clip lines against collision layer)
        for i in range(len(pts_in_order) - 1):
            p_start, p_end = pts_in_order[i], pts_in_order[i + 1]
            vec = np.array([p_end.x - p_start.x, p_end.y - p_start.y])
            seg_len = np.linalg.norm(vec)
            if seg_len < 0.01:
                continue
            u_vec = vec / seg_len

            # Clip the line so it never crosses the collision layer
            raw_line = LineString([(p_start.x, p_start.y), (p_end.x, p_end.y)])
            clipped = raw_line.difference(self.collision_walls)
            if not clipped.is_empty:
                parts = list(clipped.geoms) if hasattr(clipped, "geoms") else [clipped]
                for part in parts:
                    lx, ly = part.xy
                    (line,) = self.axes.plot(lx, ly, color="yellow", lw=2, zorder=12)
                    self.navigator.path_elements.append(line)

            # Labels and markers — skip any inside the collision layer
            for inch in range(1, int(seg_len) + 1):
                m_pos = np.array([p_start.x, p_start.y]) + u_vec * inch
                if self.prepped_collision_walls.contains(Point(m_pos[0], m_pos[1])):
                    continue
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
