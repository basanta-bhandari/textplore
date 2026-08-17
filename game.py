#!/usr/bin/env python3
"""
HOMEWARD -> SANDBOX (v5)
Real 3D via the donut.c pipeline, adapted: no 3D engine, just math.
  coordinates -> per-pixel ray -> march through 3D space -> first solid
  voxel wins (= z-buffer for free) -> surface normal -> light -> glyph.

This replaces the old per-column "shaded wall" raycaster. Terrain is a
heightfield (elevation -> actual voxel height, not just brightness), so
mountains visually rise, valleys sink, and you get real vertical
parallax as you move — not flat shaded blocks.

Biomes = hue. Elevation = darkness (bold/dim), never a different color.
Mountains are climbable (player height eases up to terrain height when
the slope isn't too steep). Caves are a simplified height-dip for now
(true overhangs are a real v6 feature, not faked here).

Controls: w/s move, a/d turn, r/f look up/down, e gather, m map, i inv,
          c size, q quit.
"""

import curses
import math
import random
import time

CHUNK_SIZE     = 16
MAX_HEIGHT     = 14.0
EYE_OFFSET     = 1.7
CLOUD_HEIGHT   = 22.0
FOV_DEG        = 60
BASE_VIEW_DIST = 26.0
RAY_STEP       = 0.6
MOVE_SPEED     = 0.35
TURN_STEP_DEG  = 6
FRAME_DELAY    = 1.0 / 64.0   # target at least 64 fps
MAX_CLIMB_SLOPE = 2.2   # max height diff per step you can climb before blocked
FLY_SPEED = 3.5
CUBE_SIZE = 0.125       # 1/8th of a "minecraft block" — blocky terrace granularity
SIZE_MODES = [
    ("tiny",   26, 9),
    ("small",  34, 11),
    ("medium", 44, 14),
    ("large",  70, 24),
    ("huge",   130, 46),
    ("full",   9999, 9999),   # uncapped — fills whatever terminal you have
]

SEED = random.randint(0, 999999)
random.seed(SEED)

# ---------------------------------------------------------------------
# value noise (dependency-free), multi-octave
# ---------------------------------------------------------------------
def _hash(x, y, seed):
    n = x * 374761393 + y * 668265263 + seed * 2147483647
    n = (n ^ (n >> 13)) * 1274126177
    n = n ^ (n >> 16)
    return (n & 0xffffffff) / 0xffffffff

def _smooth(x, y, seed):
    xi, yi = int(math.floor(x)), int(math.floor(y))
    xf, yf = x - xi, y - yi
    v00 = _hash(xi, yi, seed); v10 = _hash(xi+1, yi, seed)
    v01 = _hash(xi, yi+1, seed); v11 = _hash(xi+1, yi+1, seed)
    u = xf*xf*(3-2*xf); v = yf*yf*(3-2*yf)
    return (v00*(1-u)+v10*u)*(1-v) + (v01*(1-u)+v11*u)*v

def noise2(x, y, seed, octaves=4, persistence=0.5, scale=0.06):
    total, amp, freq, maxamp = 0.0, 1.0, scale, 0.0
    for o in range(octaves):
        total += _smooth(x*freq, y*freq, seed+o*101) * amp
        maxamp += amp
        amp *= persistence
        freq *= 2
    return total / maxamp


# ---------------------------------------------------------------------
# BIOMES — one hue each; elevation only changes brightness.
# ---------------------------------------------------------------------
OCEAN, PLAINS, GRASSLAND, FOREST, MOUNTAIN, PEAK, CAVE = range(7)
# semantic color KEYS, not raw pair numbers — resolved to real curses
# pairs in init_colors() so there is exactly one place that can get the
# color<->pair mapping wrong, instead of every dict entry guessing.
BIOME_INFO = {
    OCEAN:     {'ckey': 'ocean'},
    PLAINS:    {'ckey': 'plains'},
    GRASSLAND: {'ckey': 'grassland'},
    FOREST:    {'ckey': 'forest'},
    MOUNTAIN:  {'ckey': 'mountain'},
    PEAK:      {'ckey': 'peak'},
    CAVE:      {'ckey': 'cave'},
}
WATER_LEVEL = 0.34

