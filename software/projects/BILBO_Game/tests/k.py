import pygame

pygame.init()

WIDTH, HEIGHT = 800, 450
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Platformer Accel Camera Demo")
clock = pygame.time.Clock()

# colors
SKY = (20, 20, 40)
GROUND = (40, 200, 80)
PLAYER_COLOR = (240, 240, 240)
CENTER_LINE = (120, 120, 200)


class Player(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.image = pygame.Surface((40, 60))
        self.image.fill(PLAYER_COLOR)
        self.rect = self.image.get_rect(midbottom=(x, y))
        self.vel_x = 0.0

    def update(self, dt, keys):
        ACCEL = 1200  # pixels/s^2
        MAX_SPEED = 400  # pixels/s
        FRICTION = 12  # higher = stronger slowdown

        # horizontal acceleration
        if keys[pygame.K_LEFT]:
            self.vel_x -= ACCEL * dt
        if keys[pygame.K_RIGHT]:
            self.vel_x += ACCEL * dt

        # friction if no input
        if not keys[pygame.K_LEFT] and not keys[pygame.K_RIGHT]:
            self.vel_x *= max(0, 1 - FRICTION * dt)

        # clamp speed
        if self.vel_x > MAX_SPEED:
            self.vel_x = MAX_SPEED
        if self.vel_x < -MAX_SPEED:
            self.vel_x = -MAX_SPEED

        # integrate position
        self.rect.x += int(self.vel_x * dt)

        # simple floor
        if self.rect.bottom > HEIGHT - 40:
            self.rect.bottom = HEIGHT - 40


class Platform(pygame.sprite.Sprite):
    def __init__(self, x, y, w, h):
        super().__init__()
        self.image = pygame.Surface((w, h))
        self.image.fill(GROUND)
        self.rect = self.image.get_rect(topleft=(x, y))


# world
player = Player(100, HEIGHT - 40)
player_group = pygame.sprite.Group(player)

platforms = pygame.sprite.Group()
for i in range(20):
    platforms.add(Platform(i * 200, HEIGHT - 40, 200, 40))

# --- camera state ---

camera_x = 0.0

# we'll track a smoothed version of the player velocity
smoothed_vel_x = 0.0

# tuning parameters
VEL_SMOOTH_TAU = 0.5  # how slowly we follow the real velocity (seconds)
OFFSET_GAIN = 0.25  # how far from center we allow the player to get

running = True
while running:
    dt = clock.tick(60) / 1000.0

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    keys = pygame.key.get_pressed()
    if keys[pygame.K_ESCAPE]:
        running = False

    # --- update player ---
    player_group.update(dt, keys)

    # --- camera logic ---

    # ideal camera that keeps player centered
    base_target_x = player.rect.centerx - WIDTH // 2

    # 1) smooth version of player velocity (low-pass filter)
    #    this approximates "what the velocity was a moment ago"
    #    smoothed_v' = (v - smoothed_v) / tau
    smoothed_vel_x += (player.vel_x - smoothed_vel_x) * (dt / VEL_SMOOTH_TAU)

    # 2) "acceleration-ish" term: difference between current and smoothed vel
    dv = player.vel_x - smoothed_vel_x  # > 0 when speeding up to the right

    # 3) offset based on dv:
    #    when accelerating, this is non-zero; when speed is steady, it decays to 0
    camera_offset = OFFSET_GAIN * dv

    # camera lags behind when accelerating:
    #   - if dv > 0 (speeding up right), camera_offset > 0
    #     → camera_x is slightly smaller → player appears to the RIGHT of center
    #   - if dv < 0 (braking / reversing), player appears to the LEFT of center
    camera_x = base_target_x - camera_offset

    # --- draw ---
    screen.fill(SKY)

    # center line to visualize how far player is from perfect center
    pygame.draw.line(screen, CENTER_LINE,
                     (WIDTH // 2, 0), (WIDTH // 2, HEIGHT), 1)

    # draw platforms & player with camera offset
    for plat in platforms:
        screen.blit(plat.image, (plat.rect.x - camera_x, plat.rect.y))

    for spr in player_group:
        screen.blit(spr.image, (spr.rect.x - camera_x, spr.rect.y))

    # HUD
    font = pygame.font.SysFont("consolas", 20)
    text = font.render("←/→ accelerate • accel-based camera • ESC to quit",
                       True, (220, 220, 220))
    screen.blit(text, (20, 20))

    pygame.display.flip()

pygame.quit()
