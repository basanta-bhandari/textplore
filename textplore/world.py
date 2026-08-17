"""Lazy chunk storage and a continuous procedural world surface."""

import math

from .objects import OBJECTS
from .settings import CHUNK_SIZE, SEED
from .structures import STRUCTURES
from .terrain import (
    CAVE,
    FOREST,
    GRASSLAND,
    MOUNTAIN,
    PEAK,
    OCEAN,
    PLAINS,
    classify,
    hash_value,
    height_for,
)


class Chunk:
    __slots__ = ("height", "biome", "objects", "structures")

    def __init__(self):
        self.height = {}
        self.biome = {}
        self.objects = {}
        self.structures = {}


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
                structure_roll = hash_value(grid_x, grid_y, self.seed + 1701)
                if biome in (MOUNTAIN, PEAK, CAVE) and structure_roll < 0.004:
                    chunk.structures[key] = "cave entrance"
                    continue
                if biome in (PLAINS, GRASSLAND) and structure_roll < 0.0003:
                    coast = any(
                        classify(grid_x + dx, grid_y + dy, self.seed)[0] == OCEAN
                        for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3))
                    )
                    if coast:
                        chunk.structures[key] = "lighthouse"
                        continue
                if biome in (PLAINS, GRASSLAND, FOREST, MOUNTAIN) and structure_roll < 0.0012:
                    chunk.structures[key] = "dungeon"
                    continue

                if biome == FOREST and roll < 0.12:
                    chunk.objects[key] = "tree"
                elif biome == FOREST and roll < 0.16:
                    chunk.objects[key] = "mushroom"
                elif biome == FOREST and roll < 0.19:
                    chunk.objects[key] = "herb"
                elif biome == FOREST and roll < 0.22:
                    chunk.objects[key] = "fiber"
                elif biome in (MOUNTAIN, PEAK) and roll < 0.09:
                    chunk.objects[key] = "rock"
                elif biome in (MOUNTAIN, PEAK) and roll < 0.105:
                    chunk.objects[key] = "ore"
                elif biome in (MOUNTAIN, PEAK) and roll < 0.13:
                    chunk.objects[key] = "coal"
                elif biome in (MOUNTAIN, PEAK) and roll < 0.136:
                    chunk.objects[key] = "crystal"
                elif biome == CAVE and roll < 0.08:
                    chunk.objects[key] = "mushroom"
                elif biome == CAVE and roll < 0.14:
                    chunk.objects[key] = "coal"
                elif biome == CAVE and roll < 0.16:
                    chunk.objects[key] = "crystal"
                elif biome in (GRASSLAND, PLAINS) and roll < 0.04:
                    chunk.objects[key] = "berry"
                elif biome == PLAINS and roll < 0.065:
                    chunk.objects[key] = "clay"
                elif biome == PLAINS and roll < 0.09:
                    chunk.objects[key] = "sand"
                elif biome in (GRASSLAND, PLAINS) and roll < 0.16:
                    chunk.objects[key] = "fiber"
                elif biome in (GRASSLAND, PLAINS) and roll < 0.185:
                    chunk.objects[key] = "herb"
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

    def structure_at(self, x, y):
        chunk, local_x, local_y = self._local(x, y)
        return chunk.structures.get((local_x, local_y))

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

    def structure_position(self, grid_x, grid_y):
        jitter_x = (hash_value(grid_x, grid_y, self.seed + 809) - 0.5) * 0.3
        jitter_y = (hash_value(grid_x, grid_y, self.seed + 907) - 0.5) * 0.3
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

    def blocking_structure_at(self, x, y, player_radius=0.18):
        center_x, center_y = math.floor(x), math.floor(y)
        for grid_y in range(center_y - 2, center_y + 3):
            for grid_x in range(center_x - 2, center_x + 3):
                structure = self.structure_at(grid_x, grid_y)
                if structure is None:
                    continue
                structure_x, structure_y = self.structure_position(grid_x, grid_y)
                radius = STRUCTURES[structure]["radius"]
                if math.hypot(x - structure_x, y - structure_y) < radius + player_radius:
                    return structure
        return None