BIOME_NAMES = {
    OCEAN: "ocean", PLAINS: "plains", GRASSLAND: "grassland",
    FOREST: "forest", MOUNTAIN: "mountain", PEAK: "peak (snow)", CAVE: "cave",
}
BIOME_RAMPS = {
    OCEAN:     " ..~~≈≈≈≈≈≈",
    PLAINS:    " ..,,;;::''",
    GRASSLAND: " ..,,''\"\"``",
    FOREST:    " ..\"\"##TTTT",
    MOUNTAIN:  " ..--^^^^##",
    PEAK:      " ..--^^AAAA",
    CAVE:      "   ..::;;;;",
}

# ---------------------------------------------------------------------
# COLOR SYSTEM — semantic name -> curses pair, built once at startup.
# Tries a real 32-color extended palette (xterm-256color); falls back
# to 8 base colors x bold if the terminal doesn't support it. Every
# consumer (biomes, objects, HUD) asks for a color by NAME, never a
# raw pair number, so there is no possibility of the old index-drift
# bug (grassland silently rendering red) happening again.
# ---------------------------------------------------------------------
COLOR_NAME_TO_PAIR = {}

# name -> (xterm-256 color id, bold?) used when 256-color is available.
# Distinct hues per biome/object so nothing overloads onto "red" by
# accident; reserve real red for something that should actually alarm
# (nothing currently does — kept free for future danger/mob use).
EXTENDED_PALETTE = {
    'ocean':      (33,  False),  # blue
    'ocean_deep': (25,  False),  # darker blue
    'plains':     (222, False),  # sandy yellow
    'grassland':  (34,  False),  # green
    'forest':     (22,  False),  # dark green
    'mountain':   (245, False),  # grey
    'peak':       (255, True),   # bright white (snow)
    'cave':       (236, False),  # near-black grey
    'sky':        (81,  False),  # light blue
    'cloud':      (255, False),  # white
    'wood':       (94,  False),  # brown
    'stone':      (248, False),  # light grey
    'ore':        (178, False),  # gold
    'berry':      (197, False),  # pink/red — a real, meaningful red use
    'fiber':      (229, False),  # pale yellow
    'clay':       (173, False),  # terracotta orange
    'ui':         (250, False),  # neutral UI text
    'player':     (46,  True),   # bright green marker
}
# fallback (8-color terminals): name -> (base color const name, bold?)
BASE_PALETTE = {
    'ocean': ('BLUE', False), 'ocean_deep': ('BLUE', False),
    'plains': ('YELLOW', False), 'grassland': ('GREEN', False),
    'forest': ('GREEN', True), 'mountain': ('WHITE', False),
    'peak': ('WHITE', True), 'cave': ('BLACK', True),
    'sky': ('CYAN', False), 'cloud': ('WHITE', False),
    'wood': ('YELLOW', True), 'stone': ('WHITE', False), 'ore': ('YELLOW', False),
    'berry': ('RED', False), 'fiber': ('YELLOW', False), 'clay': ('RED', True),
    'ui': ('WHITE', False), 'player': ('GREEN', True),
}


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    extended = curses.can_change_color() or curses.COLORS >= 256
    pair_id = 1
    if extended:
        for name, (cid, bold) in EXTENDED_PALETTE.items():
            try:
                curses.init_pair(pair_id, cid, -1)
            except curses.error:
                curses.init_pair(pair_id, curses.COLOR_WHITE, -1)
            COLOR_NAME_TO_PAIR[name] = (pair_id, curses.A_BOLD if bold else 0)
            pair_id += 1
    else:
        for name, (const_name, bold) in BASE_PALETTE.items():
            c = getattr(curses, f'COLOR_{const_name}')
            curses.init_pair(pair_id, c, -1)
            COLOR_NAME_TO_PAIR[name] = (pair_id, curses.A_BOLD if bold else 0)
            pair_id += 1


def attr_for(name, extra_bold=False):
    pair, bold = COLOR_NAME_TO_PAIR.get(name, COLOR_NAME_TO_PAIR.get('ui', (0, 0)))
    return curses.color_pair(pair) | bold | (curses.A_BOLD if extra_bold else 0)


