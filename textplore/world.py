"""Lazy chunk storage and a continuous procedural world surface."""

import math

from .objects import OBJECTS
from .settings import CHUNK_SIZE, SEED
from .terrain import (
    FOREST,
    GRASSLAND,
    MOUNTAIN,
    PEAK,
    PLAINS,
    classify,
    hash_value,
    height_for,
)


class Chunk:
    __slots__ = ("height", "biome", "objects")

    def __init__(self):
        self.height = {}
        self.biome = {}
        self.objects = {}


class World:
    def __init__(self, seed=SEED):
        self.seed = seed
        self.chunks = {}

    @staticmethod
    def _chunk_coords(x, y):
        return x // CHUNK_SIZE, y // CHUNK_SIZE

    def get_chunk(self, cx, cy):
        key = (cx, cy)
        chunk = self.chunks.get(key)
        if chunk is None:
            chunk = self._generate(cx, cy)
            self.chunks[key] = chunk
        return chunk

    def _generate(self, cx, cy):
        chunk = Chunk()
        base_x, base_y = cx * CHUNK_SIZE, cy * CHUNK_SIZE
        for local_y in range(CHUNK_SIZE):
            for local_x in range(CHUNK_SIZE):
                grid_x, grid_y = base_x + local_x, base_y + local_y
                biome, elevation, dipped = classify(grid_x, grid_y, self.seed)
                key = (local_x, local_y)
                chunk.height[key] = height_for(elevation, biome, dipped)
                chunk.biome[key] = (biome, elevation)

                roll = hash_value(grid_x, grid_y, self.seed + 7)
                if biome == FOREST and roll < 0.14:
                    chunk.objects[key] = "tree"
                elif biome in (MOUNTAIN, PEAK) and roll < 0.09:
                    chunk.objects[key] = "rock"
                elif biome in (MOUNTAIN, PEAK) and 0.09 <= roll < 0.105:
                    chunk.objects[key] = "ore"
                elif biome in (GRASSLAND, PLAINS) and roll < 0.05:
                    chunk.objects[key] = "berry"
                elif biome == PLAINS and 0.05 <= roll < 0.07:
                    chunk.objects[key] = "clay"
        return chunk

    def _local(self, x, y):
        cx, cy = self._chunk_coords(x, y)
        chunk = self.get_chunk(cx, cy)
        return chunk, x - cx * CHUNK_SIZE, y - cy * CHUNK_SIZE

    def height_at(self, x, y):
        chunk, local_x, local_y = self._local(x, y)
        return chunk.height[(local_x, local_y)]

    def biome_at(self, x, y):
        chunk, local_x, local_y = self._local(x, y)
        return chunk.biome[(local_x, local_y)]

    def object_at(self, x, y):
        chunk, local_x, local_y = self._local(x, y)
        return chunk.objects.get((local_x, local_y))

    def column_at(self, x, y):
        """Fetch height, object, biome, and elevation with one chunk lookup."""
        chunk, local_x, local_y = self._local(x, y)
        key = (local_x, local_y)
        height = chunk.height[key]
        obj = chunk.objects.get(key)
        biome, elevation = chunk.biome[key]
        return height, obj, biome, elevation

    def remove_object(self, x, y):
        chunk, local_x, local_y = self._local(x, y)
        chunk.objects.pop((local_x, local_y), None)

    def surface_at(self, x, y):
        """Interpolate neighboring samples into a continuous terrain height."""
        x0, y0 = math.floor(x), math.floor(y)
        fraction_x, fraction_y = x - x0, y - y0
        h00 = self.height_at(x0, y0)
        h10 = self.height_at(x0 + 1, y0)
        h01 = self.height_at(x0, y0 + 1)
        h11 = self.height_at(x0 + 1, y0 + 1)
        lower = h00 + (h10 - h00) * fraction_x
        upper = h01 + (h11 - h01) * fraction_x
        return lower + (upper - lower) * fraction_y

    def surface_details_at(self, x, y):
        """Return smooth height plus continuously classified biome data."""
        biome, elevation, _dipped = classify(x, y, self.seed)
        return self.surface_at(x, y), biome, elevation

    def surface_normal_at(self, x, y, epsilon=0.35):
        """Estimate a normalized surface normal from the smooth heightfield."""
        slope_x = (self.surface_at(x + epsilon, y) - self.surface_at(x - epsilon, y)) / (2 * epsilon)
        slope_y = (self.surface_at(x, y + epsilon) - self.surface_at(x, y - epsilon)) / (2 * epsilon)
        nx, ny, nz = -slope_x, -slope_y, 1.0
        length = math.sqrt(nx * nx + ny * ny + nz * nz)
        return nx / length, ny / length, nz / length

    def object_position(self, grid_x, grid_y):
        """Place resources off-center so they do not form a visible grid."""
        jitter_x = (hash_value(grid_x, grid_y, self.seed + 81) - 0.5) * 0.5
        jitter_y = (hash_value(grid_x, grid_y, self.seed + 163) - 0.5) * 0.5
        return grid_x + 0.5 + jitter_x, grid_y + 0.5 + jitter_y

    def nearby_objects(self, x, y, radius):
        cell_radius = math.ceil(radius + 1.0)
        center_x, center_y = math.floor(x), math.floor(y)
        for grid_y in range(center_y - cell_radius, center_y + cell_radius + 1):
            for grid_x in range(center_x - cell_radius, center_x + cell_radius + 1):
                obj = self.object_at(grid_x, grid_y)
                if not obj:
                    continue
                object_x, object_y = self.object_position(grid_x, grid_y)
                distance = math.hypot(object_x - x, object_y - y)
                if distance <= radius + OBJECTS[obj]["radius"]:
                    yield distance, grid_x, grid_y, obj, object_x, object_y

    def blocking_object_at(self, x, y, player_radius=0.18):
        for distance, _gx, _gy, obj, _ox, _oy in self.nearby_objects(x, y, player_radius + 0.5):
            if OBJECTS[obj]["blocking"] and distance < OBJECTS[obj]["collision_radius"] + player_radius:
                return obj
        return None

    def nearest_object(self, x, y, radius=1.5):
        candidates = list(self.nearby_objects(x, y, radius))
        return min(candidates, default=None, key=lambda candidate: candidate[0])
