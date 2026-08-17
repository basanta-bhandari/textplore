"""Shared gameplay and rendering configuration."""

import random


CHUNK_SIZE = 16
MAX_HEIGHT = 14.0
SEA_LEVEL = 1.0
EYE_OFFSET = 1.7
CLOUD_HEIGHT = 22.0
FOV_DEG = 60
BASE_VIEW_DIST = 26.0
MOVE_STEP = 0.35
TURN_STEP_DEG = 6
LOOK_STEP_DEG = 3
FRAME_DELAY = 1.0 / 64.0
MAX_CLIMB_SLOPE = 2.2
FLY_STEP = 0.35

SIZE_MODES = [
    ("tiny", 26, 9),
    ("small", 34, 11),
    ("medium", 44, 14),
    ("large", 70, 24),
    ("huge", 130, 46),
    ("full", 9999, 9999),
]

SEED = random.randint(0, 999999)
random.seed(SEED)