LEGEND_ITEMS = [
    ("ocean", "~", "ocean/lake"),
    ("plains", ",", "plains"),
    ("grassland", ".", "grassland"),
    ("forest", "\"", "forest"),
    ("mountain", "^", "mountain"),
    ("peak", "A", "peak/snow"),
    ("cave", ":", "cave"),
    ("wood", "T", "tree"),
    ("stone", "#", "rock"),
    ("ore", "*", "ore"),
    ("berry", "o", "berries"),
    ("clay", "%", "clay"),
    ("cloud", "#", "cloud (sky)"),
]


def classify(gx, gy, seed):
    e = noise2(gx, gy, seed, octaves=5, scale=0.045)
    m = noise2(gx, gy, seed + 500, octaves=3, scale=0.08)
    cave_n = noise2(gx, gy, seed + 999, octaves=2, scale=0.09)

    if e < WATER_LEVEL:
        biome = OCEAN
    elif e < 0.45:
        biome = PLAINS
    elif e < 0.62:
        biome = FOREST if m > 0.52 else GRASSLAND
    elif e < 0.80:
        biome = MOUNTAIN
    else:
        biome = PEAK

    dipped = False
    if cave_n > 0.74 and biome != OCEAN:
        biome = CAVE
        dipped = True
    return biome, e, dipped


def height_for(e, biome, dipped):
    if biome == OCEAN:
        h = e / WATER_LEVEL * 1.0               # low, mostly flat
    else:
        h = e * MAX_HEIGHT
        if dipped:
            h *= 0.35                            # cave = local dip, prototype-simple
    # quantize to visible "cube" steps — Minecraft-scale block is treated
    # as 1.0 world unit here; CUBE_SIZE = 1/8 of that, so terrain reads
    # as fine blocky terraces rather than a smooth continuous slope.
    return round(h / CUBE_SIZE) * CUBE_SIZE


OBJECTS = {
    'tree':  {'ckey': 'wood', 'blocking': True, 'yield': 'wood', 'h': 3.0},
    'rock':  {'ckey': 'stone', 'blocking': True, 'yield': 'stone', 'h': 1.2},
    'ore':   {'ckey': 'ore', 'blocking': True, 'yield': 'ore', 'h': 1.0},
    'berry': {'ckey': 'berry', 'blocking': False, 'yield': 'berries', 'h': 0.6},
    'clay':  {'ckey': 'clay', 'blocking': False, 'yield': 'clay', 'h': 0.3},
    # future: mob / dungeon_entrance / base / building slot in with the
    # same shape (ckey, blocking, yield/behavior, h for voxel height).
}


class Chunk:
    __slots__ = ('height', 'biome', 'objects')
    def __init__(self):
        self.height = {}
        self.biome = {}
        self.objects = {}


