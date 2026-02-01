import pygame
import random
import math
import sys

# ----------------------------
# Crossy Road-like - One File (pygame)
# Features:
#  - Grid hopping (Frogger orientation: start bottom, move up)
#  - Grass + Roads with cars (cars enter from left only, lane speeds vary)
#  - Rivers as 2–3 lane segments, mixed by lane (pads/logs), never both in same lane
#  - Guaranteed solvable lily-pad route through each river segment
#  - Water death only evaluated after landing (no mid-hop drowning)
#  - Logs carry player sideways when standing on them
# ----------------------------

# ---------- Config ----------
SCREEN_W, SCREEN_H = 480, 720
FPS = 60

TILE = 48
COLS = SCREEN_W // TILE
SAFE_MARGIN_ROWS = 18

HOP_TIME = 0.12
PLAYER_SIZE = int(TILE * 0.70)

# Lane generation (for rows > 1)
PROB_ROAD = 0.45
PROB_RIVER_START = 0.25  # chance to start a 2–3 row river segment
MIN_GRASS_BETWEEN_HAZARDS = 1
MAX_CONSEC_ROADS = 3

# Road cars
CAR_H = int(TILE * 0.80)
CAR_MIN_W = int(TILE * 1.00)
CAR_MAX_W = int(TILE * 2.45)
CAR_MIN_SPEED = 120
CAR_MAX_SPEED = 320

# Road spawn fairness: distance gap in tiles -> time (by lane speed)
GAP_MIN_TILES = 2.6
GAP_MAX_TILES = 4.8
SPAWN_JITTER = 0.20

# River visuals / physics
WATER = (35, 90, 185)
WATER_DARK = (28, 74, 150)

LILYPAD = (70, 200, 120)
LILYPAD_DARK = (55, 170, 100)

LOG = (150, 95, 45)
LOG_DARK = (120, 75, 35)

LOG_H = int(TILE * 0.70)
LOG_MIN_W = int(TILE * 1.8)
LOG_MAX_W = int(TILE * 3.3)
LOG_MIN_SPEED = 60
LOG_MAX_SPEED = 170
LOG_GAP_MIN_TILES = 1.7
LOG_GAP_MAX_TILES = 3.3

# Colors
BG = (18, 18, 22)
GRASS = (60, 170, 80)
GRASS_DARK = (52, 150, 72)
ROAD = (45, 45, 52)
ROAD_EDGE = (35, 35, 42)
ROAD_LINE = (210, 210, 220)

PLAYER_COLOR = (240, 210, 60)
TEXT = (235, 235, 245)
DANGER = (235, 80, 90)

CAR_PALETTES = [
    ((210, 70, 80), (180, 55, 65), (230, 235, 245), (25, 25, 28)),
    ((80, 160, 220), (60, 130, 190), (230, 235, 245), (25, 25, 28)),
    ((245, 180, 60), (215, 155, 50), (230, 235, 245), (25, 25, 28)),
    ((170, 90, 210), (145, 75, 180), (230, 235, 245), (25, 25, 28)),
    ((90, 200, 140), (75, 170, 120), (230, 235, 245), (25, 25, 28)),
    ((230, 230, 235), (200, 200, 205), (60, 80, 105), (25, 25, 28)),
]

# ---------- Helpers ----------
def lerp(a, b, t):
    return a + (b - a) * t

def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

# Frogger-style mapping: bigger world_y => draw higher on screen
def world_y_to_screen(world_y, camera_y):
    anchor = int(SCREEN_H * 0.68)
    return int(anchor - (world_y - camera_y))


