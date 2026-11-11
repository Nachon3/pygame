import json
import math
import os
import random
import sys

import pygame

# -----------------------------------------------------------------------------

WIDTH, HEIGHT = 540, 720
FPS = 60
TOP_BAR = 42

HORIZON_Y = 250
ROAD_BOTTOM_Y = HEIGHT + 30
ROAD_TOP_HALF = 24
ROAD_BOTTOM_HALF = 240
WALL_H = 0.16
WALL_T = 0.07

PLAYER_DEPTH = 0.86
ROAD_SPEED = 0.22
SPAWN_DEPTH = 0.07
ENEMY_SPEED = 0.27
ENEMY_DRIFT = 0.12
ENEMY_W = 0.075
SPRITE_FRAME_SIZE = 32
SPRITE_FLOOR = 27
SPRITE_FPS = 5
GATE_H = 0.5
LANES = (-0.72, -0.36, 0.0, 0.36, 0.72)

EVENT_START_T = 1.0
EVENT_INTERVAL = 3.0
ROW_DELAY = 0.5

START_ARROWS = 10
MAX_ARROWS = 999
MAX_VISIBLE = 220

PLATFORM_FAR = 0.06
FINAL_STOP = 0.55
PLATFORM_SPEED = 0.22
PLATFORM_H = 0.22
COIN_COLOR = (255, 206, 62)
COIN_ROWS = ((6, -0.36), (12, 0.36), (17, 0.0),
             (24, 0.36), (30, -0.36), (35, 0.0))
SHOP_TIMES = (20, 38)
SHOP_COST = 3
SHOP_ARROWS = 15
FLIGHT_TIME = (0.5, 0.7)

SAVE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arrow_math_save.json")
GATE_EXP = 5
SMART_EXP = 10
DODGE_EXP = 10
KILL_EXP = 5
CLEAR_EXP_BASE = 40
CLEAR_EXP_PER_LEVEL = 10
UPGRADE_Y0, UPGRADE_H, UPGRADE_GAP = 190, 64, 8
UPGRADES = [
    {"key": "start", "name": "Starter Quiver", "max": 5, "desc": "+5 arrows at the start of every run"},
    {"key": "armor", "name": "Iron Fletching", "max": 5, "desc": "-12% arrows lost per enemy hit"},
    {"key": "gate", "name": "Math Genius", "max": 5, "desc": "+5% arrows after every good gate"},
    {"key": "steer", "name": "Swift Wind", "max": 5, "desc": "+10% steering speed"},
    {"key": "scholar", "name": "Scholar", "max": 5, "desc": "+15% EXP from everything"},
    {"key": "pierce", "name": "Piercing Shot", "max": 5, "desc": "+8% chance to deal 2 damage to the boss"},
]

WHITE = (250, 250, 250)
SHADOW_TXT = (20, 16, 30)
ROAD_A = (238, 242, 248)
ROAD_B = (228, 234, 244)
WALL_FACE_A = (92, 98, 116)
WALL_FACE_B = (84, 90, 108)
WALL_TOP = (156, 162, 178)
PLAT_FACE = (88, 94, 110)
PLAT_TOP = (168, 174, 190)
PLAT_TRIM = (124, 130, 146)
POLE = (70, 76, 94)
SHAFT = (244, 150, 40)
ARROW_RED = (226, 52, 84)
ARROW_DARK = (150, 26, 54)
CYAN = (60, 205, 235)
ENEMY_COLORS = ((250, 70, 150), (235, 55, 70), (255, 125, 40))
GOOD_TXT = (120, 215, 255)
BAD_TXT = (255, 110, 120)

LEVEL = [
    ("gate", ("x", 3), ("+", 20)),
    ("enemy", 2, 2),
    ("gate", ("+", 10), ("-", 10)),
    ("enemy", 2, 3),
    ("gate", ("x", 2), ("÷", 3)),
    ("enemy", 3, 2),
    ("gate", ("+", 50), ("x", 2)),
    ("enemy", 3, 3),
    ("gate", ("÷", 2), ("-", 20)),
    ("enemy", 4, 3),
    ("gate", ("x", 3), ("+", 100)),
    ("enemy", 5, 4),
    ("gate", ("÷", 2), ("-", 50)),
    ("final", ("x", 2), ("+", 30)),
]

# -----------------------------------------------------------------------------

def perspective(depth):
    """Return (screen_y, road_half_width) for a depth value."""
    depth = max(0.0, min(1.3, depth))
    curve = depth ** 1.65
    y = HORIZON_Y + (ROAD_BOTTOM_Y - HORIZON_Y) * curve
    half = ROAD_TOP_HALF + (ROAD_BOTTOM_HALF - ROAD_TOP_HALF) * curve
    return y, half


def project(world_x, depth):
    """World (x about -1..1, depth) -> (screen_x, screen_y, pixels_per_world_unit)."""
    y, half = perspective(depth)
    return WIDTH / 2 + world_x * half, y, half


def R(x, y, w, h):
    """Integer rect tuple, at least 1 pixel big."""
    return (int(x), int(y), max(1, int(w)), max(1, int(h)))


def apply_op(count, op):
    kind, value = op
    if kind == "+":
        count += value
    elif kind == "-":
        count -= value
    elif kind == "x":
        count *= value
    else:
        count = max(1, count // value) if count > 0 else 0
    return max(0, min(MAX_ARROWS, count))


def is_good(op):
    return op[0] in ("+", "x")


def op_text(op):
    return f"X{op[1]}" if op[0] == "x" else f"{op[0]}{op[1]}"


def clamp_step(current, target, max_step):
    return current + max(-max_step, min(max_step, target - current))


def shade(color, factor):
    return tuple(max(0, min(255, int(c * factor))) for c in color)


def arrow_colors(count):
    # Each set contains the shaft, fletching and arrowhead colors.
    if count >= 750:
        return (197, 128, 255), (154, 68, 225), (100, 40, 173)
    if count >= 500:
        return (255, 224, 106), (246, 186, 38), (177, 112, 12)
    if count >= 250:
        return (119, 235, 132), (47, 187, 87), (19, 119, 58)
    return SHAFT, ARROW_RED, ARROW_DARK


_shadow_cache = {}


def draw_shadow(surface, cx, cy, w, h):
    w, h = max(2, int(w)), max(2, int(h))
    if (w, h) not in _shadow_cache:
        shadow = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (60, 40, 70, 70), (0, 0, w, h))
        _shadow_cache[(w, h)] = shadow
    surface.blit(_shadow_cache[(w, h)], (int(cx - w / 2), int(cy - h / 2)))


def draw_text(surface, text, font, color, center, shadow=True):
    image = font.render(text, True, color)
    rect = image.get_rect(center=center)
    if shadow:
        surface.blit(font.render(text, True, SHADOW_TXT), rect.move(2, 2))
    surface.blit(image, rect)


def draw_text_at(surface, text, font, color, pos, anchor="center", shadow=True):
    """Like draw_text, but `anchor` can be any rect attribute (topleft, bottomright, ...)."""
    image = font.render(text, True, color)
    rect = image.get_rect(**{anchor: pos})
    if shadow:
        surface.blit(font.render(text, True, SHADOW_TXT), rect.move(2, 2))
    surface.blit(image, rect)


