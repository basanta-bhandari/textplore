"""Smooth heightfield ray marching and top-down terminal rendering."""

import curses
import math

from .colors import attr_for
from .objects import OBJECTS, contains
from .settings import BASE_VIEW_DIST, CLOUD_HEIGHT, EYE_OFFSET, FOV_DEG
from .terrain import BIOME_INFO, OCEAN, classify, noise2


TERRAIN_RAMP = " .,:;irsXA253hMHGS#9B&@"
OBJECT_RAMP = " .:-=+*#%@"
RAY_STEP_COARSE = 1.0
BISECT_ITERS = 5
POV_NAMES = ["first-person", "satellite/fisheye", "third-person"]

# A high, angled sun makes slopes readable in monochrome as well as color.
_LIGHT = (-0.42, -0.32, 0.848)


def _frame_caches(cache):
    if cache is None:
        cache = {}
    return (
        cache.setdefault("columns", {}),
        cache.setdefault("objects", {}),
        cache.setdefault("object_bases", {}),
        cache.setdefault("spatial_objects", {}),
    )


def _column_at(world, grid_x, grid_y, column_cache):
    key = (grid_x, grid_y)
    column = column_cache.get(key)
    if column is None:
        column = world.column_at(grid_x, grid_y)
        column_cache[key] = column
    return column


def _surface_at(world, x, y, column_cache):
    """Bilinearly interpolate four grid samples into a continuous surface."""
    x0, y0 = math.floor(x), math.floor(y)
    fraction_x, fraction_y = x - x0, y - y0
    h00 = _column_at(world, x0, y0, column_cache)[0]
    h10 = _column_at(world, x0 + 1, y0, column_cache)[0]
    h01 = _column_at(world, x0, y0 + 1, column_cache)[0]
    h11 = _column_at(world, x0 + 1, y0 + 1, column_cache)[0]
    lower = h00 + (h10 - h00) * fraction_x
    upper = h01 + (h11 - h01) * fraction_x
    return lower + (upper - lower) * fraction_y


def _object_at(world, grid_x, grid_y, object_cache):
    key = (grid_x, grid_y)
    if key not in object_cache:
        object_cache[key] = world.object_at(grid_x, grid_y)
    return object_cache[key]


def _objects_in_cell(world, cell_x, cell_y, object_cache, spatial_cache):
    """Build an overlap list once for each terrain cell visited this frame."""
    key = (cell_x, cell_y)
    if key in spatial_cache:
        return spatial_cache[key]

    candidates = []
    for grid_y in range(cell_y - 1, cell_y + 2):
        for grid_x in range(cell_x - 1, cell_x + 2):
            obj = _object_at(world, grid_x, grid_y, object_cache)
            if obj is None:
                continue
            object_x, object_y = world.object_position(grid_x, grid_y)
            radius = OBJECTS[obj]["radius"]
            overlaps = (
                object_x + radius >= cell_x
                and object_x - radius <= cell_x + 1
                and object_y + radius >= cell_y
                and object_y - radius <= cell_y + 1
            )
            if overlaps:
                candidates.append((grid_x, grid_y, obj, object_x, object_y, radius))
    spatial_cache[key] = candidates
    return candidates


def _object_hit(
    world, x, y, z, column_cache, object_cache, base_cache, spatial_cache
):
    """Test rounded nearby resources rather than a square object column."""
    cell_x, cell_y = math.floor(x), math.floor(y)
    candidates = _objects_in_cell(world, cell_x, cell_y, object_cache, spatial_cache)
    for grid_x, grid_y, obj, object_x, object_y, radius in candidates:
        if abs(x - object_x) > radius or abs(y - object_y) > radius:
            continue
        key = (grid_x, grid_y)
        if key not in base_cache:
            base_cache[key] = _surface_at(world, object_x, object_y, column_cache)
        if contains(obj, x - object_x, y - object_y, z - base_cache[key]):
            return obj
    return None


