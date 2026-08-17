#!/usr/bin/env python3
"""Launch the Textplore procedural ASCII exploration game.

Controls: w/s move, a/d turn, j/k fly up/down, r/f look up/down,
e gather, t craft, p change point of view, m map, i inventory, l legend,
c display size, q quit.
"""

import curses
import time

from textplore.colors import init_colors, render_legend
from textplore.crafting import RECIPES, craft
from textplore.player import Player
from textplore.rendering import (
    POV_NAMES,
    raymarch_pixel,
    render_raymarch,
    render_topdown,
    third_person_origin,
)
from textplore.settings import BASE_VIEW_DIST, EYE_OFFSET, FRAME_DELAY, SIZE_MODES
from textplore.terrain import BIOME_NAMES
from textplore.world import World


def handle_input(stdscr, player, world, state):
    """Drain pending key events and update mutable game state."""
    vertical_input = False
    changed = False

    while True:
        key = stdscr.getch()
        if key == -1:
            break
        if key in (ord("q"), ord("Q")):
            return True, vertical_input, changed
        if state["show_crafting"]:
            if key in (ord("t"), ord("T"), 27):
                state["show_crafting"] = False
            elif key in (ord("w"), ord("W"), curses.KEY_UP):
                state["craft_index"] = (state["craft_index"] - 1) % len(RECIPES)
            elif key in (ord("s"), ord("S"), curses.KEY_DOWN):
                state["craft_index"] = (state["craft_index"] + 1) % len(RECIPES)
            elif key in (ord("e"), ord("E"), 10, 13, curses.KEY_ENTER):
                recipe = RECIPES[state["craft_index"]]
                if craft(player.inv, recipe):
                    state["message"] = f"crafted {recipe.output_count} {recipe.name}"
                else:
                    state["message"] = f"missing materials for {recipe.name}"
            changed = True
            continue
        if key in (ord("w"), ord("W")):
            if player.try_move(world, True) == "blocked":
                state["message"] = "(too steep / blocked)"
            changed = True
        elif key in (ord("s"), ord("S")):
            player.try_move(world, False)
            changed = True
        elif key in (ord("a"), ord("A"), curses.KEY_LEFT):
            player.turn(-1)
            changed = True
        elif key in (ord("d"), ord("D"), curses.KEY_RIGHT):
            player.turn(1)
            changed = True
        elif key in (ord("j"), ord("J")):
            player.fly(1)
            vertical_input = True
            changed = True
        elif key in (ord("k"), ord("K")):
            player.fly(-1)
            vertical_input = True
            changed = True
        elif key in (ord("r"), ord("R")):
            player.look(1)
            changed = True
        elif key in (ord("f"), ord("F")):
            player.look(-1)
            changed = True
        elif key in (ord("e"), ord("E")):
            gathered = player.interact(world)
            state["message"] = f"gathered {gathered}" if gathered else "(nothing nearby to gather)"
            changed = True
        elif key in (ord("p"), ord("P")):
            state["pov_mode"] = (state["pov_mode"] + 1) % len(POV_NAMES)
            state["message"] = f"POV: {POV_NAMES[state['pov_mode']]}"
            changed = True
        elif key in (ord("t"), ord("T")):
            state["show_crafting"] = True
            state["show_inventory"] = False
            state["show_map"] = False
            changed = True
        elif key in (ord("m"), ord("M")):
            state["show_map"] = not state["show_map"]
            state["show_inventory"] = False
            changed = True
        elif key in (ord("i"), ord("I")):
            state["show_inventory"] = not state["show_inventory"]
            state["show_map"] = False
            changed = True
        elif key in (ord("l"), ord("L")):
            state["show_legend"] = not state["show_legend"]
            changed = True
        elif key in (ord("c"), ord("C")):
            state["size_mode"] = (state["size_mode"] + 1) % len(SIZE_MODES)
            changed = True
        elif key == curses.KEY_RESIZE:
            changed = True

    return False, vertical_input, changed


def draw_crafting(stdscr, player, state, max_y, max_x, y_origin):
    stdscr.addstr(y_origin, 0, "CRAFTING — w/s select, e/Enter craft, t close"[: max_x - 1])
    for index, recipe in enumerate(RECIPES):
        row = y_origin + 2 + index
        if row >= max_y - 2:
            break
        marker = ">" if index == state["craft_index"] else " "
        available = "READY" if player.inv.has(recipe.ingredients) else "need"
        line = (
            f"{marker} {recipe.output_count}x {recipe.name:<16} "
            f"[{available}]  {recipe.ingredient_text()}"
        )
        stdscr.addstr(row, 0, line[: max_x - 1])