class World:
    def __init__(self, seed=SEED):
        self.seed = seed
        self.chunks = {}

    def _cc(self, x, y):
        return x // CHUNK_SIZE, y // CHUNK_SIZE

    def get_chunk(self, cx, cy):
        key = (cx, cy)
        c = self.chunks.get(key)
        if c is None:
            c = self._generate(cx, cy)
            self.chunks[key] = c
        return c

    def _generate(self, cx, cy):
        chunk = Chunk()
        bx, by = cx*CHUNK_SIZE, cy*CHUNK_SIZE
        for ly in range(CHUNK_SIZE):
            for lx in range(CHUNK_SIZE):
                gx, gy = bx+lx, by+ly
                biome, e, dipped = classify(gx, gy, self.seed)
                h = height_for(e, biome, dipped)
                chunk.height[(lx, ly)] = h
                chunk.biome[(lx, ly)] = (biome, e)
                r = _hash(gx, gy, self.seed+7)
                if biome == FOREST and r < 0.14:
                    chunk.objects[(lx, ly)] = 'tree'
                elif biome in (MOUNTAIN, PEAK) and r < 0.09:
                    chunk.objects[(lx, ly)] = 'rock'
                elif biome in (MOUNTAIN, PEAK) and 0.09 <= r < 0.105:
                    chunk.objects[(lx, ly)] = 'ore'
                elif biome in (GRASSLAND, PLAINS) and r < 0.05:
                    chunk.objects[(lx, ly)] = 'berry'
                elif biome == PLAINS and 0.05 <= r < 0.07:
                    chunk.objects[(lx, ly)] = 'clay'
        return chunk

    def _local(self, x, y):
        cx, cy = self._cc(x, y)
        chunk = self.get_chunk(cx, cy)
        return chunk, x-cx*CHUNK_SIZE, y-cy*CHUNK_SIZE

    def height_at(self, x, y):
        chunk, lx, ly = self._local(x, y)
        return chunk.height[(lx, ly)]

    def biome_at(self, x, y):
        chunk, lx, ly = self._local(x, y)
        return chunk.biome[(lx, ly)]

    def object_at(self, x, y):
        chunk, lx, ly = self._local(x, y)
        return chunk.objects.get((lx, ly))

    def column_at(self, x, y):
        """One chunk lookup for height+object+biome together — the hot
        path for raymarching, which otherwise pays for 3 separate walks
        of the same chunk dict per step."""
        chunk, lx, ly = self._local(x, y)
        key = (lx, ly)
        h = chunk.height[key]
        obj = chunk.objects.get(key)
        biome, e = chunk.biome[key]
        return h, obj, biome, e

    def remove_object(self, x, y):
        chunk, lx, ly = self._local(x, y)
        chunk.objects.pop((lx, ly), None)


class Inventory:
    def __init__(self, base=16):
        self.capacity = base
        self.slots = {}

    def add(self, item, n=1):
        if item not in self.slots and len(self.slots) >= self.capacity:
            self.capacity *= 2
        self.slots[item] = self.slots.get(item, 0) + n

    def compact(self):
        if not self.slots:
            return f"[0/{self.capacity}] empty"
        return f"[{len(self.slots)}/{self.capacity}] " + " ".join(f"{k}:{v}" for k, v in self.slots.items())

    def full_lines(self):
        if not self.slots:
            return [f"capacity {self.capacity} — empty. gather with 'e' near a resource."]
        return [f"capacity: {len(self.slots)}/{self.capacity}"] + [f"  {k}: {v}" for k, v in self.slots.items()]


class Player:
    def __init__(self, x, y, world):
        self.x, self.y = x + 0.5, y + 0.5
        self.z = world.height_at(int(self.x), int(self.y))
        self.yaw = random.uniform(0, 360)
        self.pitch = 0.0
        self.flying = False
        self.inv = Inventory()

    def try_move(self, world, dt, forward=True):
        rad = math.radians(self.yaw)
        d = MOVE_SPEED * dt * (1 if forward else -0.5)
        nx, ny = self.x + math.cos(rad)*d, self.y + math.sin(rad)*d
        ix, iy = int(nx), int(ny)
        obj = world.object_at(ix, iy)
        if obj and OBJECTS[obj]['blocking']:
            return "blocked"
        target_h = world.height_at(ix, iy)
        if not self.flying and target_h - self.z > MAX_CLIMB_SLOPE:
            return "blocked"   # too steep to climb
        self.x, self.y = nx, ny
        if not self.flying:
            self.z += (target_h - self.z) * min(1.0, dt * 4)  # ease toward ground (climb)
        return None

    def fly(self, dt, direction):
        self.flying = True
        self.z += direction * FLY_SPEED * dt

    def gravity_ease(self, world, dt):
        """When not actively flying this frame, gently settle back toward
        the ground beneath you — keeps j/k as a deliberate 'fly' action
        rather than leaving you stuck floating forever."""
        if not self.flying:
            return
        target = world.height_at(int(self.x), int(self.y))
        diff = target - self.z
        if abs(diff) < 0.25:
            self.z = target
            self.flying = False
        else:
            self.z += diff * min(1.0, dt * 3.0)

    def turn(self, dt, direction):
        self.yaw = (self.yaw + direction * TURN_STEP_DEG * dt * 4) % 360

    def look(self, dt, direction):
        self.pitch = max(-30.0, min(30.0, self.pitch + direction * 20 * dt))

    def interact(self, world):
        ix, iy = int(self.x), int(self.y)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                o = world.object_at(ix+dx, iy+dy)
                if o:
                    item = OBJECTS[o]['yield']
                    self.inv.add(item)
                    world.remove_object(ix+dx, iy+dy)
                    return item
        return None


