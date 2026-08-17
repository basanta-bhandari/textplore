"""Semantic terminal colors and the on-screen legend."""

import curses


COLOR_NAME_TO_PAIR = {}

EXTENDED_PALETTE = {
    "ocean": (33, False),
    "ocean_deep": (25, False),
    "plains": (222, False),
    "grassland": (34, False),
    "forest": (22, False),
    "mountain": (245, False),
    "peak": (255, True),
    "cave": (236, False),
    "sky": (81, False),
    "cloud": (255, False),
    "wood": (94, False),
    "stone": (248, False),
    "ore": (178, False),
    "berry": (197, False),
    "fiber": (229, False),
    "clay": (173, False),
    "fiber": (229, False),
    "herb": (76, False),
    "mushroom": (201, False),
    "coal": (240, False),
    "crystal": (51, True),
    "sand": (223, False),
    "dungeon": (244, True),
    "lighthouse": (231, True),
    "ui": (250, False),
    "player": (46, True),
}

BASE_PALETTE = {
    "ocean": ("BLUE", False),
    "ocean_deep": ("BLUE", False),
    "plains": ("YELLOW", False),
    "grassland": ("GREEN", False),
    "forest": ("GREEN", True),
    "mountain": ("WHITE", False),
    "peak": ("WHITE", True),
    "cave": ("BLACK", True),
    "sky": ("CYAN", False),
    "cloud": ("WHITE", False),
    "wood": ("YELLOW", True),
    "stone": ("WHITE", False),
    "ore": ("YELLOW", False),
    "berry": ("RED", False),
    "fiber": ("YELLOW", False),
    "clay": ("RED", True),
    "fiber": ("YELLOW", False),
    "herb": ("GREEN", True),
    "mushroom": ("MAGENTA", False),
    "coal": ("BLACK", True),
    "crystal": ("CYAN", True),
    "sand": ("YELLOW", False),
    "dungeon": ("WHITE", False),
    "lighthouse": ("WHITE", True),
    "ui": ("WHITE", False),
    "player": ("GREEN", True),
}

LEGEND_ITEMS = [
    ("ocean", "~", "ocean/lake"),
    ("plains", ",", "plains"),
    ("grassland", ".", "grassland"),
    ("forest", '"', "forest"),
    ("mountain", "^", "mountain"),
    ("peak", "A", "peak/snow"),
    ("cave", ":", "cave"),
    ("wood", "T", "tree"),
    ("stone", "#", "rock"),
    ("ore", "*", "ore"),
    ("berry", "o", "berries"),
    ("clay", "%", "clay"),
    ("cloud", "#", "cloud (sky)"),
]


def init_colors():
    COLOR_NAME_TO_PAIR.clear()
    try:
        curses.start_color()
    except curses.error:
        return
    try:
        curses.use_default_colors()
        background = -1
    except curses.error:
        background = curses.COLOR_BLACK
    if curses.COLORS <= 0 or curses.COLOR_PAIRS <= 1:
        return

    extended = curses.can_change_color() or curses.COLORS >= 256
    palette = EXTENDED_PALETTE if extended else BASE_PALETTE

    for pair_id, (name, (color, bold)) in enumerate(palette.items(), start=1):
        if pair_id >= curses.COLOR_PAIRS:
            break
        if not extended:
            color = getattr(curses, f"COLOR_{color}")
        try:
            curses.init_pair(pair_id, color, background)
        except curses.error:
            COLOR_NAME_TO_PAIR[name] = (0, curses.A_BOLD if bold else 0)
            continue
        COLOR_NAME_TO_PAIR[name] = (pair_id, curses.A_BOLD if bold else 0)


def attr_for(name, extra_bold=False):
    pair, bold = COLOR_NAME_TO_PAIR.get(name, COLOR_NAME_TO_PAIR.get("ui", (0, 0)))
    return curses.color_pair(pair) | bold | (curses.A_BOLD if extra_bold else 0)


def render_legend(stdscr, max_y, max_x, legend_width):
    x_origin = max_x - legend_width
    if x_origin < 0:
        return
    try:
        stdscr.addstr(0, x_origin, "-- legend --"[:legend_width])
        for index, (color_key, glyph, label) in enumerate(LEGEND_ITEMS):
            row = 1 + index
            if row >= max_y - 1:
                break
            stdscr.addstr(row, x_origin, glyph, attr_for(color_key))
            stdscr.addstr(row, x_origin + 2, label[: legend_width - 3])
    except curses.error:
        pass
