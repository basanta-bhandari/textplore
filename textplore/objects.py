"""Definitions for resources placed in the world."""


OBJECTS = {
    "tree": {
        "ckey": "wood", "label": "tree (wood)", "blocking": True, "yield": "wood", "h": 3.2,
        "radius": 0.72, "collision_radius": 0.2,
    },
    "rock": {
        "ckey": "stone", "label": "rock (stone)", "blocking": True, "yield": "stone", "h": 1.15,
        "radius": 0.48, "collision_radius": 0.48,
    },
    "ore": {
        "ckey": "ore", "label": "iron ore", "blocking": True, "yield": "iron ore", "h": 0.9,
        "radius": 0.38, "collision_radius": 0.38,
    },
    "berry": {
        "ckey": "berry", "label": "berry bush", "blocking": False, "yield": "berries", "h": 0.7, "radius": 0.46,
    },
    "clay": {
        "ckey": "clay", "label": "clay deposit", "blocking": False, "yield": "clay", "h": 0.16, "radius": 0.5,
    },
    "fiber": {
        "ckey": "fiber", "label": "plant fiber", "blocking": False, "yield": "fiber", "h": 0.4, "radius": 0.24,
    },
    "herb": {
        "ckey": "herb", "label": "healing herb", "blocking": False, "yield": "herb", "h": 0.45, "radius": 0.28,
    },
    "mushroom": {
        "ckey": "mushroom", "label": "mushroom", "blocking": False, "yield": "mushroom", "h": 0.5, "radius": 0.3,
    },
    "coal": {
        "ckey": "coal", "label": "coal", "blocking": True, "yield": "coal", "h": 0.72,
        "radius": 0.35, "collision_radius": 0.35,
    },
    "crystal": {
        "ckey": "crystal", "label": "crystal", "blocking": True, "yield": "crystal", "h": 0.9,
        "radius": 0.3, "collision_radius": 0.3,
    },
    "sand": {
        "ckey": "sand", "label": "sand deposit", "blocking": False, "yield": "sand", "h": 0.12, "radius": 0.46,
    },
}


def contains(obj, local_x, local_y, local_z):
    """Return whether a point is inside an organic silhouette for an object."""
    if local_z < 0:
        return False

    radial_sq = local_x * local_x + local_y * local_y
    if obj == "tree":
        trunk = radial_sq <= 0.16**2 and local_z <= 2.45
        canopy = radial_sq / 0.72**2 + ((local_z - 2.45) / 0.82) ** 2 <= 1.0
        return trunk or canopy

    definition = OBJECTS[obj]
    radius = definition["radius"]
    half_height = definition["h"] * 0.5
    if half_height == 0:
        return False
    # Slightly asymmetric offsets stop every rock and bush looking identical.
    warped_x = local_x + 0.08 * local_y
    return (
        warped_x * warped_x / radius**2
        + local_y * local_y / (radius * 0.82) ** 2
        + ((local_z - half_height) / half_height) ** 2
        <= 1.0
    )
