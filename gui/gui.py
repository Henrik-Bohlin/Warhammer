"""
Standalone Pygame GUI prototype for the Kill Team movement tool.
Run directly:  python gui/gui.py
"""

import sys
import os
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "movement_tool"))

import pygame
import numpy as np
from shapely.geometry import Point, LineString, box
from shapely.ops import nearest_points, unary_union
from shapely.prepared import prep
from menu import show_movement_menu, show_map_menu
from maps import WIN_W, WIN_H, BASE_RADIUS, MAPS, MAP_ORDER, display_config
from entities import Terrain, Model
from navigation import PathFinder

# ── Non-map display constants ─────────────────────────────────────────────────
DASH_LENGTH = 3
CHARGE_LENGTH = 2

# ── Colours ───────────────────────────────────────────────────────────────────
C_BG = (30, 30, 40)
C_WALL = (30, 39, 46)
C_CWALL = (61, 61, 61, 0)
C_GRID = (255, 255, 255, 130)
C_REACH = (112, 161, 255, 100)
C_REACH_EDGE = (0, 255, 136, 220)
C_WALL_OVLY = (255, 255, 0, 180)
C_MODEL = (211, 28, 43, 255)
C_MODEL_RIM = (255, 255, 255, 200)
C_PATH = (255, 220, 0)
C_STATUS_BG = (0, 0, 0, 180)
C_STATUS_FG = (200, 200, 200)


def iter_polys(geom):
    """Yield individual Polygon objects from a Polygon or MultiPolygon."""
    if geom.is_empty:
        return
    if geom.geom_type == "MultiPolygon":
        yield from geom.geoms
    elif geom.geom_type == "Polygon":
        yield geom


# ── Board state (pure logic, no rendering) ────────────────────────────────────
class BoardState:
    def __init__(self, layout, max_move):
        self.board_width = layout.width
        self.board_height = layout.height
        self.linethickness = layout.line_thickness
        self.max_move = max_move
        self.base_radius = BASE_RADIUS

        terrain_cls = layout.terrain_factory or Terrain
        self.entities = terrain_cls(layout.width, layout.height, layout.line_thickness)
        self.combined_walls = self.entities.combined_walls

        self.collision_walls_list = [
            w.buffer(BASE_RADIUS, quad_segs=3) for w in self.entities.walls_list
        ]
        self.collision_walls = unary_union(self.collision_walls_list)

        _cw_geoms = (
            list(self.collision_walls.geoms)
            if self.collision_walls.geom_type == "MultiPolygon"
            else [self.collision_walls]
        )

        _wp_list = []
        for g in _cw_geoms:
            for c in list(g.exterior.coords)[:-1]:
                _wp_list.append(c)
            for hole in g.interiors:
                for c in list(hole.coords)[:-1]:
                    _wp_list.append(c)
        self.collision_wall_points = [Point(c) for c in _wp_list]
        self.wall_points_xy = np.array(_wp_list)

        self.collision_edges = []
        for wall in self.collision_walls_list:
            coords = list(wall.exterior.coords)
            for i in range(len(coords) - 1):
                self.collision_edges.append(
                    (np.array(coords[i]), np.array(coords[i + 1]))
                )

        self.prepped_collision_walls = prep(self.collision_walls)
        self._collision_walls_render_buf = self.collision_walls.buffer(0.01)

        self.legal_area = box(0, 0, layout.width, layout.height).difference(
            self.collision_walls.buffer(0.05)
        )

        self.model_pos = None
        self.current_model = None
        self.navigator = PathFinder(self)
        self.navigator.reach_segments = []
        self.navigator.path_elements = []