def _is_solid(world, x, y, z, frame_cache):
    columns, objects, bases, spatial = _frame_caches(frame_cache)
    if z <= _surface_at(world, x, y, columns):
        return True, None
    obj = _object_hit(world, x, y, z, columns, objects, bases, spatial)
    return obj is not None, obj


def _surface_light(world, x, y, column_cache):
    epsilon = 0.32
    slope_x = (
        _surface_at(world, x + epsilon, y, column_cache)
        - _surface_at(world, x - epsilon, y, column_cache)
    ) / (2 * epsilon)
    slope_y = (
        _surface_at(world, x, y + epsilon, column_cache)
        - _surface_at(world, x, y - epsilon, column_cache)
    ) / (2 * epsilon)
    nx, ny, nz = -slope_x, -slope_y, 1.0
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    diffuse = max(0.0, (nx * _LIGHT[0] + ny * _LIGHT[1] + nz * _LIGHT[2]) / length)
    return 0.22 + diffuse * 0.78


def raymarch_pixel(
    world,
    origin_x,
    origin_y,
    origin_z,
    yaw_degrees,
    pitch_degrees,
    max_dist,
    frame_cache=None,
):
    yaw = math.radians(yaw_degrees)
    pitch = math.radians(pitch_degrees)
    dx = math.cos(yaw) * math.cos(pitch)
    dy = math.sin(yaw) * math.cos(pitch)
    dz = math.sin(pitch)
    cache = frame_cache if frame_cache is not None else {}

    distance = 0.0
    while distance < max_dist:
        distance += RAY_STEP_COARSE
        ray_x = origin_x + dx * distance
        ray_y = origin_y + dy * distance
        ray_z = origin_z + dz * distance
        if ray_z > CLOUD_HEIGHT:
            return distance, "sky", None, None

        solid, _object_hint = _is_solid(world, ray_x, ray_y, ray_z, cache)
        if not solid:
            continue

        low, high = distance - RAY_STEP_COARSE, distance
        for _ in range(BISECT_ITERS):
            middle = (low + high) * 0.5
            mid_x = origin_x + dx * middle
            mid_y = origin_y + dy * middle
            mid_z = origin_z + dz * middle
            middle_solid, _middle_object = _is_solid(world, mid_x, mid_y, mid_z, cache)
            if middle_solid:
                high = middle
            else:
                low = middle

        hit_x = origin_x + dx * high
        hit_y = origin_y + dy * high
        hit_z = origin_z + dz * high
        columns, objects, bases, spatial = _frame_caches(cache)
        obj = _object_hit(world, hit_x, hit_y, hit_z, columns, objects, bases, spatial)
        if obj:
            return high, "object", obj, None

        biome, elevation, _dipped = classify(hit_x, hit_y, world.seed)
        light = _surface_light(world, hit_x, hit_y, columns)
        return high, "ground", biome, (elevation, light)

    return max_dist, None, None, None


def _pov_glyph(kind, key, closeness, extra):
    if kind == "ground":
        _elevation, light = extra
        brightness = max(0.0, min(1.0, light * (0.5 + closeness * 0.5)))
        index = min(len(TERRAIN_RAMP) - 1, int(brightness * (len(TERRAIN_RAMP) - 1)))
        glyph = TERRAIN_RAMP[index]
        return glyph, attr_for(BIOME_INFO[key]["ckey"], brightness > 0.72)

    index = min(len(OBJECT_RAMP) - 1, int((0.3 + closeness * 0.7) * (len(OBJECT_RAMP) - 1)))
    return OBJECT_RAMP[index], attr_for(OBJECTS[key]["ckey"], closeness > 0.55)