def draw_frame(stdscr, world, player, state, cloud_time):
    """Draw the HUD and whichever world view is currently active."""
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()
    mode_name, cap_width, cap_height = SIZE_MODES[state["size_mode"]]
    legend_width = (26 if max_x > 86 else 20) if state["show_legend"] and max_x > 60 else 0
    width = max(12, min(max_x - 2 - legend_width, cap_width))
    height = max(6, min(max_y - 7, cap_height))

    try:
        _distance, look_kind, look_key, _extra = raymarch_pixel(
            world,
            player.x,
            player.y,
            player.z + EYE_OFFSET,
            player.yaw,
            player.pitch,
            BASE_VIEW_DIST,
        )
        if look_kind == "ground":
            looking_at = BIOME_NAMES.get(look_key, "?")
        elif look_kind in ("object", "structure"):
            looking_at = look_key
        else:
            looking_at = "sky"

        status = f"pos:({player.x:.1f},{player.y:.1f},{player.z:.1f})  looking at: {looking_at}"
        fps_text = f"{state['fps']:5.1f} FPS"
        fps_x = max(0, max_x - legend_width - len(fps_text) - 1)
        stdscr.addstr(0, 0, status[: max(0, fps_x - 1)])
        view_name = POV_NAMES[state["pov_mode"]]
        stdscr.addstr(1, 0, f"VIEW {state['pov_mode'] + 1}/3: {view_name}"[: max_x - 1])
        stdscr.addstr(2, 0, f"inv:{player.inv.compact()}"[: max_x - 1])
        if max_x > len(fps_text) + 1:
            stdscr.addstr(0, fps_x, fps_text)

        visible_items = state.get("visible_items", {})
        if state["show_crafting"]:
            draw_crafting(stdscr, player, state, max_y, max_x - legend_width, 3)
        elif state["show_inventory"]:
            for index, line in enumerate(player.inv.full_lines()):
                if 3 + index < max_y - 1:
                    stdscr.addstr(3 + index, 0, line[: max_x - 1])
        elif state["show_map"]:
            visible_items = render_topdown(stdscr, world, player, width, height, 3, stride=3)
        elif state["pov_mode"] == 1:
            visible_items = render_topdown(stdscr, world, player, width, height, 3, stride=1)
        elif state["pov_mode"] == 2:
            camera = third_person_origin(player)
            visible_items = render_raymarch(
                stdscr, world, *camera, width, height, 3, cloud_time, marker="player"
            )
        else:
            visible_items = render_raymarch(
                stdscr,
                world,
                player.x,
                player.y,
                player.z + EYE_OFFSET,
                player.yaw,
                player.pitch,
                width,
                height,
                3,
                cloud_time,
                marker="crosshair",
            )
        state["visible_items"] = visible_items

        if legend_width:
            render_legend(stdscr, max_y, max_x, legend_width, visible_items)

        log_row = 3 + height
        if not state["show_inventory"] and not state["show_crafting"] and log_row < max_y - 1:
            stdscr.addstr(log_row, 0, state["message"][: max_x - 1])

        controls = (
            "w/s move a/d turn j/k up-down r/f look e gather t craft p pov m map i inv "
            f"l legend[{'on' if state['show_legend'] else 'off'}] "
            f"c size[{mode_name}] q quit"
        )
        stdscr.addstr(max_y - 1, 0, controls[: max_x - 1])
    except curses.error:
        pass

    stdscr.refresh()


def main(stdscr):
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    stdscr.nodelay(True)
    stdscr.timeout(0)
    init_colors()

    world = World()
    player = Player(0, 0, world)
    state = {
        # The small viewport sustains the 60 FPS input loop on typical terminals;
        # larger modes remain available with `c` when size matters more than FPS.
        "size_mode": 1,
        "pov_mode": 0,
        "show_map": False,
        "show_inventory": False,
        "show_crafting": False,
        "craft_index": 0,
        "show_legend": True,
        "visible_items": {},
        "fps": 1.0 / FRAME_DELAY,
        "message": (
            f"Seed {world.seed} — wander freely. "
            "e=gather t=craft p=pov m=map i=inv c=size q=quit"
        ),
    }
    last_frame = time.time()
    last_draw = 0.0
    cloud_time = 0.0

    while True:
        frame_started = time.time()
        dt = min(frame_started - last_frame, 0.1)
        last_frame = frame_started
        cloud_time += dt * 0.3
        if dt >= 0.001:
            instant_fps = min(240.0, 1.0 / dt)
            state["fps"] = state["fps"] * 0.9 + instant_fps * 0.1

        should_quit, vertical_input, input_changed = handle_input(stdscr, player, world, state)
        if should_quit:
            return
        old_z = player.z
        if not vertical_input:
            player.gravity_ease(world, dt)
        gravity_changed = player.z != old_z

        clouds_visible = (
            not state["show_inventory"]
            and not state["show_crafting"]
            and not state["show_map"]
            and state["pov_mode"] != 1
        )
        animation_due = clouds_visible and frame_started - last_draw >= 0.2
        if input_changed or gravity_changed or animation_due or last_draw == 0.0:
            draw_frame(stdscr, world, player, state, cloud_time)
            last_draw = frame_started
        elapsed = time.time() - frame_started
        time.sleep(max(0.0, FRAME_DELAY - elapsed))


if __name__ == "__main__":
    curses.wrapper(main)