# ---------- Road Cars ----------
class Car:
    def __init__(self, x, w, speed, palette, kind):
        self.x = float(x)
        self.w = float(w)
        self.speed = float(speed)  # always left->right
        self.palette = palette
        self.kind = kind  # "car" or "truck"

    def rect_world(self, lane_y_world):
        y_top = lane_y_world + (TILE - CAR_H) * 0.5
        return pygame.Rect(int(self.x), int(y_top), int(self.w), int(CAR_H))

    def draw(self, surf, lane_y_screen):
        body, roof, window, wheel = self.palette
        y_top = lane_y_screen + (TILE - CAR_H) / 2.0
        r = pygame.Rect(int(self.x), int(y_top), int(self.w), int(CAR_H))

        pygame.draw.rect(surf, body, r, border_radius=10)

        roof_h = int(r.h * (0.45 if self.kind == "car" else 0.38))
        roof_w = int(r.w * (0.55 if self.kind == "car" else 0.50))
        roof_x = r.x + int(r.w * 0.22)
        roof_y = r.y + int(r.h * 0.10)
        roof_rect = pygame.Rect(roof_x, roof_y, roof_w, roof_h)
        pygame.draw.rect(surf, roof, roof_rect, border_radius=8)

        win_w = max(10, int(roof_rect.w * 0.40))
        win_h = max(8, int(roof_rect.h * 0.60))
        win_rect = pygame.Rect(roof_rect.x + 6, roof_rect.y + 4, win_w, win_h)
        pygame.draw.rect(surf, window, win_rect, border_radius=6)

        wheel_r = max(5, int(r.h * 0.18))
        wy = r.y + r.h - wheel_r - 2
        wx1 = r.x + int(r.w * 0.22)
        wx2 = r.x + int(r.w * 0.78)
        pygame.draw.circle(surf, wheel, (wx1, wy), wheel_r)
        pygame.draw.circle(surf, wheel, (wx2, wy), wheel_r)

        pygame.draw.line(
            surf,
            (15, 15, 18),
            (r.x + int(r.w * 0.92), r.y + 6),
            (r.x + int(r.w * 0.92), r.y + r.h - 6),
            2,
        )


