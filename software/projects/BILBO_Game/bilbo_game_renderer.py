import abc
import math
from typing import Any

import pygame
from pygame import Surface


# ------------------------------------------------------------------------------------------------------------------
class RenderedObject(pygame.sprite.Sprite):
    image: Surface

    def __init__(self, id: str, image: Surface, x: float = 0, y: float = 0):
        """
        x, y are interpreted as WORLD coordinates with:
        - origin at bottom-left
        - x to the right
        - y upwards
        and (x, y) is the BOTTOM-LEFT position of the object.
        """
        super().__init__()
        self.id = id
        self.image = image
        self.rect = self.image.get_rect()

        # Convert bottom-left (x, y) in world coordinates to world TOP-LEFT
        # because the rect logically holds a top-left point.
        world_top_left_y = y + self.rect.height
        self.rect.topleft = (x, world_top_left_y)


class Rectangle(RenderedObject):
    def __init__(self, id: str, x: float, y: float, width: int, height: int, color=(255, 0, 0)):
        # Create an image (this sprite’s visible surface)
        image = pygame.Surface((width, height))
        image.fill(color)

        # Call the parent class with bottom-left coordinates
        super().__init__(id, image, x, y)


# ------------------------------------------------------------------------------------------------------------------
class BILBO_Game_Renderer:
    screen: Surface
    objects: dict[str, RenderedObject]
    clock: pygame.time.Clock

    screen_width: float = 1000
    screen_height: float = 500

    _exit: bool = False

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("BILBO Game Renderer")
        self.clock = pygame.time.Clock()

        self.objects = {}

        # (world_x, world_y) of the LOWER-LEFT corner of the screen
        self.coordinate_position = (0, 0)  # default camera position

        # Example: rectangle at x=100, y=100
        rectangle1 = Rectangle("rectangle1", 2000, 100, 100, 30)
        self.add_object(rectangle1)

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self._task()

    # ------------------------------------------------------------------------------------------------------------------
    def add_object(self, obj: RenderedObject):
        if obj.id in self.objects:
            raise ValueError(f"Object with id {obj.id} already exists")
        self.objects[obj.id] = obj

    # ------------------------------------------------------------------------------------------------------------------
    def _task(self):
        while not self._exit:
            # --- handle events ---
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._exit = True

            # --- render ---
            self.render()
            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()

    # ------------------------------------------------------------------------------------------------------------------
    def world_to_screen(self, x_world: float, y_world: float) -> tuple[float, float]:
        """
        Convert world coordinates (origin bottom-left, y up) to screen coordinates
        (origin top-left, y down), honoring self.coordinate_position as the
        world coordinate at the LOWER-LEFT of the screen.
        """
        cx, cy = self.coordinate_position
        screen_x = x_world - cx
        screen_y = self.screen_height - (y_world - cy)
        return screen_x, screen_y

    # ------------------------------------------------------------------------------------------------------------------
    def draw_coordinates(self):
        grid_spacing = 50  # distance in pixels/world units between grid lines

        # colors
        grid_color = (220, 220, 220)
        axis_color = (0, 0, 0)
        text_color = (50, 50, 50)

        font = pygame.font.SysFont(None, 16)

        # Screen dimensions
        width = self.screen_width
        height = self.screen_height

        cx, cy = self.coordinate_position
        world_x_min = cx
        world_x_max = cx + width
        world_y_min = cy
        world_y_max = cy + height

        # --- Axes (world x=0 and y=0) ---
        # Vertical y-axis at world x = 0 (if visible)
        if world_x_min <= 0 <= world_x_max:
            axis_screen_x, _ = self.world_to_screen(0, world_y_min)
            pygame.draw.line(self.screen, axis_color, (axis_screen_x, 0), (axis_screen_x, height), 1)
        else:
            axis_screen_x = None

        # Horizontal x-axis at world y = 0 (if visible)
        if world_y_min <= 0 <= world_y_max:
            _, axis_screen_y = self.world_to_screen(world_x_min, 0)
            pygame.draw.line(self.screen, axis_color, (0, axis_screen_y), (width, axis_screen_y), 1)
        else:
            axis_screen_y = None

        # Label the world origin (0, 0) if it's on screen
        if axis_screen_x is not None and axis_screen_y is not None:
            origin_label = font.render("(0, 0)", True, text_color)
            self.screen.blit(origin_label, (axis_screen_x + 5, axis_screen_y - 15))

        # Also label the bottom-left corner with its world coordinates
        bottom_left_label = font.render(f"({int(cx)}, {int(cy)})", True, text_color)
        # bottom-left of the screen is at (0, height); place label slightly above
        self.screen.blit(bottom_left_label, (5, height - 20))

        # --- Vertical grid lines + x labels (world x) ---
        # Start at the first multiple of grid_spacing >= world_x_min
        if grid_spacing > 0:
            first_x_world = math.ceil(world_x_min / grid_spacing) * grid_spacing
        else:
            first_x_world = world_x_min

        x_world = first_x_world
        while x_world < world_x_max:
            screen_x, _ = self.world_to_screen(x_world, world_y_min)

            # Vertical line from top to bottom
            pygame.draw.line(self.screen, grid_color, (screen_x, 0), (screen_x, height), 1)

            # World x coordinate label
            label = font.render(str(int(x_world)), True, text_color)
            # place label slightly above the bottom of the screen
            self.screen.blit(label, (screen_x + 2, height - 20))

            x_world += grid_spacing

        # --- Horizontal grid lines + y labels (world y) ---
        if grid_spacing > 0:
            first_y_world = math.ceil(world_y_min / grid_spacing) * grid_spacing
        else:
            first_y_world = world_y_min

        y_world = first_y_world
        while y_world < world_y_max:
            _, screen_y = self.world_to_screen(world_x_min, y_world)

            pygame.draw.line(self.screen, grid_color, (0, screen_y), (width, screen_y), 1)

            label = font.render(str(int(y_world)), True, text_color)
            # place label a bit to the right of the left edge, slightly above the line
            self.screen.blit(label, (5, screen_y - 15))

            y_world += grid_spacing

    # ------------------------------------------------------------------------------------------------------------------
    def draw_grid(self):
        self.draw_coordinates()

    # ------------------------------------------------------------------------------------------------------------------
    def render(self):
        self.screen.fill((255, 255, 255))

        # draw grid & coordinate labels first
        self.draw_grid()

        for obj in self.objects.values():
            # rect.topleft currently stores WORLD top-left coordinates (origin bottom-left, y up)
            world_x_top, world_y_top = obj.rect.topleft

            # Convert world → screen using camera/coordinate_position
            screen_x, screen_y = self.world_to_screen(world_x_top, world_y_top)

            # Move a copy of the rect to screen position
            draw_rect = obj.rect.copy()
            draw_rect.topleft = (int(screen_x), int(screen_y))

            self.screen.blit(obj.image, draw_rect)


if __name__ == "__main__":
    renderer = BILBO_Game_Renderer()
    renderer.start()