def render_raymarch(
    stdscr, world, origin_x, origin_y, origin_z, yaw, pitch, width, height, y_origin, cloud_time
):
    half_fov = FOV_DEG / 2
    frame_cache = {}
    glyph_rows = [[" "] * width for _ in range(height)]
    attribute_rows = [[0] * width for _ in range(height)]
    for column in range(width):
        ray_yaw = yaw - half_fov + (column / width) * FOV_DEG
        for row in range(height):
            ray_pitch = pitch + (height / 2 - row) * (FOV_DEG * 0.6 / height)
            distance, kind, key, extra = raymarch_pixel(
                world,
                origin_x,
                origin_y,
                origin_z,
                ray_yaw,
                ray_pitch,
                BASE_VIEW_DIST,
                frame_cache,
            )

            if kind is None or kind == "sky":
                cloud_x = origin_x + math.cos(math.radians(ray_yaw)) * 8 + cloud_time
                cloud_y = origin_y + math.sin(math.radians(ray_yaw)) * 8
                cloudy = noise2(cloud_x, cloud_y, world.seed + 4242, octaves=2, scale=0.06) > 0.6
                glyph = "#" if kind == "sky" and cloudy else " "
                attribute = attr_for("cloud" if cloudy and kind == "sky" else "sky")
            else:
                closeness = 1.0 - min(distance / BASE_VIEW_DIST, 1.0)
                glyph, attribute = _pov_glyph(kind, key, closeness, extra)

            glyph_rows[row][column] = glyph
            attribute_rows[row][column] = attribute

    _flush_cell_buffer(stdscr, glyph_rows, attribute_rows, y_origin)


def _flush_cell_buffer(stdscr, glyph_rows, attribute_rows, y_origin):
    for row, (glyphs, attributes) in enumerate(zip(glyph_rows, attribute_rows)):
        run_start = 0
        while run_start < len(glyphs):
            attribute = attributes[run_start]
            run_end = run_start + 1
            while run_end < len(glyphs) and attributes[run_end] == attribute:
                run_end += 1
            try:
                stdscr.addstr(
                    y_origin + row,
                    run_start,
                    "".join(glyphs[run_start:run_end]),
                    attribute,
                )
            except curses.error:
                pass
            run_start = run_end


def render_topdown(stdscr, world, player, width, height, y_origin, stride=1):
    glyph_rows = [[" "] * width for _ in range(height)]
    attribute_rows = [[0] * width for _ in range(height)]
    for row in range(height):
        for column in range(width):
            world_x = player.x + (column - width // 2) * stride
            world_y = player.y + (row - height // 2) * stride * 1.65
            if column == width // 2 and row == height // 2:
                glyph, attribute = "@", attr_for("player")
            else:
                obj = world.object_at(math.floor(world_x), math.floor(world_y))
                if obj:
                    glyph, attribute = "o", attr_for(OBJECTS[obj]["ckey"])
                else:
                    _surface, biome, elevation = world.surface_details_at(world_x, world_y)
                    normal = world.surface_normal_at(world_x, world_y)
                    diffuse = max(
                        0.0,
                        normal[0] * _LIGHT[0] + normal[1] * _LIGHT[1] + normal[2] * _LIGHT[2],
                    )
                    brightness = 0.22 + diffuse * 0.78
                    index = min(
                        len(TERRAIN_RAMP) - 1,
                        int(brightness * (len(TERRAIN_RAMP) - 1)),
                    )
                    glyph = "~" if biome == OCEAN and index > 4 else TERRAIN_RAMP[index]
                    attribute = attr_for(BIOME_INFO[biome]["ckey"], brightness > 0.72)
            glyph_rows[row][column] = glyph
            attribute_rows[row][column] = attribute

    _flush_cell_buffer(stdscr, glyph_rows, attribute_rows, y_origin)


def third_person_origin(player):
    back, up = 3.0, 2.2
    radians = math.radians(player.yaw)
    origin_x = player.x - math.cos(radians) * back
    origin_y = player.y - math.sin(radians) * back
    origin_z = player.z + up + EYE_OFFSET
    return origin_x, origin_y, origin_z, player.yaw, player.pitch - 12
