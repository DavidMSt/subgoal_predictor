import pygame
import random
import math

pygame.init()

# --- Config ---
WIDTH, HEIGHT = 960, 540
FPS = 60

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Sci-Fi Hover Bot - Pygame Demo")
clock = pygame.time.Clock()

# --- Colors ---
SPACE_DARK = (5, 5, 20)
NEON_CYAN = (0, 255, 255)
NEON_MAGENTA = (255, 0, 150)
NEON_PURPLE = (170, 0, 255)
NEON_YELLOW = (255, 255, 0)
CITY_DARK = (10, 10, 40)
WHITE = (255, 255, 255)


# --- Helpers to create simple "sprites" procedurally ---

def make_glow_circle(radius, color):
    """Create a glowing circle using multiple alpha layers."""
    size = radius * 4
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = cy = size // 2

    # outer soft glow
    for i in range(6, 0, -1):
        r = int(radius * (1 + i * 0.3))
        alpha = max(10, 40 - i * 6)
        pygame.draw.circle(surf, (*color, alpha), (cx, cy), r)

    # solid core
    pygame.draw.circle(surf, (*color, 255), (cx, cy), radius)
    return surf


def make_hover_bot():
    """Return a Surface of a tiny sci-fi hover robot."""
    w, h = 80, 100
    surf = pygame.Surface((w, h), pygame.SRCALPHA)

    # body
    body_rect = pygame.Rect(0, 0, 50, 60)
    body_rect.center = (w // 2, h // 2)
    pygame.draw.rect(surf, CITY_DARK, body_rect, border_radius=12)
    pygame.draw.rect(surf, NEON_CYAN, body_rect, width=3, border_radius=12)

    # eye visor
    visor_rect = pygame.Rect(0, 0, 36, 16)
    visor_rect.center = (w // 2, h // 2 - 5)
    pygame.draw.rect(surf, (5, 5, 30), visor_rect, border_radius=8)
    pygame.draw.rect(surf, NEON_MAGENTA, visor_rect, width=2, border_radius=8)

    # eyes
    eye_y = visor_rect.centery
    pygame.draw.circle(surf, NEON_CYAN, (visor_rect.left + 10, eye_y), 4)
    pygame.draw.circle(surf, NEON_CYAN, (visor_rect.right - 10, eye_y), 4)

    # antenna
    pygame.draw.line(
        surf, NEON_PURPLE,
        (body_rect.centerx, body_rect.top),
        (body_rect.centerx, body_rect.top - 15),
        2
    )
    pygame.draw.circle(
        surf, NEON_YELLOW,
        (body_rect.centerx, body_rect.top - 18),
        4
    )

    # hover ring
    ring_rect = pygame.Rect(0, 0, 50, 12)
    ring_rect.center = (w // 2, body_rect.bottom + 10)
    pygame.draw.ellipse(surf, (0, 0, 0, 120), ring_rect)
    pygame.draw.ellipse(surf, NEON_CYAN, ring_rect, 2)

    return surf


def make_platform(width=160, height=26):
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    base_rect = pygame.Rect(0, 0, width, height)
    pygame.draw.rect(surf, CITY_DARK, base_rect, border_radius=12)
    pygame.draw.rect(surf, NEON_PURPLE, base_rect, width=3, border_radius=12)

    # neon stripes
    stripe_color = (40, 40, 90)
    for i in range(3):
        stripe_rect = pygame.Rect(
            8 + i * (width // 3),
            6,
            width // 4,
            height - 12
        )
        pygame.draw.rect(surf, stripe_color, stripe_rect, border_radius=8)

    # glowing dots
    for x in range(12, width, 24):
        pygame.draw.circle(surf, NEON_CYAN, (x, height - 6), 3)

    return surf


# --- Classes ---

class StarLayer:
    def __init__(self, count, speed, color):
        self.speed = speed
        self.color = color
        self.stars = []
        for _ in range(count):
            x = random.randrange(0, WIDTH)
            y = random.randrange(0, HEIGHT)
            size = random.choice((1, 2, 2, 3))
            self.stars.append([x, y, size])

    def update(self, dt):
        for star in self.stars:
            star[0] -= self.speed * dt
            if star[0] < 0:
                star[0] = WIDTH
                star[1] = random.randrange(0, HEIGHT)

    def draw(self, surf):
        for x, y, size in self.stars:
            pygame.draw.circle(surf, self.color, (int(x), int(y)), size)


class CityScape:
    def __init__(self):
        self.buildings = []
        for _ in range(40):
            w = random.randint(40, 120)
            h = random.randint(80, 260)
            x = random.randint(0, WIDTH)
            y = HEIGHT - h
            self.buildings.append(pygame.Rect(x, y, w, h))

    def draw(self, surf, offset_x):
        for b in self.buildings:
            rect = b.copy()
            rect.x += int(offset_x * 0.4)
            pygame.draw.rect(surf, CITY_DARK, rect)
            # windows
            for wx in range(rect.x + 6, rect.right - 6, 12):
                for wy in range(rect.y + 8, rect.bottom - 10, 16):
                    if random.random() < 0.4:
                        pygame.draw.rect(surf, NEON_YELLOW, (wx, wy, 6, 10))


class HoverBot(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.base_image = make_hover_bot()
        self.image = self.base_image
        self.rect = self.image.get_rect(center=(x, y))
        self.vel = pygame.math.Vector2(0, 0)
        self.hover_phase = 0.0

    def update(self, dt, keys):
        accel = 900
        max_speed = 260

        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            self.vel.x -= accel * dt
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            self.vel.x += accel * dt
        if not (keys[pygame.K_a] or keys[pygame.K_LEFT] or
                keys[pygame.K_d] or keys[pygame.K_RIGHT]):
            # horizontal damping
            self.vel.x *= (1 - 4 * dt)

        # clamp speed
        if self.vel.length() > max_speed:
            self.vel.scale_to_length(max_speed)

        # apply velocity
        self.rect.centerx += int(self.vel.x * dt)

        # hover motion
        self.hover_phase += dt * 4.0
        hover_offset = math.sin(self.hover_phase) * 6
        self.rect.centery = HEIGHT // 2 + int(hover_offset)

        # keep on screen
        self.rect.centerx = max(60, min(WIDTH - 60, self.rect.centerx))

        # tilt based on velocity
        angle = -self.vel.x * 0.06
        angle = max(-18, min(18, angle))
        self.image = pygame.transform.rotate(self.base_image, angle)
        self.rect = self.image.get_rect(center=self.rect.center)


class Platform(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.image = make_platform()
        self.rect = self.image.get_rect(center=(x, y))


# --- Scene setup ---

star_layer_far = StarLayer(80, speed=20, color=(80, 80, 120))
star_layer_mid = StarLayer(55, speed=40, color=(120, 120, 255))
star_layer_near = StarLayer(25, speed=70, color=(200, 200, 255))

city = CityScape()
city_scroll = 0.0

# glow orbs in the sky
orbs = []
for _ in range(4):
    radius = random.randint(20, 40)
    color = random.choice([NEON_CYAN, NEON_MAGENTA, NEON_PURPLE])
    surf = make_glow_circle(radius, color)
    rect = surf.get_rect(
        center=(
            random.randint(80, WIDTH - 80),
            random.randint(60, HEIGHT // 2 - 40),
        )
    )
    speed = random.uniform(10, 30)
    orbs.append((surf, rect, speed))

bot = HoverBot(WIDTH // 2, HEIGHT // 2)
platforms = pygame.sprite.Group()
for i in range(5):
    px = 140 + i * 160
    py = HEIGHT - 80 - (i % 2) * 25
    platforms.add(Platform(px, py))

all_sprites = pygame.sprite.Group()
all_sprites.add(bot, *platforms)

font = pygame.font.SysFont("consolas", 22)

# --- Main loop ---

running = True
while running:
    dt = clock.tick(FPS) / 1000.0

    # events
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            running = False

    keys = pygame.key.get_pressed()

    # update
    star_layer_far.update(dt)
    star_layer_mid.update(dt)
    star_layer_near.update(dt)

    city_scroll -= 40 * dt
    if city_scroll < -WIDTH:
        city_scroll = 0

    # move orbs slowly
    updated_orbs = []
    for surf_o, rect_o, speed in orbs:
        rect_o.x -= int(speed * dt)
        if rect_o.right < 0:
            rect_o.x = WIDTH + random.randint(0, 200)
            rect_o.y = random.randint(60, HEIGHT // 2 - 40)
        updated_orbs.append((surf_o, rect_o, speed))
    orbs = updated_orbs

    all_sprites.update(dt, keys)

    # draw background
    screen.fill(SPACE_DARK)
    star_layer_far.draw(screen)
    star_layer_mid.draw(screen)

    # cityscape
    city.draw(screen, city_scroll)

    # near stars and orbs on top of city
    star_layer_near.draw(screen)
    for surf_o, rect_o, _ in orbs:
        screen.blit(surf_o, rect_o)

    # draw sprites
    platforms.draw(screen)
    all_sprites.draw(screen)

    # UI text
    text = font.render("A/D or ←/→ to move • ESC to quit", True, NEON_CYAN)
    screen.blit(text, (20, 20))

    pygame.display.flip()

pygame.quit()