# ---------- River Platforms ----------
class Log:
    def __init__(self, x, w, speed, direction):
        self.x = float(x)
        self.w = float(w)
        self.speed = float(speed)
        self.dir = int(direction)  # -1 left, +1 right

    def rect_world(self, lane_y_world):
        lane_center_y = lane_y_world + TILE * 0.5
        y_top = lane_center_y - LOG_H * 0.5
        return pygame.Rect(int(self.x), int(y_top), int(self.w), int(LOG_H))

    def draw(self, surf, lane_y_screen):
        y_top = lane_y_screen + (TILE - LOG_H) / 2.0
        r = pygame.Rect(int(self.x), int(y_top), int(self.w), int(LOG_H))

        pygame.draw.rect(surf, LOG, r, border_radius=10)
        stripe_count = max(2, int(r.w / 50))
        for i in range(stripe_count):
            sx = r.x + int((i + 1) * r.w / (stripe_count + 1))
            pygame.draw.line(surf, LOG_DARK, (sx, r.y + 6), (sx, r.y + r.h - 6), 2)
        pygame.draw.circle(surf, LOG_DARK, (r.x + 10, r.y + r.h // 2), 4)
        pygame.draw.circle(surf, LOG_DARK, (r.x + r.w - 10, r.y + r.h // 2), 4)


# ---------- Lane ----------
class Lane:
    def __init__(self, row_idx, lane_type, river_mode=None, route_col=None):
        self.row = row_idx
        self.type = lane_type  # "grass", "road", "river"
        self.river_mode = river_mode  # None, "pads", "logs"
        self.route_col = route_col    # only meaningful for river pad lanes

        # road
        self.cars = []
        self.road_speed = 0.0
        self.road_spawn_timer = 0.0
        self.road_next_spawn_time = 0.0

        # river
        self.logs = []
        self.log_dir = 1
        self.log_speed = 0.0
        self.log_spawn_timer = 0.0
        self.log_next_spawn_time = 0.0
        self.lilypads = []  # list of columns

        if self.type == "road":
            self._init_road()
        elif self.type == "river":
            if self.river_mode not in ("pads", "logs"):
                self.river_mode = random.choice(["pads", "logs"])
            self._init_river()

    # ----- Road -----
    def _calc_next_road_spawn_time(self):
        gap_tiles = random.uniform(GAP_MIN_TILES, GAP_MAX_TILES)
        gap_px = gap_tiles * TILE
        base_time = gap_px / max(1.0, self.road_speed)
        return max(0.28, base_time + random.uniform(-SPAWN_JITTER, SPAWN_JITTER))

    def _spawn_car_offscreen_left(self):
        kind = "truck" if random.random() < 0.28 else "car"
        palette = random.choice(CAR_PALETTES)
        w = random.uniform(TILE * 1.8, TILE * 2.6) if kind == "truck" else random.uniform(CAR_MIN_W, CAR_MAX_W)
        x = -w - random.uniform(TILE * 0.8, TILE * 2.4)
        self.cars.append(Car(x, w, self.road_speed, palette, kind))

    def _init_road(self):
        self.road_speed = random.uniform(CAR_MIN_SPEED, CAR_MAX_SPEED)
        self.road_next_spawn_time = random.uniform(0.35, 0.85)
        self.road_spawn_timer = 0.0

    def update_road(self, dt):
        for car in self.cars:
            car.x += car.speed * dt
        self.cars = [c for c in self.cars if c.x < SCREEN_W + c.w + TILE * 3]

        self.road_spawn_timer += dt
        if self.road_spawn_timer >= self.road_next_spawn_time:
            can_spawn = True
            if self.cars:
                leftmost = min(self.cars, key=lambda c: c.x)
                required_clear_px = random.uniform(TILE * 1.4, TILE * 2.8)
                if leftmost.x < required_clear_px:
                    can_spawn = False

            if can_spawn:
                self._spawn_car_offscreen_left()
                self.road_spawn_timer = 0.0
                self.road_next_spawn_time = self._calc_next_road_spawn_time()
            else:
                self.road_spawn_timer = min(self.road_spawn_timer, self.road_next_spawn_time - 0.15)

    # ----- River -----
    def _calc_next_log_spawn_time(self):
        gap_tiles = random.uniform(LOG_GAP_MIN_TILES, LOG_GAP_MAX_TILES)
        gap_px = gap_tiles * TILE
        base_time = gap_px / max(1.0, abs(self.log_speed))
        return max(0.35, base_time + random.uniform(-0.12, 0.12))

    def _spawn_log_offscreen(self):
        w = random.uniform(LOG_MIN_W, LOG_MAX_W)
        buffer_px = random.uniform(TILE * 0.6, TILE * 2.0)
        if self.log_dir == 1:
            x = -w - buffer_px
        else:
            x = SCREEN_W + buffer_px
        self.logs.append(Log(x, w, abs(self.log_speed), self.log_dir))

    def _init_river(self):
        if self.river_mode == "pads":
            # GUARANTEED solvable pad at route_col
            pads = []
            rc = self.route_col if self.route_col is not None else COLS // 2
            pads.append(rc)

            # add extra pads for variety
            cols = list(range(COLS))
            random.shuffle(cols)
            target_extra = random.randint(1, 3)
            for c in cols:
                if len(pads) >= 1 + target_extra:
                    break
                if all(abs(c - pc) >= 2 for pc in pads):
                    pads.append(c)

            self.lilypads = pads
            self.logs = []

        elif self.river_mode == "logs":
            self.lilypads = []
            self.log_dir = random.choice([-1, 1])
            self.log_speed = random.uniform(LOG_MIN_SPEED, LOG_MAX_SPEED) * self.log_dir
            self.log_spawn_timer = 0.0
            self.log_next_spawn_time = random.uniform(0.35, 0.85)

            # seed 0-2 logs offscreen so they enter naturally
            if random.random() < 0.85:
                self._spawn_log_offscreen()
                if random.random() < 0.45:
                    self.log_next_spawn_time = self._calc_next_log_spawn_time()

    def update_river_logs(self, dt):
        for log in self.logs:
            log.x += log.speed * log.dir * dt

        new_logs = []
        for log in self.logs:
            if log.dir == 1:
                if log.x < SCREEN_W + log.w + TILE * 3:
                    new_logs.append(log)
            else:
                if log.x + log.w > -TILE * 3:
                    new_logs.append(log)
        self.logs = new_logs

        self.log_spawn_timer += dt
        if self.log_spawn_timer >= self.log_next_spawn_time:
            can_spawn = True
            if self.logs:
                if self.log_dir == 1:
                    leftmost = min(self.logs, key=lambda l: l.x)
                    if leftmost.x < random.uniform(TILE * 1.0, TILE * 2.4):
                        can_spawn = False
                else:
                    rightmost = max(self.logs, key=lambda l: l.x + l.w)
                    if rightmost.x + rightmost.w > SCREEN_W - random.uniform(TILE * 1.0, TILE * 2.4):
                        can_spawn = False

            if can_spawn:
                self._spawn_log_offscreen()
                self.log_spawn_timer = 0.0
                self.log_next_spawn_time = self._calc_next_log_spawn_time()
            else:
                self.log_spawn_timer = min(self.log_spawn_timer, self.log_next_spawn_time - 0.12)

    def update(self, dt):
        if self.type == "road":
            self.update_road(dt)
        elif self.type == "river" and self.river_mode == "logs":
            self.update_river_logs(dt)

    def draw(self, surf, camera_y):
        lane_y_world = self.row * TILE
        lane_y_screen = world_y_to_screen(lane_y_world, camera_y)

        if lane_y_screen > SCREEN_H or lane_y_screen < -TILE:
            return

        if self.type == "grass":
            pygame.draw.rect(surf, GRASS, (0, lane_y_screen, SCREEN_W, TILE))
            for c in range(COLS):
                if (self.row + c) % 2 == 0:
                    pygame.draw.rect(surf, GRASS_DARK, (c * TILE, lane_y_screen, TILE, TILE))
            return

        if self.type == "road":
            pygame.draw.rect(surf, ROAD, (0, lane_y_screen, SCREEN_W, TILE))
            edge_h = int(TILE * 0.12)
            pygame.draw.rect(surf, ROAD_EDGE, (0, lane_y_screen, SCREEN_W, edge_h))
            pygame.draw.rect(surf, ROAD_EDGE, (0, lane_y_screen + TILE - edge_h, SCREEN_W, edge_h))

            center_y = lane_y_screen + TILE // 2
            for i in range(0, SCREEN_W, 28):
                if (i // 28) % 2 == 0:
                    pygame.draw.line(surf, ROAD_LINE, (i, center_y), (i + 14, center_y), 2)

            for car in self.cars:
                car.draw(surf, lane_y_screen)
            return

        if self.type == "river":
            pygame.draw.rect(surf, WATER, (0, lane_y_screen, SCREEN_W, TILE))
            band_h = max(6, TILE // 6)
            pygame.draw.rect(surf, WATER_DARK, (0, lane_y_screen, SCREEN_W, band_h))
            pygame.draw.rect(surf, WATER_DARK, (0, lane_y_screen + TILE - band_h, SCREEN_W, band_h))

            if self.river_mode == "pads":
                for col in self.lilypads:
                    cx = col * TILE + TILE // 2
                    cy = lane_y_screen + TILE // 2
                    r = int(TILE * 0.34)
                    pygame.draw.circle(surf, LILYPAD, (cx, cy), r)
                    pygame.draw.circle(surf, LILYPAD_DARK, (cx + 6, cy - 4), int(r * 0.35))

            elif self.river_mode == "logs":
                for log in self.logs:
                    log.draw(surf, lane_y_screen)


# ---------- Player ----------
class Player:
    def __init__(self):
        self.reset()

    def reset(self):
        self.x = float((COLS // 2) * TILE + TILE // 2)
        self.row = 0
        self.dead = False

        self.moving = False
        self.start_x = self.x
        self.start_row = self.row
        self.target_x = self.x
        self.target_row = self.row
        self.t = 0.0

        self.max_row = 0

    def current_col(self):
        return int(self.x // TILE)

    def try_move(self, dcol, drow):
        if self.dead or self.moving:
            return
        col = self.current_col()
        new_col = col + dcol
        new_row = self.row + drow
        if new_col < 0 or new_col >= COLS:
            return
        if new_row < -3:
            return

        self.moving = True
        self.t = 0.0
        self.start_x, self.start_row = self.x, self.row
        self.target_x = new_col * TILE + TILE // 2
        self.target_row = new_row

    def update(self, dt):
        if self.dead:
            return
        if self.moving:
            self.t += dt / HOP_TIME
            if self.t >= 1.0:
                self.t = 1.0
                self.moving = False
                self.x = float(self.target_x)
                self.row = self.target_row
                if self.row > self.max_row:
                    self.max_row = self.row

    def world_pos(self):
        if not self.moving:
            return self.x, (self.row * TILE + TILE // 2)

        t = clamp(self.t, 0.0, 1.0)
        ease = t * t * (3 - 2 * t)

        x = lerp(self.start_x, self.target_x, ease)
        y0 = self.start_row * TILE + TILE // 2
        y1 = self.target_row * TILE + TILE // 2
        y = lerp(y0, y1, ease)

        arc = math.sin(ease * math.pi) * (TILE * 0.18)
        y += arc
        return x, y

    def hitbox_world(self):
        x, y = self.world_pos()
        return pygame.Rect(int(x - PLAYER_SIZE // 2), int(y - PLAYER_SIZE // 2),
                           int(PLAYER_SIZE), int(PLAYER_SIZE))

    def draw(self, surf, camera_y):
        hb = self.hitbox_world()
        hb.y = world_y_to_screen(hb.y, camera_y)
        pygame.draw.rect(surf, PLAYER_COLOR, hb, border_radius=10)
        eye_y = hb.y + 12
        pygame.draw.circle(surf, (20, 20, 22), (hb.x + 14, eye_y), 3)
        pygame.draw.circle(surf, (20, 20, 22), (hb.x + hb.w - 14, eye_y), 3)


# ---------- World ----------
class World:
    def __init__(self):
        self.lanes = {}
        self.min_row = 0
        self.max_row = 0

        self._consec_roads = 0
        self._grass_since_hazard = 999

        # River segment control: queue of modes and a guaranteed route column
        self._river_modes_queue = []
        self._river_route_col = None

    def reset(self):
        self.lanes.clear()
        self.min_row = -6
        self.max_row = 18

        self._consec_roads = 0
        self._grass_since_hazard = 999
        self._river_modes_queue = []
        self._river_route_col = None

        for r in range(self.min_row, self.max_row + 1):
            if r <= 1:
                self.lanes[r] = Lane(r, "grass", None, None)
            else:
                lane_type, river_mode, route_col = self._choose_lane()
                self.lanes[r] = Lane(r, lane_type, river_mode, route_col)

    def _start_river_segment(self):
        length = random.choice([2, 3])
        # Mixed rivers by lane (never within lane):
        # 2 rows: pads -> logs
        # 3 rows: pads -> logs -> pads
        self._river_modes_queue = ["pads", "logs"] if length == 2 else ["pads", "logs", "pads"]

        self._river_route_col = COLS // 2 + random.choice([-1, 0, 1])
        self._river_route_col = max(0, min(COLS - 1, self._river_route_col))

    def _choose_lane(self):
        # If mid river segment, pop next river mode
        if self._river_modes_queue:
            mode = self._river_modes_queue.pop(0)

            # gentle drift so path isn't perfectly vertical
            drift = random.choice([-1, 0, 0, 1])
            self._river_route_col = max(0, min(COLS - 1, self._river_route_col + drift))

            self._grass_since_hazard = 0
            self._consec_roads = 0
            return "river", mode, self._river_route_col

        # grass buffer
        if self._grass_since_hazard < MIN_GRASS_BETWEEN_HAZARDS:
            self._grass_since_hazard += 1
            self._consec_roads = 0
            return "grass", None, None

        # cap consecutive roads
        if self._consec_roads >= MAX_CONSEC_ROADS:
            self._consec_roads = 0
            self._grass_since_hazard = 0
            return "grass", None, None

        roll = random.random()

        # start river segment
        if roll < PROB_RIVER_START:
            self._start_river_segment()
            mode = self._river_modes_queue.pop(0)
            self._grass_since_hazard = 0
            self._consec_roads = 0
            return "river", mode, self._river_route_col

        # road
        if roll < PROB_RIVER_START + PROB_ROAD:
            self._consec_roads += 1
            self._grass_since_hazard = 0
            return "road", None, None

        # grass
        self._consec_roads = 0
        self._grass_since_hazard += 1
        return "grass", None, None

    def ensure_rows(self, player_row):
        target_min = player_row - SAFE_MARGIN_ROWS
        target_max = player_row + SAFE_MARGIN_ROWS

        while self.max_row < target_max:
            self.max_row += 1
            lane_type, river_mode, route_col = self._choose_lane()
            self.lanes[self.max_row] = Lane(self.max_row, lane_type, river_mode, route_col)

        while self.min_row > target_min:
            self.min_row -= 1
            self.lanes[self.min_row] = Lane(self.min_row, "grass", None, None)

        prune_below = player_row - (SAFE_MARGIN_ROWS + 6)
        prune_above = player_row + (SAFE_MARGIN_ROWS + 10)
        for r in list(self.lanes.keys()):
            if r < prune_below or r > prune_above:
                del self.lanes[r]

        self.min_row = min(self.lanes.keys())
        self.max_row = max(self.lanes.keys())

    def update(self, dt):
        for lane in self.lanes.values():
            lane.update(dt)

    def draw(self, surf, camera_y):
        surf.fill(BG)
        for r in sorted(self.lanes.keys()):
            self.lanes[r].draw(surf, camera_y)

    def lane_at(self, row):
        return self.lanes.get(row)


# ---------- Game ----------
def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Crossy Road-like - pygame (Solvable Rivers)")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 22)
    font_big = pygame.font.SysFont("consolas", 34)

    world = World()
    player = Player()
    world.reset()

    camera_y = player.row * TILE

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

        # --- Events ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

                if player.dead:
                    if event.key in (pygame.K_r, pygame.K_RETURN, pygame.K_SPACE):
                        player.reset()
                        world.reset()
                        camera_y = player.row * TILE
                    continue

                if event.key in (pygame.K_w, pygame.K_UP):
                    player.try_move(0, 1)
                elif event.key in (pygame.K_s, pygame.K_DOWN):
                    player.try_move(0, -1)
                elif event.key in (pygame.K_a, pygame.K_LEFT):
                    player.try_move(-1, 0)
                elif event.key in (pygame.K_d, pygame.K_RIGHT):
                    player.try_move(1, 0)

        # --- Update ---
        world.ensure_rows(player.row)
        world.update(dt)
        player.update(dt)

        target_cam_y = player.row * TILE
        camera_y = lerp(camera_y, target_cam_y, 1 - math.pow(0.001, dt))

        # --- Hazards ---
        # IMPORTANT: drowning/carry is only resolved AFTER landing (no mid-hop drown).
        if not player.dead:
            lane = world.lane_at(player.row)
            if lane:
                lane_y_world = lane.row * TILE
                hb = player.hitbox_world()

                # Road collision only after landing (consistency and fairness)
                if lane.type == "road":
                    if not player.moving:
                        for car in lane.cars:
                            if hb.colliderect(car.rect_world(lane_y_world)):
                                player.dead = True
                                break

                # River: must be on platform; logs carry after landing
                elif lane.type == "river":
                    if not player.moving:
                        on_platform = False
                        carry_dx = 0.0

                        px, py = player.world_pos()

                        if lane.river_mode == "pads":
                            pad_r = TILE * 0.34
                            for col in lane.lilypads:
                                cx = col * TILE + TILE * 0.5
                                cy = lane_y_world + TILE * 0.5
                                if (px - cx) ** 2 + (py - cy) ** 2 <= (pad_r * 0.92) ** 2:
                                    on_platform = True
                                    break

                        elif lane.river_mode == "logs":
                            for log in lane.logs:
                                if hb.colliderect(log.rect_world(lane_y_world)):
                                    on_platform = True
                                    carry_dx = log.speed * log.dir * dt
                                    break

                        if on_platform:
                            if carry_dx != 0.0:
                                player.x += carry_dx
                            if player.x < 0 or player.x > SCREEN_W:
                                player.dead = True
                        else:
                            player.dead = True

        # --- Draw ---
        world.draw(screen, camera_y)
        player.draw(screen, camera_y)

        score = max(0, player.max_row)
        screen.blit(font.render(f"Score: {score}", True, TEXT), (12, 10))

        if player.dead:
            overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 130))
            screen.blit(overlay, (0, 0))
            msg = font_big.render("RIP!", True, DANGER)
            msg2 = font.render("Press R / Enter / Space to restart", True, TEXT)
            screen.blit(msg, (SCREEN_W // 2 - msg.get_width() // 2, SCREEN_H // 2 - 40))
            screen.blit(msg2, (SCREEN_W // 2 - msg2.get_width() // 2, SCREEN_H // 2 + 10))

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