LUMA_RAMP = " .:-=+*#%@"
RAY_STEP_COARSE = 2.0
BISECT_ITERS = 5


def _is_solid(world, rx, ry, rz):
    """Cheap solidity test only — used during coarse scan + bisection.
    Detailed biome/normal info is computed once, after the true hit
    point is found, not on every candidate sample."""
    h, obj, biome, e = world.column_at(int(rx), int(ry))
    if obj and h <= rz <= h + OBJECTS[obj]['h']:
        return True, obj
    if rz <= h:
        return True, None
    return False, None


def raymarch_pixel(world, ox, oy, oz, yaw_deg, pitch_deg, max_dist):
    """Adapted donut pipeline: march a single 3D ray until it hits a
    solid voxel (ground column or object). First hit = z-buffer, free.
    Coarse scan (large step, ONE combined chunk lookup per step) finds
    the interval containing the surface; a fixed-count bisection (not a
    linear re-scan) narrows it. Detailed biome/lighting info is only
    computed once, at the very end, for the confirmed hit — not for
    every candidate sample along the way."""
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    dx = math.cos(yaw) * math.cos(pitch)
    dy = math.sin(yaw) * math.cos(pitch)
    dz = math.sin(pitch)

    dist = 0.0
    while dist < max_dist:
        dist += RAY_STEP_COARSE
        rx, ry, rz = ox + dx*dist, oy + dy*dist, oz + dz*dist
        if rz > CLOUD_HEIGHT:
            return dist, 'sky', None, None
        solid, obj_hint = _is_solid(world, rx, ry, rz)
        if solid:
            lo, hi = dist - RAY_STEP_COARSE, dist
            for _ in range(BISECT_ITERS):
                mid = (lo + hi) * 0.5
                mrx, mry, mrz = ox + dx*mid, oy + dy*mid, oz + dz*mid
                msolid, mobj_hint = _is_solid(world, mrx, mry, mrz)
                if msolid:
                    hi, obj_hint = mid, mobj_hint
                else:
                    lo = mid
            frx, fry, frz = ox + dx*hi, oy + dy*hi, oz + dz*hi
            fix, fiy = int(frx), int(fry)
            h, obj, biome, e = world.column_at(fix, fiy)
            if obj and h <= frz <= h + OBJECTS[obj]['h']:
                return hi, 'object', obj, None
            nh = world.height_at(fix+1, fiy)
            normal_tilt = max(0.0, min(1.0, 0.5 + (h - nh) * 0.15))
            return hi, 'ground', biome, (e, normal_tilt)
    return max_dist, None, None, None


def _pov_color(kind, key, t, extra):
    """Resolve a raymarch hit to (glyph, curses attr) using the semantic
    color system — never a raw pair number."""
    if kind == 'ground':
        e, tilt = extra
        ramp = BIOME_RAMPS.get(key, LUMA_RAMP)
        idx = min(len(ramp)-1, int(t * (len(ramp)-1)))
        ch = ramp[idx]
        extra_bold = tilt > 0.55 or t > 0.6
        return ch, attr_for(BIOME_INFO[key]['ckey'], extra_bold)
    else:  # object
        idx = min(len(LUMA_RAMP)-1, int(t * (len(LUMA_RAMP)-1)))
        ch = LUMA_RAMP[idx]
        return ch, attr_for(OBJECTS[key]['ckey'], t > 0.55)