_label_cache = {}


def gate_label(font, text):
    """White text with a dark outline, rendered once and scaled every frame."""
    if text not in _label_cache:
        img = font.render(text, True, WHITE)
        dark = font.render(text, True, SHADOW_TXT)
        pad = 5
        label = pygame.Surface((img.get_width() + pad * 2, img.get_height() + pad * 2), pygame.SRCALPHA)
        for dx in (-3, 0, 3):
            for dy in (-3, 0, 3):
                label.blit(dark, (pad + dx, pad + dy))
        label.blit(img, (pad, pad))
        _label_cache[text] = label
    return _label_cache[text]


def draw_figure(surface, x, y, r, color, t, phase):
    """A capsule-shaped guard seen from the front. (x, y) is the point between its feet."""
    if r < 1.2:
        pygame.draw.rect(surface, color, R(x - r, y - 3.6 * r, 2 * r, 3.6 * r))
        return
    dark = shade(color, 0.62)
    light = shade(color, 1.25)
    bob = math.sin(t * 9 + phase) * 0.07 * r
    swing = math.sin(t * 9 + phase) * 0.2 * r
    draw_shadow(surface, x, y, 2.8 * r, 0.8 * r)
    pygame.draw.rect(surface, dark, R(x - 0.85 * r, y - 1.1 * r + swing, 0.75 * r, 1.1 * r), border_radius=max(1, int(0.3 * r)))
    pygame.draw.rect(surface, dark, R(x + 0.10 * r, y - 1.1 * r - swing, 0.75 * r, 1.1 * r), border_radius=max(1, int(0.3 * r)))
    pygame.draw.rect(surface, color, R(x - r, y - 4.0 * r + bob, 2 * r, 3.3 * r), border_radius=max(1, int(r)))
    pygame.draw.ellipse(surface, light, R(x - 0.72 * r, y - 3.6 * r + bob, 0.55 * r, 1.5 * r))
    pygame.draw.rect(surface, (34, 26, 44), R(x - 0.7 * r, y - 3.3 * r + bob, 1.4 * r, 0.5 * r),
                     border_radius=max(1, int(0.25 * r)))

# -----------------------------------------------------------------------------

class Gate:

    def __init__(self, left_op, right_op, final=False):
        self.ops = (left_op, right_op)
        self.final = final
        self.depth = SPAWN_DEPTH
        self.used = False

    def update(self, dt):
        self.depth += ROAD_SPEED * dt

    def draw(self, surface, game):
        y, half = perspective(self.depth)
        cx = WIDTH / 2
        h = GATE_H * half
        if self.final:
            top = GATE_H + 0.42
            for sign in (-1, 1):
                x1, x2 = cx + sign * 1.0 * half, cx + sign * 1.32 * half
                pygame.draw.rect(surface, WALL_FACE_A, R(min(x1, x2), y - top * half, abs(x2 - x1), top * half))
            pygame.draw.rect(surface, WALL_FACE_B, R(cx - 1.32 * half, y - top * half, 2.64 * half,
                                                     (top - GATE_H) * half))
            pygame.draw.rect(surface, WALL_TOP, R(cx - 1.32 * half, y - top * half - 0.05 * half,
                                                  2.64 * half, 0.05 * half))

        for side in (0, 1):
            op = self.ops[side]
            good = is_good(op)
            x1 = cx + (-0.97 if side == 0 else 0.03) * half
            x2 = cx + (-0.03 if side == 0 else 0.97) * half
            w = x2 - x1
            if w < 3 or h < 3:
                continue
            panel = pygame.transform.smoothscale(game.grad_blue if good else game.grad_red,
                                                 (max(1, int(w)), max(1, int(h))))
            if self.used:
                panel.set_alpha(90)
            surface.blit(panel, (int(x1), int(y - h)))

            label = gate_label(game.font_gate, op_text(op))
            scale = (h * 0.62) / label.get_height()
            if scale > 0.2:
                label = pygame.transform.smoothscale(
                    label, (max(1, int(label.get_width() * scale)), max(1, int(label.get_height() * scale))))
                surface.blit(label, label.get_rect(center=(int((x1 + x2) / 2), int(y - h * 0.5))))

        pole_w = max(2, 0.04 * half)
        for wx in (-1.0, 0.0, 1.0):
            pygame.draw.rect(surface, POLE, R(cx + wx * half - pole_w / 2, y - h * 1.12, pole_w, h * 1.12))


class Enemy:

    def __init__(self, wx, color):
        self.wx = wx
        self.depth = SPAWN_DEPTH
        self.color = color
        self.dead = False
        self.phase = random.uniform(0, math.tau)

    def update(self, dt, target_wx):
        self.depth += ENEMY_SPEED * dt
        self.wx = clamp_step(self.wx, target_wx, ENEMY_DRIFT * dt)

    def draw(self, surface, t, frames):
        sx, y, half = project(self.wx, self.depth)
        radius = ENEMY_W * half
        if not frames:
            draw_figure(surface, sx, y, radius, self.color, t, self.phase)
            return

        frame_index = int(t * SPRITE_FPS + self.phase) % len(frames)
        size = max(1, round(3.8 * radius))
        frame = pygame.transform.scale(frames[frame_index], (size, size))
        draw_shadow(surface, sx, y, 2.8 * radius, 0.8 * radius)
        # Anchor to the sheet's shared floor so the jumping frames stay airborne.
        surface.blit(frame, (round(sx - size / 2), round(y - SPRITE_FLOOR * size / SPRITE_FRAME_SIZE)))


def load_sprite_frames(filename, frame_size):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if not os.path.isfile(path):
        return ()
    sheet = pygame.image.load(path).convert_alpha()
    frames = []
    for x in range(0, sheet.get_width(), frame_size):
        frames.append(sheet.subsurface((x, 0, frame_size, frame_size)))
    return frames


