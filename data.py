import json
from pathlib import Path

# This file loads all of the JSON data and shared paths used by the game.
# Keeping it separate makes the main battle file easier to read.

# Paths to the project folder and each data file.
BASE_DIR = Path(__file__).resolve().parent
POKEMON_DATA_PATH = BASE_DIR / "pokemon.json"
MOVES_DATA_PATH = BASE_DIR / "moves.json"
TYPE_CHART_PATH = BASE_DIR / "typechart.json"
CONFIG_PATH = BASE_DIR / "config.json"
TYPE_COLORS_PATH = BASE_DIR / "type_colors.json"
BACKGROUND_PATH = BASE_DIR / "background.webp"
FRONT_SPRITE_DIR = BASE_DIR / "front_sprites"
BACK_SPRITE_DIR = BASE_DIR / "back_sprites"

WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 860

def load_json(path: Path) -> dict:
    """Read one JSON file and turn it into a Python dictionary.

    If something goes wrong, return an empty dictionary so the program
    does not crash immediately while loading startup data.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

# These variables are loaded once at startup and then reused everywhere else.
POKEMON_DB = load_json(POKEMON_DATA_PATH)
MOVES_DB = load_json(MOVES_DATA_PATH)
TYPE_DATA = load_json(TYPE_CHART_PATH)
CONFIG = load_json(CONFIG_PATH)
TYPE_COLORS = load_json(TYPE_COLORS_PATH)
POKEMON_NAMES = tuple(POKEMON_DB.keys())