# ── GUI ───────────────────────────────────────────────────────────────────────
class GUI:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.FULLSCREEN | pygame.NOFRAME)
        pygame.display.set_caption("Warhammer Movement Tool")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("monospace", 18)
        self.font_bold = pygame.font.SysFont("monospace", 20, bold=True)
        self.font_panel = pygame.font.SysFont("monospace", 14)

        layout_key = show_map_menu(self.screen, self.font, MAPS, MAP_ORDER)
        max_move = show_movement_menu(self.screen, self.font)

        self.move_mode = "normal"
        self._path_lines = []
        self._path_labels = []
        self._status = (
            "Click to place model  |  Ctrl+Click to measure path  |  ESC to reset"
        )

        self._load_map(layout_key, max_move)

    # ── coordinate transforms (depend on per-map scale/offsets) ──────────────

    def b2s(self, bx, by):
        """Board inches → screen pixels."""
        return (
            int(bx * self.scale) + self.board_offset_x,
            int(WIN_H - by * self.scale) - self.board_offset_y,
        )

    def s2b(self, sx, sy):
        """Screen pixels → board inches."""
        return (
            (sx - self.board_offset_x) / self.scale,
            (WIN_H - sy + self.board_offset_y) / self.scale,
        )

    def poly_pts(self, shapely_poly):
        return [self.b2s(x, y) for x, y in shapely_poly.exterior.coords]

    def hole_pts(self, ring):
        return [self.b2s(x, y) for x, y in ring.coords]

    # ── map loading ───────────────────────────────────────────────────────────

    def _load_map(self, layout_key, max_move=None):
        layout = MAPS[layout_key]
        if max_move is None:
            max_move = self.board.max_move

        self.layout = layout
        self.scale, self.board_px_w, self.board_px_h, self.board_offset_x, self.board_offset_y = display_config(layout)

        self.board = BoardState(layout, max_move)
        self.move_mode = "normal"
        self._path_lines = []
        self._path_labels = []
        self._overlay_surf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        self._static_surf = self._build_static()
        self._status = (
            "Click to place model  |  Ctrl+Click to measure path  |  ESC to reset"
        )

    # ── effective movement ────────────────────────────────────────────────────

    def _effective_move(self):
        if self.move_mode == "dash":
            return self.board.max_move + DASH_LENGTH
        elif self.move_mode == "charge":
            return self.board.max_move + CHARGE_LENGTH
        return self.board.max_move

    def _recompute_reach(self):
        nav = self.board.navigator
        nav.calculate_total_reach(self.board.model_pos, self._effective_move())
        self._update_overlay()
        self._path_lines = []
        self._path_labels = []
        mode_label = self.move_mode.upper() if self.move_mode != "normal" else "MOVE"
        self._status = (
            f'{mode_label}  |  Reach: {self._effective_move()}"  |  '
            "D=dash  C=charge  ESC=reset"
        )

    # ── static background ─────────────────────────────────────────────────────

    def _build_static(self):
        surf = pygame.Surface((WIN_W, WIN_H))

        if self.layout.background_image and os.path.exists(self.layout.background_image):
            img = pygame.image.load(self.layout.background_image).convert()
            surf.fill(C_BG)
            surf.blit(
                pygame.transform.scale(img, (self.board_px_w, self.board_px_h)),
                (self.board_offset_x, self.board_offset_y),
            )
        else:
            surf.fill(C_BG)
        self._draw_grid(surf)

        cwall_surf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        for cwall in self.board.collision_walls_list:
            pts = self.poly_pts(cwall)
            if len(pts) >= 3:
                pygame.draw.polygon(cwall_surf, C_CWALL, pts)
        surf.blit(cwall_surf, (0, 0))

        for wall in self.board.entities.walls_list:
            pts = self.poly_pts(wall)
            if len(pts) >= 3:
                pygame.draw.polygon(surf, C_WALL, pts)

        return surf

    def _draw_grid(self, surf):
        grid = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        w, h = self.layout.width, self.layout.height
        gc = self.layout.grid_color

        cell = self.layout.grid_cell_size
        cols = self.layout.grid_cols
        rows = self.layout.grid_rows

        if cell and cols and rows:
            # Tombworld-style: fixed cell size with equal margins derived from board dims.
            margin_x = (w - cols * cell) / 2
            margin_y = (h - rows * cell) / 2

            grid_x0, _ = self.b2s(margin_x, 0)
            grid_x1, _ = self.b2s(margin_x + cols * cell, 0)
            _, grid_y0 = self.b2s(0, margin_y + rows * cell)  # screen top of grid
            _, grid_y1 = self.b2s(0, margin_y)                # screen bottom of grid

            for c in range(cols + 1):
                sx, _ = self.b2s(margin_x + c * cell, 0)
                pygame.draw.line(grid, gc, (sx, grid_y0), (sx, grid_y1))
            for r in range(rows + 1):
                _, sy = self.b2s(0, margin_y + r * cell)
                pygame.draw.line(grid, gc, (grid_x0, sy), (grid_x1, sy))
        else:
            lt = self.layout.line_thickness
            x_positions = np.arange(lt, w - lt + 0.001, 1.0)
            y_positions = np.arange(lt, h - lt + 0.001, 1.0)

            board_left, board_top = self.b2s(lt, h - lt)
            board_right, board_bottom = self.b2s(w - lt, lt)

            for bx in x_positions:
                sx, _ = self.b2s(bx, 0)
                pygame.draw.line(grid, gc, (sx, board_top), (sx, board_bottom))
            for by in y_positions:
                _, sy = self.b2s(0, by)
                pygame.draw.line(grid, gc, (board_left, sy), (board_right, sy))

        surf.blit(grid, (0, 0))

    # ── reach overlay ─────────────────────────────────────────────────────────

    def _update_overlay(self):
        self._overlay_surf.fill((0, 0, 0, 0))
        nav = self.board.navigator

        if nav.reach_poly and not nav.reach_poly.is_empty:
            cw = self.board.collision_walls
            wall_overlay = cw.intersection(nav.reach_poly)
            blue_area = nav.reach_poly.difference(wall_overlay)

            for p in iter_polys(blue_area):
                pts = self.poly_pts(p)
                if len(pts) >= 3:
                    pygame.draw.polygon(self._overlay_surf, C_REACH, pts)
                    pygame.draw.lines(self._overlay_surf, C_REACH_EDGE, True, pts, 2)

            for p in iter_polys(wall_overlay):
                try:
                    pts = self.poly_pts(p)
                    if len(pts) >= 3:
                        pygame.draw.polygon(self._overlay_surf, C_WALL_OVLY, pts)
                        for hole in p.interiors:
                            hpts = self.hole_pts(hole)
                            if len(hpts) >= 3:
                                pygame.draw.polygon(self._overlay_surf, C_REACH, hpts)
                except Exception:
                    pass

        if self.board.current_model:
            m = self.board.current_model
            sx, sy = self.b2s(m.x, m.y)
            r_px = max(1, int(m.base_radius * self.scale))
            pygame.draw.circle(self._overlay_surf, C_MODEL, (sx, sy), r_px)
            pygame.draw.circle(self._overlay_surf, C_MODEL_RIM, (sx, sy), r_px, 2)

    # ── path tracing ──────────────────────────────────────────────────────────

    def _trace_path(self, target_pt):
        self._path_lines = []
        self._path_labels = []
        nav = self.board.navigator
        board = self.board

        curr_pt = target_pt
        pts_in_order = [target_pt]
        visited = set()

        while curr_pt.distance(board.model_pos) > 0.01:
            ck = (round(curr_pt.x, 4), round(curr_pt.y, 4))
            visited.add(ck)
            found = False
            for s in nav.reach_segments:
                sk = (round(s["origin"].x, 4), round(s["origin"].y, 4))
                if sk in visited:
                    continue
                if s["poly"].distance(curr_pt) < 0.01:
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

            raw_line = LineString([(p_start.x, p_start.y), (p_end.x, p_end.y)])
            clipped = raw_line.difference(board.collision_walls)
            if not clipped.is_empty:
                parts = list(clipped.geoms) if hasattr(clipped, "geoms") else [clipped]
                for part in parts:
                    lx, ly = part.xy
                    self._path_lines.append(
                        ([self.b2s(x, y) for x, y in zip(lx, ly)], C_PATH, 2)
                    )

            for inch in range(1, int(seg_len) + 1):
                m_pos = np.array([p_start.x, p_start.y]) + u_vec * inch
                if board.prepped_collision_walls.contains(Point(m_pos[0], m_pos[1])):
                    continue
                sx, sy = self.b2s(m_pos[0], m_pos[1])
                self._path_labels.append((sx, sy, f'{inch}"'))

            total_dist += math.ceil(seg_len)

        self._status = (
            f'Path: {total_dist}" / {board.max_move}"  |  '
            "Click to reposition  |  ESC to reset"
        )

    # ── frame rendering ───────────────────────────────────────────────────────

    def _draw_frame(self):
        self.screen.blit(self._static_surf, (0, 0))
        self.screen.blit(self._overlay_surf, (0, 0))

        for pts, colour, width in self._path_lines:
            if len(pts) >= 2:
                pygame.draw.lines(self.screen, colour, False, pts, width)

        for sx, sy, text in self._path_labels:
            pygame.draw.circle(self.screen, (255, 255, 255), (sx, sy), 4)
            lbl = self.font.render(text, True, (255, 255, 255))
            bg = pygame.Surface(
                (lbl.get_width() + 6, lbl.get_height() + 4), pygame.SRCALPHA
            )
            bg.fill((0, 0, 0, 180))
            self.screen.blit(bg, (sx - lbl.get_width() // 2 - 3, sy - 18))
            self.screen.blit(lbl, (sx - lbl.get_width() // 2, sy - 17))

        self._draw_left_panel()

        pygame.display.flip()

    def _draw_left_panel(self):
        lines = [s.strip() for s in self._status.split("|") if s.strip()]
        y = 20
        for line in lines:
            lbl = self.font_panel.render(line, True, C_STATUS_FG)
            self.screen.blit(lbl, (10, y))
            y += lbl.get_height() + 8

        hints = ["Q: exit", "L: change map", "M: change movement budget"]
        if self.board.current_model is not None:
            hints.append("ESC: reset position")
        y = WIN_H - 20 - len(hints) * (self.font_panel.get_height() + 6)
        for hint in hints:
            lbl = self.font_panel.render(hint, True, (140, 140, 140))
            self.screen.blit(lbl, (10, y))
            y += lbl.get_height() + 6

    # ── main event loop ───────────────────────────────────────────────────────

    def run(self):
        ctrl_held = False

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return

                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_LCTRL, pygame.K_RCTRL):
                        ctrl_held = True
                    elif event.key == pygame.K_q:
                        pygame.quit()
                        return
                    elif event.key == pygame.K_ESCAPE:
                        if self.board.current_model is not None:
                            self.board.current_model = None
                            self.board.model_pos = None
                            self.board.navigator.reach_poly = None
                            self.board.navigator.reach_segments = []
                            self._path_lines = []
                            self._path_labels = []
                            self._update_overlay()
                            self._status = "Click to place model  |  Ctrl+Click to measure path  |  ESC to reset"
                    elif event.key == pygame.K_d:
                        if self.board.current_model is not None:
                            self.move_mode = "normal" if self.move_mode == "dash" else "dash"
                            self._recompute_reach()
                    elif event.key == pygame.K_c:
                        if self.board.current_model is not None:
                            self.move_mode = "normal" if self.move_mode == "charge" else "charge"
                            self._recompute_reach()
                    elif event.key == pygame.K_m:
                        new_move = show_movement_menu(self.screen, self.font)
                        self.board.max_move = new_move
                        if self.board.current_model is not None:
                            self._recompute_reach()
                    elif event.key == pygame.K_l:
                        layout_key = show_map_menu(self.screen, self.font, MAPS, MAP_ORDER)
                        self._load_map(layout_key)

                elif event.type == pygame.KEYUP:
                    if event.key in (pygame.K_LCTRL, pygame.K_RCTRL):
                        ctrl_held = False

                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    bx, by = self.s2b(*event.pos)
                    raw_pos = Point(bx, by)
                    nav = self.board.navigator

                    if ctrl_held and self.board.current_model:
                        target = raw_pos
                        if nav.reach_poly and not nav.reach_poly.contains(target):
                            target, _ = nearest_points(nav.reach_poly, target)
                        self._trace_path(target)
                    else:
                        self._path_lines = []
                        self._path_labels = []
                        if not self.board.legal_area.contains(raw_pos):
                            final_pos, _ = nearest_points(self.board.legal_area, raw_pos)
                        else:
                            final_pos = raw_pos

                        self.board.model_pos = final_pos
                        self.board.current_model = Model(final_pos.x, final_pos.y)
                        self._status = "Computing reach area…"
                        self._draw_frame()

                        nav.calculate_total_reach(final_pos, self._effective_move())
                        self._update_overlay()
                        mode_label = self.move_mode.upper() if self.move_mode != "normal" else ""
                        self._status = (
                            f'Model at ({final_pos.x:.1f}", {final_pos.y:.1f}")  |  '
                            f'Reach: {self._effective_move()}" {mode_label}  |  '
                            "Ctrl+Click to measure path  |  D=dash  C=charge  L=map  |  ESC to reset"
                        )

            self._draw_frame()
            self.clock.tick(30)


if __name__ == "__main__":
    GUI().run()