class Coin:
    def __init__(self, wx, pickup_time):
        self.wx = wx
        # Starts offscreen and reaches the player at pickup_time.
        self.depth = PLAYER_DEPTH - ROAD_SPEED * pickup_time

    def draw(self, surface, t, frames):
        if self.depth < SPAWN_DEPTH:
            return
        x, y, half = project(self.wx, self.depth)
        if frames:
            frame = frames[int(t * 5) % len(frames)]
            size = max(1, round(0.29 * half))
            image = pygame.transform.scale(frame, (size, size))
            surface.blit(image, image.get_rect(center=(round(x), round(y - 0.12 * half))))
            return
        radius = max(2, round(0.055 * half))
        center = (round(x), round(y - 0.12 * half))
        pygame.draw.circle(surface, (143, 81, 15), center, radius + 1)
        pygame.draw.circle(surface, COIN_COLOR, center, radius)
        pygame.draw.circle(surface, (255, 243, 157), center, max(1, radius // 2), 1)


class Boss:
    def __init__(self, level):
        self.wx = 0.0
        self.depth_factor = 0.82
        # Use the old crowd size as HP to keep the arrow requirement familiar.
        self.max_hp = 9 * min(30, 6 + (3 * level) // 2)
        self.hp = self.max_hp

    def ground_pos(self, platform_depth):
        """Return the boss's feet position on top of the platform."""
        sx, y, half = project(self.wx, platform_depth * self.depth_factor)
        return sx, y - PLATFORM_H * half, half

    def draw(self, surface, platform_depth, t, frames):
        if self.hp <= 0:
            return
        x, y, half = self.ground_pos(platform_depth)
        draw_shadow(surface, x, y, 0.75 * half, 0.18 * half)
        if frames:
            frame = frames[int(t * 7) % len(frames)]
            size = max(1, round(1.44 * half))
            image = pygame.transform.scale(frame, (size, size))
            surface.blit(image, image.get_rect(midbottom=(round(x), round(y))))
            return
        dark = (75, 36, 96)
        body = (139, 65, 170)
        for side in (-1, 1):
            pygame.draw.polygon(surface, dark, [
                (x + side * 0.10 * half, y - 1.10 * half),
                (x + side * 0.28 * half, y - 1.44 * half),
                (x + side * 0.30 * half, y - 1.03 * half),
            ])
            pygame.draw.ellipse(surface, dark,
                                R(x + side * 0.17 * half - 0.10 * half,
                                  y - 0.22 * half, 0.20 * half, 0.22 * half))
        pygame.draw.rect(surface, body, R(x - 0.25 * half, y - 1.18 * half,
                                          0.50 * half, 1.08 * half),
                         border_radius=max(1, round(0.15 * half)))
        pygame.draw.rect(surface, dark, R(x - 0.19 * half, y - 1.01 * half,
                                          0.38 * half, 0.22 * half))
        for side in (-1, 1):
            pygame.draw.circle(surface, COIN_COLOR,
                               (round(x + side * 0.10 * half), round(y - 0.90 * half)),
                               max(1, round(0.038 * half)))


class FlyArrow:
    """An arrow flying from the bundle to the boss."""

    def __init__(self, wx0, d0, boss, colors):
        self.wx0 = wx0
        self.d0 = d0
        self.boss = boss
        self.shaft_color, self.tip_color, _ = colors
        self.t = 0.0
        self.dur = random.uniform(*FLIGHT_TIME)

    def update(self, dt):
        self.t += dt / self.dur

    def pos(self, platform_depth, t):
        wx = self.wx0 + (self.boss.wx - self.wx0) * t
        depth = self.d0 + (platform_depth * self.boss.depth_factor - self.d0) * t
        sx, y, half = project(wx, depth)
        height = 0.25 + (PLATFORM_H + 0.65 - 0.25) * t + 0.32 * math.sin(math.pi * t)
        return sx, y - height * half, half

    def draw(self, surface, platform_depth):
        t = min(1.0, self.t)
        x1, y1, half = self.pos(platform_depth, t)
        x0, y0, _ = self.pos(platform_depth, max(0.0, t - 0.08))
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        width = max(1, int(0.02 * half))
        if length < 1:
            pygame.draw.circle(surface, self.shaft_color, (int(x1), int(y1)), width)
            return
        ux, uy = dx / length, dy / length
        tail = (x1 - ux * max(length, 6), y1 - uy * max(length, 6))
        pygame.draw.line(surface, self.shaft_color, tail, (x1, y1), width + 1)
        hs = max(2.0, 0.045 * half)
        pygame.draw.polygon(surface, self.tip_color, [(x1 + ux * hs * 1.6, y1 + uy * hs * 1.6),
                                                 (x1 - uy * hs * 0.6, y1 + ux * hs * 0.6),
                                                 (x1 + uy * hs * 0.6, y1 - ux * hs * 0.6)])
        pygame.draw.line(surface, WHITE, tail, (tail[0] + ux * hs, tail[1] + uy * hs), 1)



class Squad:

    def __init__(self):
        self.reset()

    def reset(self):
        self.wx = 0.0
        self.count = START_ARROWS
        self.speed_mult = 1.0

    def bundle_radius(self):
        return 0.05 + 0.0105 * math.sqrt(min(self.count, MAX_VISIBLE))

    def width(self):
        return self.bundle_radius() * 0.9 + 0.02

    def update(self, dt):
        if pygame.mouse.get_pressed()[0]:
            half = perspective(PLAYER_DEPTH)[1]
            target = (pygame.mouse.get_pos()[0] - WIDTH / 2) / half
            self.wx = clamp_step(self.wx, target, 2.6 * self.speed_mult * dt)
        else:
            keys = pygame.key.get_pressed()
            direction = (int(bool(keys[pygame.K_RIGHT] or keys[pygame.K_d]))
                         - int(bool(keys[pygame.K_LEFT] or keys[pygame.K_a])))
            self.wx += direction * 1.6 * self.speed_mult * dt
        limit = max(0.45, 0.95 - self.bundle_radius() * 0.8)
        self.wx = max(-limit, min(limit, self.wx))

    def draw(self, surface, t):
        n = min(self.count, MAX_VISIBLE)
        if n <= 0:
            return
        shaft_color, fletching_color, head_color = arrow_colors(self.count)
        rad = self.bundle_radius()
        points = []
        for i in range(n):
            angle = i * 2.39996
            dist = math.sqrt((i + 0.5) / n) * rad
            points.append((PLAYER_DEPTH + math.sin(angle) * dist * 0.10, math.cos(angle) * dist, i))
        points.sort()

        sx, sy, half0 = project(self.wx, PLAYER_DEPTH)
        draw_shadow(surface, sx, sy + 0.02 * half0, 2.8 * rad * half0, 0.9 * rad * half0)

        for depth, ox, i in points:
            wx = self.wx + ox
            height = 0.20 + math.sin(t * 5 + i) * 0.012
            tail_x, tail_y, half = project(wx, depth)
            tip_x, tip_y, tip_half = project(wx, depth - 0.09)
            tail_y -= height * half
            tip_y -= height * tip_half
            dx, dy = tip_x - tail_x, tip_y - tail_y
            length = math.hypot(dx, dy)
            ux, uy = dx / length, dy / length
            width = max(2, int(0.022 * half))
            head_x = tip_x - ux * width * 3
            head_y = tip_y - uy * width * 3
            tail = (tail_x, tail_y)
            mid = (tail_x + dx * 0.35, tail_y + dy * 0.35)
            pygame.draw.line(surface, shaft_color, mid, (head_x, head_y), width)
            pygame.draw.line(surface, fletching_color, tail, mid, width + 1)
            pygame.draw.polygon(surface, head_color, [
                (tip_x, tip_y),
                (head_x - uy * width, head_y + ux * width),
                (head_x + uy * width, head_y - ux * width),
            ])


class Progress:

    def __init__(self):
        self.player_level = 1
        self.exp = 0.0
        self.points = 0
        self.level_no = 1
        self.levels = {u["key"]: 0 for u in UPGRADES}

    def exp_needed(self):
        return 80 + 40 * (self.player_level - 1)

    def add_exp(self, amount):
        """Add EXP (boosted by Scholar). Returns (exp_gained, player_levels_gained)."""
        gained = amount * self.exp_mult()
        self.exp += gained
        ups = 0
        while self.exp >= self.exp_needed():
            self.exp -= self.exp_needed()
            self.player_level += 1
            self.points += 1
            ups += 1
        return gained, ups

    def level_of(self, key):
        return self.levels.get(key, 0)

    def max_of(self, key):
        return next(u["max"] for u in UPGRADES if u["key"] == key)

    def cost(self, key):
        return self.level_of(key) + 1

    def is_maxed(self, key):
        return self.level_of(key) >= self.max_of(key)

    def can_buy(self, key):
        return not self.is_maxed(key) and self.points >= self.cost(key)

    def buy(self, key):
        if not self.can_buy(key):
            return False
        self.points -= self.cost(key)
        self.levels[key] += 1
        return True

    #upgrade effects
    def start_bonus(self):
        return 5 * self.level_of("start")

    def armor_factor(self):
        return 1.0 - 0.12 * self.level_of("armor")

    def gate_bonus(self):
        return 0.05 * self.level_of("gate")

    def steer_mult(self):
        return 1.0 + 0.10 * self.level_of("steer")

    def exp_mult(self):
        return 1.0 + 0.15 * self.level_of("scholar")

    def pierce_chance(self):
        return 0.08 * self.level_of("pierce")

    #saving / loading
    def save(self):
        data = {"player_level": self.player_level, "exp": round(self.exp, 2), "points": self.points,
                "level_no": self.level_no, "levels": self.levels}
        try:
            with open(SAVE_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except OSError:
            pass

    @classmethod
    def load(cls):
        progress = cls()
        try:
            with open(SAVE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            progress.player_level = max(1, int(data.get("player_level", 1)))
            progress.exp = max(0.0, float(data.get("exp", 0.0)))
            progress.points = max(0, int(data.get("points", 0)))
            progress.level_no = max(1, int(data.get("level_no", 1)))
            saved = data.get("levels", {})
            for u in UPGRADES:
                progress.levels[u["key"]] = max(0, min(u["max"], int(saved.get(u["key"], 0))))
        except (OSError, ValueError, TypeError, AttributeError):
            return cls()
        return progress

# -----------------------------------------------------------------------------

def make_backdrop():
    surf = pygame.Surface((WIDTH, HORIZON_Y + 1))
    stops = [(0.0, (206, 86, 170)), (0.55, (246, 146, 172)), (1.0, (255, 198, 128))]
    for y in range(HORIZON_Y + 1):
        ratio = y / HORIZON_Y
        for (r0, c0), (r1, c1) in zip(stops, stops[1:]):
            if r0 <= ratio <= r1:
                k = (ratio - r0) / (r1 - r0)
                color = tuple(int(c0[i] + (c1[i] - c0[i]) * k) for i in range(3))
                break
        pygame.draw.line(surf, color, (0, y), (WIDTH, y))

    clouds = pygame.Surface((WIDTH, HORIZON_Y + 1), pygame.SRCALPHA)
    for cx, cy, s in ((90, 110, 1.0), (300, 88, 1.35), (460, 130, 0.9), (190, 165, 0.7), (400, 190, 0.6)):
        for ox, oy, w, h in ((0, 0, 90, 26), (-30, 8, 70, 20), (36, 9, 74, 20), (4, -10, 56, 20)):
            pygame.draw.ellipse(clouds, (255, 190, 215, 150),
                                (int(cx + ox * s - w * s / 2), int(cy + oy * s - h * s / 2), int(w * s), int(h * s)))
    surf.blit(clouds, (0, 0))
    return surf

def make_ground():
    surf = pygame.Surface((WIDTH, HEIGHT - HORIZON_Y))
    top, bottom = (255, 206, 120), (238, 138, 50)
    span = HEIGHT - HORIZON_Y
    for y in range(span):
        k = y / span
        pygame.draw.line(surf, tuple(int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)), (0, y), (WIDTH, y))
    return surf

def make_gradient(color):
    surf = pygame.Surface((4, 64), pygame.SRCALPHA)
    for y in range(64):
        k = y / 63
        glow = shade(color, 1.0 + 0.35 * k)
        surf.fill((*glow, int(40 + 150 * k ** 1.3)), (0, y, 4, 1))
    return surf

N_BANDS = 22

def draw_road(surface, travel):

    cx = WIDTH / 2
    shift = (travel * N_BANDS) % 2.0
    for k in range(-2, N_BANDS + 1):
        d1 = max(0.0, min(1.0, (k + shift) / N_BANDS))
        d2 = max(0.0, min(1.0, (k + 1 + shift) / N_BANDS))
        if d2 - d1 < 1e-4:
            continue
        y1, h1 = perspective(d1)
        y2, h2 = perspective(d2)
        even = k % 2 == 0

        pygame.draw.polygon(surface, ROAD_A if even else ROAD_B,
                            [(cx - h1, y1), (cx + h1, y1), (cx + h2, y2), (cx - h2, y2)])
        face = WALL_FACE_A if even else WALL_FACE_B
        for sign in (-1, 1):
            xa, xb = cx + sign * h1, cx + sign * h2
            ta, tb = cx + sign * h1 * (1 + WALL_T), cx + sign * h2 * (1 + WALL_T)
            top_a, top_b = y1 - WALL_H * h1, y2 - WALL_H * h2
            pygame.draw.polygon(surface, face, [(xa, y1), (xb, y2), (xb, top_b), (xa, top_a)])
            pygame.draw.polygon(surface, WALL_TOP, [(xa, top_a), (xb, top_b), (tb, top_b), (ta, top_a)])

def draw_platform(surface, platform_depth, boss, t, boss_frames):
    cx = WIDTH / 2
    y_f, h_f = perspective(platform_depth)
    y_b, h_b = perspective(platform_depth * 0.10)
    width = 1.40
    top_f = y_f - PLATFORM_H * h_f
    top_b = y_b - PLATFORM_H * h_b
    pygame.draw.rect(surface, PLAT_FACE, R(cx - width * h_f, top_f, 2 * width * h_f, PLATFORM_H * h_f))
    pygame.draw.polygon(surface, PLAT_TOP, [(cx - width * h_f, top_f), (cx + width * h_f, top_f),
                                            (cx + width * h_b, top_b), (cx - width * h_b, top_b)])
    pygame.draw.line(surface, PLAT_TRIM, (cx - width * h_f, top_f), (cx + width * h_f, top_f),
                     max(1, int(0.02 * h_f)))
    boss.draw(surface, platform_depth, t, boss_frames)

# -----------------------------------------------------------------------------

class Game:
    def __init__(self):
        pygame.init()
        try:
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.SCALED)
        except pygame.error:
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Arrow Math Run - Pseudo 3D")
        self.clock = pygame.time.Clock()

        self.font_bar = pygame.font.Font(None, 28)
        self.font_pill = pygame.font.Font(None, 26)
        self.font_gate = pygame.font.Font(None, 96)
        self.font_big = pygame.font.Font(None, 60)
        self.font_title = pygame.font.Font(None, 68)
        self.font_normal = pygame.font.Font(None, 30)
        self.font_small = pygame.font.Font(None, 22)
        self.font_desc = pygame.font.Font(None, 22)
        for font in (self.font_bar, self.font_pill, self.font_gate, self.font_big, self.font_title,
                     self.font_small):
            font.set_bold(True)

        self.backdrop = make_backdrop()
        self.ground = make_ground()
        self.grad_blue = make_gradient((90, 190, 255))
        self.grad_red = make_gradient((255, 85, 110))
        self.slime_frames = load_sprite_frames("Slime.png", SPRITE_FRAME_SIZE)
        self.skeleton_frames = load_sprite_frames("Skeleton.png", SPRITE_FRAME_SIZE)
        self.skeleton_damage = 7
        self.coin_frames = load_sprite_frames("Coin_16.png", 32)
        self.coin_icon = None
        if self.coin_frames:
            coin_frame = self.coin_frames[0]
            coin_art = coin_frame.subsurface(coin_frame.get_bounding_rect())
            self.coin_icon = pygame.transform.scale(coin_art, (16, 16))
        self.boss_frames = load_sprite_frames("Boss_Idle.png", 64)
        shop_frames = load_sprite_frames("Shop.png", 64)
        self.shop_sprite = shop_frames[0] if shop_frames else None
        self.dim_light = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.dim_light.fill((0, 0, 0, 80))
        self.dim_dark = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.dim_dark.fill((0, 0, 0, 165))

        self.progress = Progress.load()
        self.squad = Squad()
        self.time = 0.0
        self.state = "start"
        self.result = ""
        self.upgrade_return = "start"
        self.upgrade_index = 0
        self.upgrade_msg = ""
        self.upgrade_msg_time = 0.0
        self.upgrade_button = pygame.Rect(0, 0, 210, 44)
        self.upgrade_button.center = (WIDTH // 2, 480)
        self.upgrade_back_button = pygame.Rect(0, 0, 150, 32)
        self.upgrade_back_button.center = (WIDTH // 2, HEIGHT - 20)
        self.shop_buy_button = pygame.Rect(130, 346, 280, 44)
        self.shop_continue_button = pygame.Rect(130, 400, 280, 44)
        self.reset()

    #  setup
    def reset(self):
        self.squad.reset()
        self.squad.count += self.progress.start_bonus()
        self.squad.speed_mult = self.progress.steer_mult()
        self.run_exp = 0.0
        self.run_levelups = 0
        self.banner_text = ""
        self.banner_time = 0.0
        self.gates = []
        self.enemies = []
        self.spawn_queue = []
        self.fly = []
        self.particles = []
        self.floaters = []
        self.level_time = 0.0
        self.travel = 0.0
        self.event_index = 0
        self.phase = "run"
        self.platform_depth = PLATFORM_FAR
        self.attack_delay = 0.0
        self.launch_accum = 0.0
        self.coins = 0
        self.road_coins = []
        for pickup_time, lane in COIN_ROWS:
            for i in range(3):
                self.road_coins.append(Coin(lane, pickup_time + i * 0.5))
        self.shop_index = 0
        self.shop_message = ""
        self.result = ""

        self.boss = Boss(self.progress.level_no)

        self.level = []
        for event in LEVEL:
            if event[0] in ("gate", "final"):
                ops = [event[1], event[2]]
                random.shuffle(ops)
                self.level.append((event[0], ops[0], ops[1]))
            else:
                self.level.append(event)

    def start(self):
        self.reset()
        self.state = "playing"

    def restart(self):
        if self.state == "won":
            self.progress.level_no += 1
            self.progress.save()
        self.start()

    def spawn_event(self, event):
        if event[0] in ("gate", "final"):
            self.gates.append(Gate(event[1], event[2], final=event[0] == "final"))
            return
        _, rows, per_row = event
        lvl = self.progress.level_no
        rows += (lvl - 1) // 5                                 # later levels send more rows...
        per_row = min(len(LANES), per_row + (lvl - 1) // 4)    # ...and more guards per row
        for r in range(rows):
            lanes = random.sample(LANES, per_row)
            entries = [(lane + random.uniform(-0.05, 0.05), random.choice(ENEMY_COLORS)) for lane in lanes]
            self.spawn_queue.append((self.level_time + r * ROW_DELAY, entries))

    #  effects 
    def burst(self, x, y, color, n=8):
        for _ in range(n):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(40, 170)
            self.particles.append([x, y, math.cos(angle) * speed, math.sin(angle) * speed,
                                   random.uniform(0.25, 0.5), color])

    def floater(self, text, x, y, color, small=False):
        self.floaters.append([text, x, y, 1.0, color, small])

#  EXP 
    def gain_exp(self, amount, pos=None, label=""):
        gained, ups = self.progress.add_exp(amount)
        self.run_exp += gained
        if ups:
            self.run_levelups += ups
            self.banner_text = f"LEVEL UP!  +{ups} skill point{'s' if ups > 1 else ''}"
            self.banner_time = 2.2
        if pos is not None:
            self.floater(f"{label}+{int(round(gained))} XP", pos[0], pos[1], (255, 215, 80), small=True)

    def hit_boss(self):
        if self.boss.hp <= 0:
            return
        damage = 1
        if random.random() < self.progress.pierce_chance():
            damage += 1
        damage = min(damage, self.boss.hp)
        self.boss.hp -= damage
        x, y, half = self.boss.ground_pos(self.platform_depth)
        self.burst(x, y - 0.65 * half, CYAN, 6)
        self.gain_exp(KILL_EXP * damage)

    def end_run(self, state, message):
        """Finish the run: pay the level-clear bonus, store the result and save progress."""
        if state == "won":
            self.gain_exp(CLEAR_EXP_BASE + CLEAR_EXP_PER_LEVEL * self.progress.level_no)
        self.state = state
        self.result = message
        self.progress.save()

    def update_effects(self, dt):
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0]
        for f in self.floaters:
            f[2] -= 45 * dt
            f[3] -= dt
        self.floaters = [f for f in self.floaters if f[3] > 0]
        self.banner_time = max(0.0, self.banner_time - dt)
        self.upgrade_msg_time = max(0.0, self.upgrade_msg_time - dt)

    #  gameplay 
    def update(self, dt):
        squad = self.squad
        squad.update(dt)

        if self.phase == "run":
            self.update_run(dt)
        elif self.phase == "approach":
            self.travel += ROAD_SPEED * dt
            self.platform_depth = min(FINAL_STOP, self.platform_depth + PLATFORM_SPEED * dt)
            if self.platform_depth >= FINAL_STOP:
                self.phase = "attack"
                self.attack_delay = 0.6
        else:
            self.update_attack(dt)

    def road_hit_damage(self):
        return 3 + int(self.travel / 2.2) * 2

    def update_run(self, dt):
        squad = self.squad
        self.level_time += dt
        self.travel += ROAD_SPEED * dt

        # Level script
        while (self.event_index < len(self.level)
               and self.level_time >= EVENT_START_T + self.event_index * EVENT_INTERVAL):
            self.spawn_event(self.level[self.event_index])
            self.event_index += 1
        while self.spawn_queue and self.spawn_queue[0][0] <= self.level_time:
            _, entries = self.spawn_queue.pop(0)
            for wx, color in entries:
                self.enemies.append(Enemy(wx, color))

        # Gates
        for gate in self.gates:
            gate.update(dt)
            if not gate.used and gate.depth >= PLAYER_DEPTH:
                gate.used = True
                chosen = gate.ops[0 if squad.wx < 0 else 1]
                other = gate.ops[1 if squad.wx < 0 else 0]
                before = squad.count
                squad.count = apply_op(before, chosen)
                smart = squad.count >= apply_op(before, other)       # did you pick the better gate?
                bonus = 0
                if is_good(chosen) and self.progress.gate_bonus() > 0:   # Math Genius upgrade
                    bonus = int(math.ceil(squad.count * self.progress.gate_bonus()))
                    squad.count = min(MAX_ARROWS, squad.count + bonus)
                sx, sy, half = project(squad.wx, PLAYER_DEPTH)
                text = op_text(chosen) + (f" (+{bonus})" if bonus else "")
                self.floater(text, sx, sy - 0.6 * half, GOOD_TXT if is_good(chosen) else BAD_TXT)
                self.gain_exp(GATE_EXP + (SMART_EXP if smart else 0), (sx, sy - 0.3 * half),
                              "Smart pick!  " if smart else "")
        self.gates = [g for g in self.gates if g.depth < 1.25]

        # Enemies
        for enemy in self.enemies:
            enemy.update(dt, squad.wx)
            if (not enemy.dead and abs(enemy.depth - PLAYER_DEPTH) < 0.04
                    and abs(enemy.wx - squad.wx) < ENEMY_W + squad.width()):
                enemy.dead = True
                base_cost = self.road_hit_damage()
                cost = max(1, int(round(base_cost * self.progress.armor_factor())))   # Iron Fletching
                arrows_lost = min(cost, squad.count)
                squad.count = max(0, squad.count - cost)
                sx, sy, half = project(enemy.wx, enemy.depth)
                self.burst(sx, sy - 2 * ENEMY_W * half, enemy.color, 10)
                if arrows_lost > 0:
                    self.floater(f"-{arrows_lost}", sx, sy - 0.5 * half, BAD_TXT)
        for enemy in self.enemies:                                   # guards that walked past you
            if not enemy.dead and enemy.depth >= 1.2:
                self.gain_exp(DODGE_EXP)
        self.enemies = [e for e in self.enemies if not e.dead and e.depth < 1.2]

        if squad.count <= 0:
            self.end_run("lost", "All your arrows are gone!")
            return

        self.update_coins(dt)
        if self.shop_index < len(SHOP_TIMES) and self.level_time >= SHOP_TIMES[self.shop_index]:
            self.shop_index += 1
            self.shop_message = ""
            self.state = "shop"
            return

        if (self.event_index >= len(self.level) and not self.gates
                        and not self.enemies and not self.spawn_queue):
                    self.phase = "approach"

    def update_attack(self, dt):
        squad = self.squad
        self.attack_delay -= dt

        # Reserve one point of HP per arrow already in flight.
        open_hits = self.boss.hp - len(self.fly)
        if self.attack_delay <= 0 and squad.count > 0 and open_hits > 0:
            self.launch_accum += max(30.0, squad.count / 1.2) * dt
            n = int(self.launch_accum)
            self.launch_accum -= n
            n = min(n, squad.count, open_hits)
            rad = squad.bundle_radius()
            for i in range(n):
                colors = arrow_colors(squad.count - i)
                self.fly.append(FlyArrow(squad.wx + random.uniform(-0.8, 0.8) * rad,
                                         PLAYER_DEPTH + random.uniform(-0.01, 0.01), self.boss, colors))
            squad.count -= n

        for arrow in self.fly:
            arrow.update(dt)
            if arrow.t >= 1.0:
                self.hit_boss()
        self.fly = [a for a in self.fly if a.t < 1.0]

        if self.boss.hp == 0:
            self.end_run("won", "Boss defeated!")
        elif self.attack_delay <= 0 and squad.count == 0 and not self.fly:
            self.end_run("lost", f"Out of arrows - boss has {self.boss.hp} HP left")

    def update_coins(self, dt):
        remaining = []
        for coin in self.road_coins:
            coin.depth += ROAD_SPEED * dt
            near_player = abs(coin.depth - PLAYER_DEPTH) < 0.04
            same_lane = abs(coin.wx - self.squad.wx) < self.squad.width() + 0.055
            if near_player and same_lane:
                self.coins += 1
                x, y, half = project(coin.wx, coin.depth)
                self.floater("+1 coin", x, y - 0.5 * half, COIN_COLOR, small=True)
            elif coin.depth < 1.2:
                remaining.append(coin)
        self.road_coins = remaining

    def buy_shop_arrows(self):
        if self.coins < SHOP_COST:
            self.shop_message = "Not enough coins"
        elif self.squad.count + SHOP_ARROWS > MAX_ARROWS:
            self.shop_message = "Not enough room for a full bundle"
        else:
            self.coins -= SHOP_COST
            self.squad.count += SHOP_ARROWS
            self.shop_message = f"+{SHOP_ARROWS} arrows!"

    def draw_coin_label(self, text, font, color, pos, anchor="center"):
        width, height = font.size(text)
        icon_space = 22 if self.coin_icon is not None else 0
        rect = pygame.Rect(0, 0, width + icon_space, max(height, 16))
        setattr(rect, anchor, pos)
        if self.coin_icon is not None:
            self.screen.blit(self.coin_icon, self.coin_icon.get_rect(midleft=rect.midleft))
        draw_text_at(self.screen, text, font, color,
                     (rect.left + icon_space, rect.centery), "midleft")

    def draw_shop(self):
        s = self.screen
        cx = WIDTH // 2
        s.blit(self.dim_dark, (0, 0))
        pygame.draw.rect(s, (48, 36, 78), (100, 144, 340, 352), border_radius=16)
        if self.shop_sprite is not None:
            s.blit(self.shop_sprite, self.shop_sprite.get_rect(midbottom=(cx, 211)))
        draw_text(s, "ARROW SHOP", self.font_big, COIN_COLOR, (cx, 233))
        self.draw_coin_label(f"Coins: {self.coins}    Arrows: {self.squad.count}",
                             self.font_normal, WHITE, (cx, 285))
        draw_text(s, self.shop_message, self.font_small, COIN_COLOR, (cx, 320))
        pygame.draw.rect(s, (40, 150, 100), self.shop_buy_button, border_radius=10)
        pygame.draw.rect(s, (96, 102, 132), self.shop_continue_button, border_radius=10)
        self.draw_coin_label(f"{SHOP_COST} coins / +{SHOP_ARROWS} arrows [Enter]",
                             self.font_small, WHITE, self.shop_buy_button.center)
        draw_text(s, "Continue [Space / Esc]", self.font_small, WHITE, self.shop_continue_button.center)

    def draw_road_shop(self):
        if self.shop_sprite is None or self.shop_index >= len(SHOP_TIMES):
            return
        seconds_left = SHOP_TIMES[self.shop_index] - self.level_time
        depth = PLAYER_DEPTH - seconds_left * ROAD_SPEED
        if depth < SPAWN_DEPTH:
            return
        x, y, half = project(1.10, depth)
        size = max(1, round(0.48 * half))
        image = pygame.transform.scale(self.shop_sprite, (size, size))
        self.screen.blit(image, image.get_rect(midbottom=(round(x), round(y))))

    #  drawing
    def draw(self):
        s = self.screen
        if self.state == "upgrade":
            self.draw_upgrade()
            return
        s.blit(self.backdrop, (0, 0))
        s.blit(self.ground, (0, HORIZON_Y))
        draw_road(s, self.travel)
        draw_platform(s, self.platform_depth, self.boss, self.time, self.boss_frames)
        if self.state == "playing" and self.phase == "run":
            self.draw_road_shop()

        items = [(g.depth, 0, g) for g in self.gates]
        items += [(e.depth, 1, e) for e in self.enemies]
        items += [(coin.depth, 3, coin) for coin in self.road_coins]
        items.append((PLAYER_DEPTH, 2, self.squad))
        items.sort(key=lambda item: item[0])
        enemy_frames = self.slime_frames
        if self.skeleton_frames and self.road_hit_damage() >= self.skeleton_damage:
            enemy_frames = self.skeleton_frames
        for _, kind, obj in items:
            if kind == 0:
                obj.draw(s, self)
            elif kind == 1:
                obj.draw(s, self.time, enemy_frames)
            elif kind == 3:
                obj.draw(s, self.time, self.coin_frames)
            elif self.squad.count > 0:
                obj.draw(s, self.time)

        for arrow in self.fly:
            arrow.draw(s, self.platform_depth)
        for x, y, vx, vy, life, color in self.particles:
            pygame.draw.circle(s, color, (int(x), int(y)), max(1, int(5 * life / 0.5)))
        for text, x, y, life, color, small in self.floaters:
            draw_text(s, text, self.font_pill if small else self.font_big, color, (int(x), int(y)))

        self.draw_hud()
        if self.banner_time > 0:
            draw_text(s, self.banner_text, self.font_big, (255, 215, 80), (WIDTH // 2, 235))
        self.draw_overlay()
        if self.state == "shop":
            self.draw_shop()

    def draw_hud(self):
        s = self.screen
        cx = WIDTH // 2
        pygame.draw.rect(s, (0, 0, 0), (0, 0, WIDTH, TOP_BAR))
        banner = self.font_bar.render("Use your math skills to multiply arrows", True, WHITE)
        if banner.get_width() > WIDTH - 16:
            ratio = (WIDTH - 16) / banner.get_width()
            banner = pygame.transform.smoothscale(banner, (WIDTH - 16, max(1, int(banner.get_height() * ratio))))
        s.blit(banner, banner.get_rect(center=(cx, TOP_BAR // 2)))

        level_pill = pygame.Rect(0, 0, 104, 26)
        level_pill.center = (cx, TOP_BAR + 22)
        pygame.draw.rect(s, (190, 105, 10), level_pill.move(0, 2), border_radius=13)
        pygame.draw.rect(s, (255, 170, 32), level_pill, border_radius=13)
        draw_text(s, f"Level {self.progress.level_no}", self.font_pill, WHITE, level_pill.center)

        count_pill = pygame.Rect(0, 0, 96, 26)
        count_pill.center = (cx, TOP_BAR + 54)
        pygame.draw.rect(s, (20, 150, 80), count_pill.move(0, 2), border_radius=13)
        pygame.draw.rect(s, (40, 220, 125), count_pill, border_radius=13)
        ix, iy = count_pill.left + 14, count_pill.centery
        pygame.draw.line(s, WHITE, (ix - 5, iy + 6), (ix + 6, iy - 5), 2)                    # arrow icon
        pygame.draw.polygon(s, WHITE, [(ix + 8, iy - 8), (ix + 1, iy - 6), (ix + 8, iy + 1)])
        draw_text(s, str(self.squad.count), self.font_pill, WHITE, (count_pill.centerx + 10, count_pill.centery))

        if self.state in ("playing", "shop"):
            self.draw_coin_label(f"Coins: {self.coins}", self.font_pill, COIN_COLOR,
                                 (WIDTH - 16, TOP_BAR + 12), "topright")
        if self.phase in ("approach", "attack"):
            boss_bar = pygame.Rect(cx - 94, TOP_BAR + 73, 188, 26)
            pygame.draw.rect(s, (95, 30, 64), boss_bar, border_radius=8)
            fill = int(boss_bar.width * self.boss.hp / self.boss.max_hp)
            if fill > 0:
                pygame.draw.rect(s, (235, 70, 100), (boss_bar.x, boss_bar.y, fill, boss_bar.height),
                                 border_radius=8)
            draw_text(s, f"BOSS HP {self.boss.hp}/{self.boss.max_hp}",
                      self.font_pill, WHITE, boss_bar.center)

        self.draw_exp_bar(pygame.Rect(18, HEIGHT - 24, WIDTH - 36, 12))

    def draw_exp_bar(self, rect):
        s = self.screen
        p = self.progress
        pygame.draw.rect(s, (30, 24, 44), rect.inflate(4, 4), border_radius=9)
        fill = int(rect.w * min(1.0, p.exp / p.exp_needed()))
        if fill > 0:
            pygame.draw.rect(s, (255, 205, 60), (rect.x, rect.y, fill, rect.h), border_radius=6)
        draw_text_at(s, f"LV {p.player_level}", self.font_small, WHITE, (rect.left, rect.top - 4), "bottomleft")
        draw_text_at(s, f"{int(p.exp)} / {p.exp_needed()} XP", self.font_small, WHITE,
                     (rect.right, rect.top - 4), "bottomright")

    def draw_upgrade_button(self):
        s = self.screen
        p = self.progress
        rect = self.upgrade_button
        base = (255, 170, 32) if p.points > 0 else (96, 102, 132)
        pygame.draw.rect(s, shade(base, 0.6), rect.move(0, 3), border_radius=14)
        pygame.draw.rect(s, base, rect, border_radius=14)
        draw_text(s, "UPGRADES  [U]", self.font_pill, WHITE, rect.center)
        if p.points > 0:                                       # red badge with the unspent points
            pygame.draw.circle(s, (235, 60, 80), (rect.right - 4, rect.top + 4), 12)
            draw_text(s, str(p.points), self.font_small, WHITE, (rect.right - 4, rect.top + 4), shadow=False)

    def draw_overlay(self):
        s = self.screen
        cx = WIDTH // 2
        p = self.progress
        if self.state == "start":
            s.blit(self.dim_light, (0, 0))
            draw_text(s, "ARROW MATH RUN", self.font_title, (255, 215, 80), (cx, 215))
            draw_text(s, "Steer: A / D, arrows, or drag the mouse", self.font_normal, WHITE, (cx, 290))
            draw_text(s, "Blue gates help, red gates hurt - do the math!", self.font_normal, WHITE, (cx, 325))
            draw_text(s, "Collect coins, buy arrows, and beat the boss!", self.font_normal, WHITE, (cx, 360))
            draw_text(s, f"Player level {p.player_level}    Skill points {p.points}", self.font_normal,
                      (255, 215, 80), (cx, 405))
            draw_text(s, "Press SPACE or click to start", self.font_normal, (110, 235, 160), (cx, 440))
            self.draw_upgrade_button()
        elif self.state in ("won", "lost"):
            s.blit(self.dim_dark, (0, 0))
            won = self.state == "won"
            draw_text(s, "LEVEL CLEARED!" if won else "DEFEATED", self.font_title,
                      (110, 235, 160) if won else (255, 110, 120), (cx, 175))
            draw_text(s, self.result, self.font_normal, WHITE, (cx, 232))
            draw_text(s, f"EXP earned: +{int(self.run_exp)}", self.font_normal, (255, 215, 80), (cx, 292))
            if self.run_levelups:
                draw_text(s, f"LEVEL UP!  You are now player level {p.player_level}", self.font_normal,
                          (110, 235, 160), (cx, 328))
            else:
                draw_text(s, f"Player level {p.player_level}", self.font_normal, WHITE, (cx, 328))
            draw_text(s, f"Skill points: {p.points}", self.font_normal, WHITE, (cx, 364))
            self.draw_upgrade_button()
            hint = "Press R for the next level" if won else "Press R to try again"
            draw_text(s, hint, self.font_normal, (255, 215, 80), (cx, 545))
            draw_text(s, "ESC to quit", self.font_normal, WHITE, (cx, 575))

    #  upgrades
    def upgrade_rect(self, index):
        return pygame.Rect(24, UPGRADE_Y0 + index * (UPGRADE_H + UPGRADE_GAP), WIDTH - 48, UPGRADE_H)

    def open_upgrade(self):
        if self.state in ("start", "won", "lost"):
            self.upgrade_return = self.state
            self.state = "upgrade"
            self.upgrade_index = 0
            self.upgrade_msg = ""
            self.upgrade_msg_time = 0.0

    def close_upgrade(self):
        self.state = self.upgrade_return

    def buy_selected_upgrade(self):
        key = UPGRADES[self.upgrade_index]["key"]
        if self.progress.buy(key):
            self.progress.save()
            self.upgrade_msg = f"{UPGRADES[self.upgrade_index]['name']} upgraded!"
        elif self.progress.is_maxed(key):
            self.upgrade_msg = "Already at max level"
        else:
            self.upgrade_msg = "Not enough skill points"
        self.upgrade_msg_time = 1.6

    def upgrade_key(self, key):
        if key in (pygame.K_ESCAPE, pygame.K_u, pygame.K_b):
            self.close_upgrade()
        elif key in (pygame.K_UP, pygame.K_w):
            self.upgrade_index = (self.upgrade_index - 1) % len(UPGRADES)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.upgrade_index = (self.upgrade_index + 1) % len(UPGRADES)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self.buy_selected_upgrade()

    def upgrade_hover(self, pos):
        for i in range(len(UPGRADES)):
            if self.upgrade_rect(i).collidepoint(pos):
                self.upgrade_index = i

    def upgrade_click(self, pos):
        if self.upgrade_back_button.collidepoint(pos):
            self.close_upgrade()
            return
        for i in range(len(UPGRADES)):
            if self.upgrade_rect(i).collidepoint(pos):
                self.upgrade_index = i
                self.buy_selected_upgrade()
                return

    def draw_upgrade(self):
        s = self.screen
        cx = WIDTH // 2
        p = self.progress
        s.fill((30, 22, 48))
        pygame.draw.rect(s, (48, 36, 78), (0, 0, WIDTH, 96))
        draw_text(s, "UPGRADES", self.font_title, (255, 215, 80), (cx, 48))
        draw_text(s, f"Skill points: {p.points}", self.font_normal,
                  (110, 235, 160) if p.points else WHITE, (cx, 126))
        self.draw_exp_bar(pygame.Rect(60, 166, WIDTH - 120, 12))

        for i, upgrade in enumerate(UPGRADES):
            key = upgrade["key"]
            rect = self.upgrade_rect(i)
            level = p.level_of(key)
            selected = i == self.upgrade_index
            pygame.draw.rect(s, (74, 56, 118) if selected else (46, 36, 72), rect, border_radius=12)
            if selected:
                pygame.draw.rect(s, (255, 205, 60), rect, 2, border_radius=12)
            draw_text_at(s, upgrade["name"], self.font_pill, WHITE, (rect.x + 14, rect.y + 8), "topleft")
            draw_text_at(s, upgrade["desc"], self.font_desc, (205, 195, 230), (rect.x + 14, rect.y + 36),
                         "topleft", shadow=False)
            for k in range(upgrade["max"]):                       # level pips
                px = rect.right - 18 - (upgrade["max"] - 1 - k) * 18
                if k < level:
                    pygame.draw.circle(s, (255, 205, 60), (px, rect.y + 20), 6)
                else:
                    pygame.draw.circle(s, (110, 96, 150), (px, rect.y + 20), 6, 2)
            if p.is_maxed(key):
                label, color = "MAX", (110, 235, 160)
            else:
                label, color = f"Cost: {p.cost(key)}", WHITE if p.can_buy(key) else (255, 120, 130)
            draw_text_at(s, label, self.font_small, color, (rect.right - 14, rect.bottom - 8),
                         "bottomright", shadow=False)

        if self.upgrade_msg_time > 0:
            draw_text(s, self.upgrade_msg, self.font_normal, (255, 215, 80), (cx, 640))
        draw_text(s, "UP / DOWN select   -   ENTER or click to buy", self.font_desc, (205, 195, 230),
                  (cx, 668), shadow=False)
        pygame.draw.rect(s, (96, 102, 132), self.upgrade_back_button, border_radius=12)
        draw_text(s, "BACK  [ESC]", self.font_small, WHITE, self.upgrade_back_button.center)

    def on_click(self, pos):
        if self.state == "upgrade":
            self.upgrade_click(pos)
        elif self.state == "shop":
            if self.shop_buy_button.collidepoint(pos):
                self.buy_shop_arrows()
            elif self.shop_continue_button.collidepoint(pos):
                self.state = "playing"
        elif self.state in ("start", "won", "lost"):
            if self.upgrade_button.collidepoint(pos):
                self.open_upgrade()
            elif self.state == "start":
                self.start()

    #  main loop
    def run(self):
        running = True
        while running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            self.time += dt

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if self.state == "upgrade":
                        self.upgrade_key(event.key)
                    elif self.state == "shop":
                        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            self.buy_shop_arrows()
                        elif event.key in (pygame.K_SPACE, pygame.K_ESCAPE):
                            self.state = "playing"
                    elif event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_u and self.state in ("start", "won", "lost"):
                        self.open_upgrade()
                    elif self.state == "start" and event.key == pygame.K_SPACE:
                        self.start()
                    elif self.state in ("won", "lost") and event.key in (pygame.K_r, pygame.K_SPACE):
                        self.restart()
                elif event.type == pygame.MOUSEMOTION and self.state == "upgrade":
                    self.upgrade_hover(event.pos)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.on_click(event.pos)
            if self.state == "playing":
                self.update(dt)
            self.update_effects(dt)

            self.draw()
            pygame.display.flip()

        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    Game().run()
