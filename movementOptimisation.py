import numpy as np
import matplotlib.pyplot as plt
from shapely.geometry import Point, Polygon, LineString, MultiPolygon
from shapely.ops import unary_union, nearest_points
import math


class TombWorldBoard:
    def __init__(self):
        self.board_width = 32
        self.board_height = 20
        self.max_move = 6.0

        self.fig, self.ax = plt.subplots(figsize=(16, 10))
        self.fig.canvas.manager.set_window_title(
            "Warhammer: Infinite Pivot Optimization"
        )

        self.walls = self.build_tomb_world_blueprint()
        self.wall_points = [
            Point(c) for wall in self.walls for c in list(wall.exterior.coords)[:-1]
        ]
        self.combined_walls = unary_union(self.walls)

        self.model_pos = None
        self.reach_segments = []
        self.reach_poly = None
        self.path_elements = []

        self.setup_plot()
        self.fig.canvas.mpl_connect("button_press_event", self.on_click)
        plt.tight_layout()
        plt.show()

    def build_tomb_world_blueprint(self):
        # Blueprint matching the layout in image_de10e6.png
        return [
            Polygon([(4, 4), (28, 4), (28, 6), (6, 6), (6, 16), (4, 16)]),
            Polygon([(12, 10), (16, 10), (16, 14), (12, 14)]),
            Polygon([(22, 10), (24, 10), (24, 20), (22, 20)]),
            Polygon([(8, 12), (10, 12), (10, 14), (8, 14)]),
        ]

    def setup_plot(self):
        self.ax.clear()
        self.ax.set_aspect("equal")
        self.ax.set_xlim(0, self.board_width)
        self.ax.set_ylim(0, self.board_height)
        self.ax.set_xticks(np.arange(0, self.board_width + 1, 1))
        self.ax.set_yticks(np.arange(0, self.board_height + 1, 1))
        self.ax.grid(True, linestyle=":", color="gray", alpha=0.15)
        for wall in self.walls:
            wx, wy = wall.exterior.xy
            self.ax.fill(wx, wy, color="#1e272e", zorder=5)

    def get_visibility_poly(self, origin, radius):
        if radius <= 0.001:
            return None
        circle = origin.buffer(radius, quad_segs=32)
        shadows = []
        orig_arr = np.array([origin.x, origin.y])
        for wall in self.walls:
            pts = list(wall.exterior.coords)[:-1]
            for i in range(len(pts)):
                p1, p2 = np.array(pts[i]), np.array(pts[(i + 1) % len(pts)])
                v1, v2 = (p1 - orig_arr), (p2 - orig_arr)
                n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
                if n1 < 0.001 or n2 < 0.001:
                    continue
                ext1 = orig_arr + (v1 / n1) * 50
                ext2 = orig_arr + (v2 / n2) * 50
                shadows.append(Polygon([p1, p2, ext2, ext1]))
        try:
            return circle.difference(unary_union(shadows))
        except:
            return circle

    def calculate_total_reach(self, start_pt):
        self.reach_segments = []
        primary = self.get_visibility_poly(start_pt, self.max_move)
        if primary:
            self.reach_segments.append({"poly": primary, "origin": start_pt})

        # Track best remaining budget at each corner to prevent infinite loops
        corner_budgets = {}
        safe_walls = self.combined_walls.buffer(-0.01)

        # Queue format: (current_point, remaining_budget)
        queue = [(start_pt, self.max_move)]

        while queue:
            origin, budget = queue.pop(0)

            for corner in self.wall_points:
                dist = origin.distance(corner)
                # Check if this corner is reachable and visible from current origin
                if 0.01 < dist < budget:
                    if not LineString([origin, corner]).intersects(safe_walls):

                        used_inches = math.ceil(dist)
                        remaining = budget - used_inches

                        if remaining >= 0:
                            # 1. Test Corner Pivot
                            if (
                                corner not in corner_budgets
                                or remaining > corner_budgets[corner]
                            ):
                                corner_budgets[corner] = remaining
                                poly = self.get_visibility_poly(corner, remaining)
                                if poly:
                                    self.reach_segments.append(
                                        {"poly": poly, "origin": corner}
                                    )
                                    queue.append((corner, remaining))

                            # 2. Test Segment Pivot (Projecting to the full inch mark)
                            if used_inches < budget:
                                dir_vec = np.array(
                                    [corner.x - origin.x, corner.y - origin.y]
                                )
                                dir_vec = (dir_vec / dist) * used_inches
                                seg_pt = Point(
                                    origin.x + dir_vec[0], origin.y + dir_vec[1]
                                )

                                # Only pivot if we cleared the wall and didn't land inside another
                                if not self.combined_walls.contains(seg_pt):
                                    if (
                                        seg_pt not in corner_budgets
                                        or remaining > corner_budgets[seg_pt]
                                    ):
                                        corner_budgets[seg_pt] = remaining
                                        poly_s = self.get_visibility_poly(
                                            seg_pt, remaining
                                        )
                                        if poly_s:
                                            self.reach_segments.append(
                                                {"poly": poly_s, "origin": seg_pt}
                                            )
                                            queue.append((seg_pt, remaining))

        self.reach_poly = unary_union(
            [s["poly"] for s in self.reach_segments]
        ).difference(self.combined_walls)
        return self.reach_poly

    def trace_and_label_path(self, target):
        for e in self.path_elements:
            try:
                e.remove()
            except:
                pass
        self.path_elements = []

        curr_pt = target
        pts_in_order = [target]
        while curr_pt.distance(self.model_pos) > 0.01:
            found = False
            for s in self.reach_segments:
                if s["poly"].buffer(0.01).contains(curr_pt):
                    pts_in_order.append(s["origin"])
                    curr_pt = s["origin"]
                    found = True
                    break
            if not found:
                break

        pts_in_order.reverse()
        total_dist = 0
        for i in range(len(pts_in_order) - 1):
            p_start, p_end = pts_in_order[i], pts_in_order[i + 1]
            vec = np.array([p_end.x - p_start.x, p_end.y - p_start.y])
            seg_len = np.linalg.norm(vec)
            if seg_len < 0.01:
                continue
            u_vec = vec / seg_len

            (line,) = self.ax.plot(
                [p_start.x, p_end.x],
                [p_start.y, p_end.y],
                color="yellow",
                lw=2,
                zorder=12,
            )
            self.path_elements.append(line)

            for inch in range(1, int(seg_len) + 1):
                m_pos = np.array([p_start.x, p_start.y]) + u_vec * inch
                (dot,) = self.ax.plot(m_pos[0], m_pos[1], "wo", ms=4, zorder=20)
                lbl = self.ax.text(
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
                self.path_elements.extend([dot, lbl])

            if seg_len % 1.0 > 0.01:
                lbl = self.ax.text(
                    p_end.x,
                    p_end.y + 0.4,
                    f'+{seg_len%1.0:.1f}"',
                    color="#fffa65",
                    fontsize=8,
                    weight="bold",
                    zorder=25,
                    bbox=dict(facecolor="#303952", alpha=0.9, lw=0),
                )
                self.path_elements.append(lbl)
            total_dist += math.ceil(seg_len)  # Warhammer deduction logic

        self.ax.set_title(f'Used: {total_dist} inches of {self.max_move}" Budget')
        self.fig.canvas.draw()

    def on_click(self, event):
        if event.xdata is None or event.ydata is None:
            return
        pos = Point(event.xdata, event.ydata)
        if event.key == "control" and self.model_pos:
            target = pos
            if self.reach_poly and not self.reach_poly.contains(pos):
                target, _ = nearest_points(self.reach_poly, pos)
            self.trace_and_label_path(target)
            return
        if self.combined_walls.contains(pos):
            return
        self.model_pos = pos
        self.update_display()

    def update_display(self):
        self.setup_plot()
        self.path_elements = []
        reach = self.calculate_total_reach(self.model_pos)
        if isinstance(reach, (Polygon, MultiPolygon)):
            polys = [reach] if isinstance(reach, Polygon) else reach.geoms
            for p in polys:
                x, y = p.exterior.xy
                self.ax.fill(x, y, alpha=0.3, fc="#70a1ff", ec="#1e90ff", zorder=2)
        self.ax.add_patch(
            plt.Circle(
                (self.model_pos.x, self.model_pos.y), 0.4, color="#ff4757", zorder=10
            )
        )
        self.fig.canvas.draw()


if __name__ == "__main__":
    TombWorldBoard()
