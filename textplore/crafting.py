"""Crafting recipes and inventory transactions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Recipe:
    name: str
    ingredients: dict
    output_count: int = 1

    def ingredient_text(self):
        return " + ".join(f"{count} {item}" for item, count in self.ingredients.items())


RECIPES = [
    Recipe("planks", {"wood": 1}, 4),
    Recipe("sticks", {"planks": 2}, 4),
    Recipe("rope", {"fiber": 3}),
    Recipe("torch", {"sticks": 1, "coal": 1}, 4),
    Recipe("stone pickaxe", {"stone": 3, "sticks": 2}),
    Recipe("iron pickaxe", {"iron ore": 3, "sticks": 2}),
    Recipe("bandage", {"fiber": 2, "herb": 1}),
    Recipe("clay bricks", {"clay": 2}, 2),
    Recipe("crystal lantern", {"iron ore": 1, "crystal": 1, "torch": 1}),
    Recipe("mushroom stew", {"mushroom": 2, "berries": 1}),
]


def craft(inventory, recipe):
    if not inventory.consume(recipe.ingredients):
        return False
    inventory.add(recipe.name, recipe.output_count)
    return True