def render_raymarch(stdscr, world, ox, oy, oz, oyaw, opitch, w, h, y0, cloud_t):
    """Core first/third-person renderer — camera origin/angle passed in
    explicitly so first-person and third-person POV can share this."""
    half_fov = FOV_DEG / 2
    for col in range(w):
        yaw = oyaw - half_fov + (col / w) * FOV_DEG
        for row in range(h):
            pitch = opitch + (h/2 - row) * (FOV_DEG * 0.6 / h)
            dist, kind, key, extra = raymarch_pixel(world, ox, oy, oz, yaw, pitch, BASE_VIEW_DIST)

            if kind is None or kind == 'sky':
                gx = ox + math.cos(math.radians(yaw)) * 8 + cloud_t
                gy = oy + math.sin(math.radians(yaw)) * 8
                cloudy = noise2(gx, gy, world.seed + 4242, octaves=2, scale=0.06) > 0.6
                ch = '#' if (kind == 'sky' and cloudy) else ' '
                attr = attr_for('cloud' if cloudy and kind == 'sky' else 'sky')
            else:
                t = 1.0 - min(dist / BASE_VIEW_DIST, 1.0)
                ch, attr = _pov_color(kind, key, t, extra)

            try:
                stdscr.addstr(y0+row, col, ch, attr)
            except curses.error:
                pass


