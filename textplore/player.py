"""Player movement, interaction, and inventory behavior."""

import math
import random

from .inventory import Inventory
from .objects import OBJECTS
from .settings import FLY_STEP, LOOK_STEP_DEG, MAX_CLIMB_SLOPE, MOVE_STEP, TURN_STEP_DEG


class Player:
    def __init__(self, x, y, world):
        self.x, self.y = x + 0.5, y + 0.5
        self.z = world.surface_at(self.x, self.y)
        self.yaw = random.uniform(0, 360)
        self.pitch = 0.0
        self.flying = False
        self.inv = Inventory()

    def try_move(self, world, forward=True):
        radians = math.radians(self.yaw)
        distance = MOVE_STEP * (1 if forward else -0.5)
        next_x = self.x + math.cos(radians) * distance
        next_y = self.y + math.sin(radians) * distance
        if world.blocking_object_at(next_x, next_y):
            return "blocked"

        target_height = world.surface_at(next_x, next_y)
        if not self.flying and target_height - self.z > MAX_CLIMB_SLOPE:
            return "blocked"

        self.x, self.y = next_x, next_y
        if not self.flying:
            self.z = target_height
        return None

    def fly(self, direction):
        self.flying = True
        self.z += direction * FLY_STEP

    def gravity_ease(self, world, dt):
        if not self.flying:
            return
        target = world.surface_at(self.x, self.y)
        difference = target - self.z
        if abs(difference) < 0.25:
            self.z = target
            self.flying = False
        else:
            self.z += difference * min(1.0, dt * 3.0)

    def turn(self, direction):
        self.yaw = (self.yaw + direction * TURN_STEP_DEG) % 360

    def look(self, direction):
        self.pitch = max(-30.0, min(30.0, self.pitch + direction * LOOK_STEP_DEG))

    def interact(self, world):
        nearest = world.nearest_object(self.x, self.y)
        if nearest is None:
            return None
        _distance, grid_x, grid_y, obj, _object_x, _object_y = nearest
        item = OBJECTS[obj]["yield"]
        self.inv.add(item)
        world.remove_object(grid_x, grid_y)
        return item
