from shapely.geometry import Point, box
from shapely.ops import unary_union


class Terrain:
    def __init__(self, width=32, height=20, thickness=0.5):
        self.board_width = width
        self.board_height = height
        self.linethickness = thickness

        # Now call the walls method
        self.walls_list = self.walls()
        self.combined_walls = unary_union(self.walls_list)

        # Pre-calculate points for the navigator
        self.wall_points = [
            Point(c)
            for wall in self.walls_list
            for c in list(wall.exterior.coords)[:-1]
        ]

    def walls(self):

        # Blueprint matching the layout in image_de10e6.png
        walls_list = []

        walls_list.append(box(0, 0, self.board_width, self.linethickness))
        # Top rail
        walls_list.append(
            box(
                0,
                self.board_height - self.linethickness,
                self.board_width,
                self.board_height,
            )
        )
        # Left rail
        walls_list.append(box(0, 0, self.linethickness, self.board_height))
        # Right rail
        walls_list.append(
            box(
                self.board_width - self.linethickness,
                0,
                self.board_width,
                self.board_height,
            )
        )
        # Internal walls (coordinates scaled from original 33"×21" blueprint to 30"×22")
        walls_list.append(box(4.1, 0, 5.0, 11.0))
        walls_list.append(box(24.1, 0, 25.0, 17.8))
        walls_list.append(box(4.1, 10.0, 24.1, 11.0))
        walls_list.append(box(12.3, 11.0, 13.2, self.board_height - self.linethickness))
        walls_list.append(box(16.8, 11.0, 17.7, self.board_height - self.linethickness))

        walls_list.append(box(10.9, 3.1, 18.2, 4.2))

        return walls_list


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
