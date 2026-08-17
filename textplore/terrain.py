"""Procedural noise, biome classification, and terrain elevation."""

import math

from .settings import MAX_HEIGHT, SEA_LEVEL


OCEAN, PLAINS, GRASSLAND, FOREST, MOUNTAIN, PEAK, CAVE = range(7)
WATER_LEVEL = 0.34

BIOME_INFO = {
    OCEAN: {"ckey": "ocean"},
    PLAINS: {"ckey": "plains"},
    GRASSLAND: {"ckey": "grassland"},
    FOREST: {"ckey": "forest"},
    MOUNTAIN: {"ckey": "mountain"},
    PEAK: {"ckey": "peak"},
    CAVE: {"ckey": "cave"},
}

BIOME_NAMES = {
    OCEAN: "ocean",
    PLAINS: "plains",
    GRASSLAND: "grassland",
    FOREST: "forest",
    MOUNTAIN: "mountain",
    PEAK: "peak (snow)",
    CAVE: "cave",
}

def hash_value(x, y, seed):
    """Return a stable pseudo-random value for an integer grid point."""
    n = x * 374761393 + y * 668265263 + seed * 2147483647
    n = (n ^ (n >> 13)) * 1274126177
    n ^= n >> 16
    return (n & 0xFFFFFFFF) / 0xFFFFFFFF


def _smooth(x, y, seed):
    xi, yi = int(math.floor(x)), int(math.floor(y))
    xf, yf = x - xi, y - yi
    v00 = hash_value(xi, yi, seed)
    v10 = hash_value(xi + 1, yi, seed)
    v01 = hash_value(xi, yi + 1, seed)
    v11 = hash_value(xi + 1, yi + 1, seed)
    u = xf * xf * (3 - 2 * xf)
    v = yf * yf * (3 - 2 * yf)
    return (v00 * (1 - u) + v10 * u) * (1 - v) + (v01 * (1 - u) + v11 * u) * v


def noise2(x, y, seed, octaves=4, persistence=0.5, scale=0.06):
    total, amp, freq, maxamp = 0.0, 1.0, scale, 0.0
    for octave in range(octaves):
        total += _smooth(x * freq, y * freq, seed + octave * 101) * amp
        maxamp += amp
        amp *= persistence
        freq *= 2
    return total / maxamp


def classify(gx, gy, seed):
    elevation = noise2(gx, gy, seed, octaves=5, scale=0.045)
    moisture = noise2(gx, gy, seed + 500, octaves=3, scale=0.08)
    cave_noise = noise2(gx, gy, seed + 999, octaves=2, scale=0.09)

    if elevation < WATER_LEVEL:
        biome = OCEAN
    elif elevation < 0.45:
        biome = PLAINS
    elif elevation < 0.62:
        biome = FOREST if moisture > 0.52 else GRASSLAND
    elif elevation < 0.80:
        biome = MOUNTAIN
    else:
        biome = PEAK

    dipped = cave_noise > 0.74 and biome != OCEAN
    if dipped:
        biome = CAVE
    return biome, elevation, dipped


def height_for(elevation, biome, dipped):
    """Map noise to a continuous surface with a level sea and smooth coast."""
    if biome == OCEAN:
        return SEA_LEVEL

    land = max(0.0, (elevation - WATER_LEVEL) / (1.0 - WATER_LEVEL))
    height = SEA_LEVEL + (land ** 1.25) * (MAX_HEIGHT - SEA_LEVEL)
    if dipped:
        height = SEA_LEVEL + (height - SEA_LEVEL) * 0.35
    return height
