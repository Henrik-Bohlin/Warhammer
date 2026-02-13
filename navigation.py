import numpy as np
import math
from shapely.geometry import Point, Polygon, LineString
from shapely.ops import unary_union, nearest_points


class PathFinder:
    def __init__(self, board_context):
        self.ctx = board_context  # This gives the logic access to walls/axes
        self.reach_segments = []
        self.reach_poly = None
        self.path_elements = []

    def get_visibility_poly(self, origin, radius):
        """
        Calculates the 'Reach Zone': the area a model can see or move into,
        taking into account the 'blind spots' created by walls.
        """

        # Move distance is zero
        if radius <= 0.001:
            return None

        # Potential reach area is a circle around the model
        model_reach_circle = origin.buffer(radius, quad_segs=32)

        # Blind spots
        visibility_obstruction = []
        origin_coords = np.array([origin.x, origin.y])

        for wall in self.ctx.entities.walls_list:
            vertices = list(wall.exterior.coords)[:-1]
            for i in range(len(vertices)):
                segment_start = np.array(vertices[i])
                segment_end = np.array(vertices[(i + 1) % len(vertices)])
                to_start, to_end = (segment_start - origin_coords), (
                    segment_end - origin_coords
                )
                dist_to_start, dist_to_end = np.linalg.norm(to_start), np.linalg.norm(
                    to_end
                )
                if dist_to_start < 0.001 or dist_to_end < 0.001:
                    continue
                projecton_length = 50
                projected_start = (
                    origin_coords + (to_start / dist_to_start) * projecton_length
                )
                projected_end = (
                    origin_coords + (to_end / dist_to_end) * projecton_length
                )
                visibility_obstruction.append(
                    Polygon(
                        [segment_start, segment_end, projected_end, projected_start]
                    )
                )

        # Remove blind spots from the potential reach area
        try:
            all_blocked_areas = unary_union(visibility_obstruction)
            actual_reach_poly = model_reach_circle.difference(all_blocked_areas)
            return actual_reach_poly
        except Exception:
            # Default return full circle
            return model_reach_circle

    # navigation.py inside class PathFinder
    def calculate_total_reach(self, start_pt, max_move):
        self.reach_segments = []

        # 1. Primary visibility from start
        primary = self.get_visibility_poly(start_pt, max_move)
        if primary:
            self.reach_segments.append({"poly": primary, "origin": start_pt})

        # Track best remaining budget to prevent infinite loops and improve RPi 5 performance
        corner_budgets = {}

        # Use entities from context
        combined_walls = self.ctx.entities.combined_walls
        wall_points = self.ctx.entities.wall_points
        safe_walls = combined_walls.buffer(-0.01)

        queue = [(start_pt, max_move)]

        while queue:
            origin, budget = queue.pop(0)

            for corner in wall_points:
                dist = origin.distance(corner)

                # Check if corner is reachable and visible
                if 0.01 < dist < budget:
                    if not LineString([origin, corner]).intersects(safe_walls):

                        # Warhammer rounding: round up the cost of the segment
                        used_inches = math.ceil(dist)
                        remaining = budget - used_inches

                        if remaining >= 0:
                            # --- 1. Corner Pivot ---
                            if (
                                corner not in corner_budgets
                                or remaining > corner_budgets.get(corner, -1)
                            ):
                                corner_budgets[corner] = remaining
                                poly = self.get_visibility_poly(corner, remaining)
                                if poly:
                                    self.reach_segments.append(
                                        {"poly": poly, "origin": corner}
                                    )
                                    queue.append((corner, remaining))

                            # --- 2. Segment Pivot (The "Fluid" Fix) ---
                            # Project past the corner to the full inch mark
                            if used_inches <= budget:
                                dir_vec = np.array(
                                    [corner.x - origin.x, corner.y - origin.y]
                                )
                                # Normalize and scale to the full inch used
                                dir_vec = (dir_vec / dist) * used_inches
                                seg_pt = Point(
                                    origin.x + dir_vec[0], origin.y + dir_vec[1]
                                )

                                # Only pivot if we cleared the wall and didn't land inside another
                                if not combined_walls.contains(seg_pt):
                                    if (
                                        seg_pt not in corner_budgets
                                        or remaining > corner_budgets.get(seg_pt, -1)
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

        # Merge all segments and remove wall areas
        self.reach_poly = unary_union(
            [s["poly"] for s in self.reach_segments]
        ).difference(combined_walls)
        return self.reach_poly
