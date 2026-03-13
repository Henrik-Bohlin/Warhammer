import numpy as np
import math
from collections import deque
from shapely.geometry import Point, Polygon, LineString
from shapely.ops import unary_union, nearest_points
from shapely.prepared import prep


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
        model_reach_circle = origin.buffer(radius, quad_segs=16)

        # Blind spots
        visibility_obstruction = []
        origin_coords = np.array([origin.x, origin.y])

        for segment_start, segment_end in self.ctx.collision_edges:
            # Back-face culling: buffered walls are convex (CCW winding),
            # so edges whose inward side faces the origin cast redundant shadows
            edge_vec = segment_end - segment_start
            to_origin = origin_coords - segment_start
            cross = edge_vec[0] * to_origin[1] - edge_vec[1] * to_origin[0]
            if cross > 0:
                continue

            to_start = segment_start - origin_coords
            to_end = segment_end - origin_coords
            dist_to_start = np.linalg.norm(to_start)
            dist_to_end = np.linalg.norm(to_end)
            if dist_to_start < 0.001 or dist_to_end < 0.001:
                continue
            projecton_length = 50
            projected_start = (
                origin_coords + (to_start / dist_to_start) * projecton_length
            )
            projected_end = origin_coords + (to_end / dist_to_end) * projecton_length
            visibility_obstruction.append(
                Polygon([segment_start, segment_end, projected_end, projected_start])
            )

        # Remove blind spots from the potential reach area
        try:
            all_blocked_areas = unary_union(visibility_obstruction)
            actual_reach_poly = model_reach_circle.difference(all_blocked_areas)
            # Also subtract the collision layer so reach never extends into it
            actual_reach_poly = actual_reach_poly.difference(self.ctx.collision_walls)
            # Heal any invalid geometry from boolean ops (prevents compounding errors)
            if not actual_reach_poly.is_valid:
                actual_reach_poly = actual_reach_poly.buffer(0)
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

        # Use collision walls (walls + base_radius buffer)
        combined_walls = self.ctx.collision_walls
        wall_points = self.ctx.collision_wall_points
        wp_xy = self.ctx.wall_points_xy  # Numpy array for fast distance
        safe_walls = combined_walls.buffer(-0.01)
        prepped_safe = prep(safe_walls)
        prepped_walls = self.ctx.prepped_collision_walls

        queue = deque([(start_pt, max_move)])

        while queue:
            origin, budget = queue.popleft()
            origin_xy = np.array([origin.x, origin.y])

            # Vectorised distance to ALL wall points (one numpy call)
            dists = np.linalg.norm(wp_xy - origin_xy, axis=1)

            # Only check corners within budget range
            candidates = np.where((dists > 0.01) & (dists < budget))[0]

            for idx in candidates:
                corner = wall_points[idx]
                dist = float(dists[idx])
                ckey = (round(corner.x, 4), round(corner.y, 4))

                if not prepped_safe.intersects(LineString([origin, corner])):

                    # Warhammer rounding: round up the cost of the segment
                    used_inches = math.ceil(dist)
                    remaining = budget - used_inches

                    if remaining >= 0:
                        # --- 1. Corner Pivot ---
                        if (
                            ckey not in corner_budgets
                            or remaining > corner_budgets[ckey]
                        ):
                            corner_budgets[ckey] = remaining
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
                            seg_pt = Point(origin.x + dir_vec[0], origin.y + dir_vec[1])

                            # Only pivot if we cleared the wall and didn't land inside another
                            if not prepped_walls.contains(seg_pt):
                                skey = (round(seg_pt.x, 4), round(seg_pt.y, 4))
                                if (
                                    skey not in corner_budgets
                                    or remaining > corner_budgets[skey]
                                ):
                                    corner_budgets[skey] = remaining
                                    poly_s = self.get_visibility_poly(seg_pt, remaining)
                                    if poly_s:
                                        self.reach_segments.append(
                                            {"poly": poly_s, "origin": seg_pt}
                                        )
                                        queue.append((seg_pt, remaining))

        # Merge all segments and remove wall areas
        merged = unary_union([s["poly"] for s in self.reach_segments]).difference(
            combined_walls
        )
        # Heal any invalid geometry from accumulated boolean ops
        self.reach_poly = merged.buffer(0) if not merged.is_valid else merged
        return self.reach_poly