def render_topdown(stdscr, world, player, w, h, y0, stride=1):
    """Direct height/biome sampling from directly overhead — no raymarch
    needed since we're looking straight down. `stride` controls zoom:
    stride=1 is closer/denser (satellite POV), stride>1 covers a wider
    area per screen cell (the full mental map)."""
    cx, cy = int(player.x), int(player.y)
    for row in range(h):
        for col in range(w):
            wx = cx - (w//2)*stride + col*stride
            wy = cy - (h//2)*stride + row*stride
            if wx == cx and wy == cy:
                ch, attr = '@', attr_for('player')
            else:
                obj = world.object_at(wx, wy)
                if obj:
                    ch, attr = '^', attr_for(OBJECTS[obj]['ckey'])
                else:
                    biome, e = world.biome_at(wx, wy)
                    ramp = BIOME_RAMPS.get(biome, LUMA_RAMP)
                    idx = min(len(ramp)-1, int(min(1.0, e*1.4) * (len(ramp)-1)))
                    ch = ramp[idx]
                    attr = attr_for(BIOME_INFO[biome]['ckey'], (e*7) % 1.0 > 0.5)
            try:
                stdscr.addstr(y0+row, col, ch, attr)
            except curses.error:
                pass


def render_legend(stdscr, max_y, max_x, legend_w):
    """Color/glyph index pinned to the right edge of the screen."""
    x0 = max_x - legend_w
    if x0 < 0:
        return
    try:
        stdscr.addstr(0, x0, "-- legend --"[:legend_w])
        for i, (ckey, glyph, label) in enumerate(LEGEND_ITEMS):
            row = 1 + i
            if row >= max_y - 1:
                break
            stdscr.addstr(row, x0, glyph, attr_for(ckey))
            stdscr.addstr(row, x0+2, label[:legend_w-3])
    except curses.error:
        pass


POV_NAMES = ["first-person", "satellite/fisheye", "third-person"]


def third_person_origin(player):
    """Camera behind + above the player, looking where they're facing.
    No player model exists to render, so nothing needs hiding — the
    'without the player rendered' requirement is automatic."""
    back, up = 3.0, 2.2
    rad = math.radians(player.yaw)
    ox = player.x - math.cos(rad) * back
    oy = player.y - math.sin(rad) * back
    oz = player.z + up + EYE_OFFSET
    opitch = player.pitch - 12  # tilt down slightly to see the ground ahead
    return ox, oy, oz, player.yaw, opitch


def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(0)
    init_colors()

    world = World()
    player = Player(0, 0, world)

    size_mode = 1 if max(stdscr.getmaxyx()) < 60 else 3
    pov_mode = 0
    show_map, show_inv = False, False
    show_legend = True
    msg = f"Seed {world.seed} — wander freely. e=gather p=pov m=map i=inv c=size q=quit"
    last = time.time()
    cloud_t = 0.0

    while True:
        now = time.time()
        dt = min(now - last, 0.1)
        last = now
        cloud_t += dt * 0.3

        vertical_input = False
        while True:
            ch = stdscr.getch()
            if ch == -1:
                break
            if ch in (ord('q'), ord('Q')):
                return
            elif ch in (ord('w'), ord('W')):
                r = player.try_move(world, max(dt, 0.05), True)
                if r == "blocked":
                    msg = "(too steep / blocked)"
            elif ch in (ord('s'), ord('S')):
                player.try_move(world, max(dt, 0.05), False)
            elif ch in (ord('a'), ord('A'), curses.KEY_LEFT):
                player.turn(max(dt, 0.05), -1)
            elif ch in (ord('d'), ord('D'), curses.KEY_RIGHT):
                player.turn(max(dt, 0.05), 1)
            elif ch in (ord('j'), ord('J')):
                player.fly(max(dt, 0.05), 1)     # j = up
                vertical_input = True
            elif ch in (ord('k'), ord('K')):
                player.fly(max(dt, 0.05), -1)    # k = down
                vertical_input = True
            elif ch in (ord('r'), ord('R')):
                player.look(max(dt, 0.05), 1)
            elif ch in (ord('f'), ord('F')):
                player.look(max(dt, 0.05), -1)
            elif ch in (ord('e'), ord('E')):
                got = player.interact(world)
                msg = f"gathered {got}" if got else "(nothing nearby to gather)"
            elif ch in (ord('p'), ord('P')):
                pov_mode = (pov_mode + 1) % 3
                msg = f"POV: {POV_NAMES[pov_mode]}"
            elif ch in (ord('m'), ord('M')):
                show_map, show_inv = not show_map, False
            elif ch in (ord('i'), ord('I')):
                show_inv, show_map = not show_inv, False
            elif ch in (ord('l'), ord('L')):
                show_legend = not show_legend
            elif ch in (ord('c'), ord('C')):
                size_mode = (size_mode + 1) % len(SIZE_MODES)

        if not vertical_input:
            player.gravity_ease(world, dt)

        stdscr.erase()
        max_y, max_x = stdscr.getmaxyx()
        mode_name, cap_w, cap_h = SIZE_MODES[size_mode]
        legend_w = 16 if (show_legend and max_x > 60) else 0
        w = max(12, min(max_x - 2 - legend_w, cap_w))
        h = max(6, min(max_y - 6, cap_h))

        try:
            look_dist, look_kind, look_key, _ = raymarch_pixel(
                world, player.x, player.y, player.z + EYE_OFFSET, player.yaw, player.pitch, BASE_VIEW_DIST)
            looking_at = (BIOME_NAMES.get(look_key, "?") if look_kind == 'ground'
                          else (look_key if look_kind == 'object' else "sky"))
            stdscr.addstr(0, 0, f"pos:({int(player.x)},{int(player.y)},{player.z:.1f}) "
                                 f"pov:{POV_NAMES[pov_mode]} looking at: {looking_at}"[:max_x-1])
            stdscr.addstr(1, 0, f"inv:{player.inv.compact()}"[:max_x-1])

            if show_inv:
                for i, line in enumerate(player.inv.full_lines()):
                    if 2+i < max_y-1:
                        stdscr.addstr(2+i, 0, line[:max_x-1])
            elif show_map:
                render_topdown(stdscr, world, player, w, h, 2, stride=3)
            elif pov_mode == 1:
                render_topdown(stdscr, world, player, w, h, 2, stride=1)
            elif pov_mode == 2:
                ox, oy, oz, oyaw, opitch = third_person_origin(player)
                render_raymarch(stdscr, world, ox, oy, oz, oyaw, opitch, w, h, 2, cloud_t)
            else:
                render_raymarch(stdscr, world, player.x, player.y, player.z + EYE_OFFSET,
                                 player.yaw, player.pitch, w, h, 2, cloud_t)

            if legend_w:
                render_legend(stdscr, max_y, max_x, legend_w)

            log_row = 2 + h
            if not show_inv and log_row < max_y-1:
                stdscr.addstr(log_row, 0, msg[:max_x-1])
            stdscr.addstr(max_y-1, 0,
                f"w/s move a/d turn j/k up-down r/f look e gather p pov m map i inv "
                f"l legend[{'on' if show_legend else 'off'}] c size[{mode_name}] q quit"[:max_x-1])
        except curses.error:
            pass

        stdscr.refresh()
        elapsed = time.time() - now
        time.sleep(max(0.0, FRAME_DELAY - elapsed))


if __name__ == '__main__':
    curses.wrapper(main)
