"""Rare world structures and their smooth implicit geometry."""

import math


STRUCTURES = {
    "cave entrance": {"ckey": "cave", "label": "cave entrance", "radius": 1.05, "h": 1.8},
    "dungeon": {"ckey": "dungeon", "label": "dungeon ruins", "radius": 1.35, "h": 2.0},
    "lighthouse": {"ckey": "lighthouse", "label": "lighthouse", "radius": 0.85, "h": 8.5},
}


def contains_structure(kind, local_x, local_y, local_z):
    if local_z < 0:
        return False
    radial = math.hypot(local_x, local_y)

    if kind == "cave entrance":
        # A dark, rounded mouth with an irregular stone lip.
        dome = radial * radial / 1.05**2 + ((local_z - 0.72) / 0.9) ** 2 <= 1.0
        notch = local_x > 0.28 and abs(local_y) < 0.28 and local_z < 0.72
        return dome and not notch

    if kind == "dungeon":
        wall = 0.82 <= radial <= 1.3 and local_z <= 1.35
        doorway = local_x > 0.72 and abs(local_y) < 0.3 and local_z < 0.9
        cap = radial <= 0.62 and 0.22 <= local_z <= 0.42
        return (wall and not doorway) or cap

    if kind == "lighthouse":
        if local_z <= 6.8:
            tower_radius = 0.62 - local_z * 0.025
            return radial <= tower_radius
        lantern_room = radial <= 0.78 and local_z <= 7.65
        roof_radius = max(0.0, (8.5 - local_z) * 0.9)
        roof = 7.65 < local_z <= 8.5 and radial <= roof_radius
        return lantern_room or roof

    return False
