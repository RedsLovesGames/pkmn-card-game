from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Protocol, Tuple, cast
import struct

import graphics
from data import (
    BACK_SPRITE_DIR,
    CONFIG,
    FRONT_SPRITE_DIR,
    POKEMON_DB,
    POKEMON_NAMES,
    TYPE_COLORS,
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
)
from graphics import GraphWin, Image, Line, Oval, Point, Rectangle, Text, update as graphics_update


class Drawable(Protocol):
    def draw(self, graphwin: GraphWin) -> None:
        ...

    def undraw(self) -> None:
        ...


BUTTON_TEXT_NUDGE = 0.0
CENTER_TEXT_NUDGE = 0.0
TOP_LEFT_TEXT_NUDGE = 0.0
BATTLE_LOG_WRAP_WIDTH = 396
RESULT_WRAP_WIDTH = 360
MOVE_CARD_LAYOUT = {
    "left_col_x": 10,
    "right_col_x": 132,
    "right_col_width": 96,
    "name_y": 4,
    "power_y": 18,
    "meta_y": 31,
    "accuracy_y": 4,
    "effect_y": 22,
    "effect_max_lines": 2,
}

MeasureTextFn = Callable[[str, int, str], Tuple[int, int]]


def _graphics_measure_text(value: str, size: int, style: str) -> Tuple[int, int]:
    measure = getattr(graphics, "measure_text", None)
    if callable(measure):
        typed_measure = cast(MeasureTextFn, measure)
        return typed_measure(value, size, style)

    legacy_measure = getattr(graphics, "_measure_text", None)
    if callable(legacy_measure):
        typed_legacy_measure = cast(MeasureTextFn, legacy_measure)
        return typed_legacy_measure(value, size, style)

    raise AttributeError("graphics module does not expose a text measurement helper")


def rgb_to_hex(color: Tuple[int, int, int]) -> str:
    return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"


def blend_with_white(color: Tuple[int, int, int], amount: float) -> Tuple[int, int, int]:
    red = int(color[0] + (255 - color[0]) * amount)
    green = int(color[1] + (255 - color[1]) * amount)
    blue = int(color[2] + (255 - color[2]) * amount)
    return (red, green, blue)


def type_color_rgb(type_name: str) -> Tuple[int, int, int]:
    color = TYPE_COLORS.get(type_name, (180, 180, 180))
    return (int(color[0]), int(color[1]), int(color[2]))


def get_sprite_path(name: str, is_back: bool) -> Optional[str]:
    folder = BACK_SPRITE_DIR if is_back else FRONT_SPRITE_DIR
    gif_path = folder / f"{name.lower()}.gif"
    if gif_path.exists():
        return str(gif_path)
    return None


@dataclass
class Rect:
    x: int
    y: int
    width: int
    height: int

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height


@dataclass
class ButtonState:
    label: str
    rect: Rect
    event_id: str
    enabled: bool = True
    fill: Tuple[int, int, int] = (245, 245, 238)
    text_color: Tuple[int, int, int] = (28, 28, 28)
    border_color: Tuple[int, int, int] = (50, 50, 50)


@dataclass
class SelectionCardState:
    name: str
    poke_type: str
    selected: bool
    rect: Rect
    button: ButtonState


@dataclass
class MoveCardState:
    rect: Rect
    event_id: str
    name_text: str
    power_text: str
    meta_text: str
    accuracy_text: str
    effect_text: str
    move_type: str
    enabled: bool


@dataclass
class PokemonHudState:
    name: str
    poke_type: str
    status: Optional[str]
    current_hp: int
    max_hp: int
    hp_display: float


@dataclass
class SpriteState:
    name: str
    is_back: bool
    size: Tuple[int, int]
    pos: Tuple[int, int]


@dataclass
class SwitchOptionState:
    label: str
    rect: Rect
    event_id: str
    enabled: bool


@dataclass
class SelectionScreenState:
    title: str
    summary: str
    cards: List[SelectionCardState]
    start_button: ButtonState
    clear_button: ButtonState


@dataclass
class BattleScreenState:
    mode_label: str
    battle_log_text: str
    enemy_hud: PokemonHudState
    player_hud: PokemonHudState
    enemy_sprite: SpriteState
    player_sprite: SpriteState
    move_cards: List[MoveCardState]
    switch_button: ButtonState
    back_button: ButtonState
    quit_button: ButtonState


@dataclass
class SwitchOverlayState:
    title: str
    options: List[SwitchOptionState]
    close_button: Optional[ButtonState]


@dataclass
class ResultOverlayState:
    header: str
    subtext: str
    header_color: Tuple[int, int, int]
    back_button: ButtonState


class GraphicsRenderer:
    def __init__(self) -> None:
        self.win: Optional[GraphWin] = None
        self._hitboxes: List[Tuple[Rect, str, bool]] = []
        self._drawn_items: List[Drawable] = []
        self._sprite_cache: Dict[Tuple[str, bool, Tuple[int, int]], Optional[str]] = {}
        self._image_size_cache: Dict[str, Tuple[int, int]] = {}

    def create_window(self) -> None:
        self.win = GraphWin("Pokemon Battle", WINDOW_WIDTH, WINDOW_HEIGHT, autoflush=False)
        self.win.setBackground(rgb_to_hex((31, 34, 41)))

    def close_window(self) -> None:
        if self.win:
            self.win.close()

    def is_open(self) -> bool:
        return bool(self.win and not self.win.isClosed())

    def _get_win(self) -> GraphWin:
        if self.win is None:
            raise RuntimeError("Renderer window has not been created")
        return self.win

    def begin_frame(self) -> None:
        if not self.win:
            return
        for item in reversed(self._drawn_items):
            item.undraw()
        self._drawn_items = []
        self._hitboxes = []

    def end_frame(self) -> None:
        if self.win:
            graphics_update()

    def get_input_events(self) -> List[str]:
        if not self.win:
            return []
        point = self.win.checkMouse()
        if point is None:
            return []
        for rect, event_id, enabled in reversed(self._hitboxes):
            if enabled and rect.contains(point.x, point.y):
                return [event_id]
        return []

    def load_sprite(self, name: str, is_back: bool, size: Tuple[int, int]) -> Optional[str]:
        normalized_size = (int(size[0]), int(size[1]))
        key = (name, is_back, normalized_size)
        if key not in self._sprite_cache:
            self._sprite_cache[key] = get_sprite_path(name, is_back)
        return self._sprite_cache[key]

    def _get_image_size(self, image_path: str) -> Tuple[int, int]:
        cached = self._image_size_cache.get(image_path)
        if cached is not None:
            return cached

        image_file = Path(image_path)
        data = image_file.read_bytes()
        if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
            width, height = struct.unpack(">II", data[16:24])
        elif data[:3] == b"GIF" and len(data) >= 10:
            width, height = struct.unpack("<HH", data[6:10])
        else:
            width, height = (96, 96)
        size = (int(width), int(height))
        self._image_size_cache[image_path] = size
        return size

    def draw_selection_screen(self, state: SelectionScreenState) -> None:
        self._draw_top_left_label(36, 28, state.title, (245, 245, 245), size=22, style="bold")
        self._draw_top_left_label(36, 56, state.summary, (245, 245, 245), size=12)
        self._draw_line(36, 82, WINDOW_WIDTH - 36, 82, (220, 220, 220), 2)

        for card in state.cards:
            self._draw_selection_card(card)

        self._draw_button(state.start_button)
        self._draw_button(state.clear_button)

    def draw_battle_screen(self, state: BattleScreenState) -> None:
        field_origin = (20, 20)
        self._draw_field_panel(field_origin)
        self._draw_standing_spots(field_origin)
        self._draw_hud(state.enemy_hud, field_origin[0] + 42, field_origin[1] + 34, 342, "FOE", (196, 72, 86))
        self._draw_hud(state.player_hud, field_origin[0] + 536, field_origin[1] + 286, 382, "YOU", (68, 132, 212))
        self._draw_sprite(state.enemy_sprite, field_origin)
        self._draw_sprite(state.player_sprite, field_origin)

        self._draw_top_left_label(26, 426, state.mode_label, (245, 245, 245), size=12)
        self._draw_panel(Rect(20, 446, 430, 126), fill=(244, 244, 236), border=(50, 50, 50), border_width=3)
        self._draw_wrapped_top_left_block(36, 464, state.battle_log_text, BATTLE_LOG_WRAP_WIDTH, (24, 24, 24), size=13)

        self._draw_panel(Rect(464, 446, 516, 126), fill=(244, 244, 236), border=(50, 50, 50), border_width=3)
        for move_card in state.move_cards:
            self._draw_move_card(move_card)

        self._draw_button(state.switch_button)
        self._draw_button(state.back_button)
        self._draw_button(state.quit_button)

    def draw_switch_overlay(self, state: SwitchOverlayState) -> None:
        self._draw_scrim()
        panel = Rect(305, 210, 390, 300)
        self._draw_panel(panel, fill=(244, 244, 236), border=(50, 50, 50), border_width=3)
        self._draw_top_left_label(panel.x + 18, panel.y + 18, state.title, (24, 24, 24), size=16, style="bold")
        self._draw_line(panel.x + 18, panel.y + 48, panel.x + panel.width - 18, panel.y + 48, (120, 120, 120), 1)
        for option in state.options:
            self._draw_button(ButtonState(option.label, option.rect, option.event_id, option.enabled))
        if state.close_button:
            self._draw_button(state.close_button)

    def draw_result_overlay(self, state: ResultOverlayState) -> None:
        self._draw_scrim()
        panel = Rect(290, 200, 420, 240)
        self._draw_panel(panel, fill=(244, 244, 236), border=(50, 50, 50), border_width=3)
        self._draw_top_left_label(panel.x + 22, panel.y + 26, state.header, state.header_color, size=24, style="bold")
        self._draw_wrapped_top_left_block(panel.x + 22, panel.y + 76, state.subtext, RESULT_WRAP_WIDTH, (68, 68, 68), size=13)
        self._draw_button(state.back_button)

    def _draw_selection_card(self, card: SelectionCardState) -> None:
        fill = (241, 241, 236) if not card.selected else (224, 241, 224)
        self._draw_panel(card.rect, fill=fill, border=(65, 68, 74), border_width=3)
        card_sprite_size = (int(CONFIG["layout"]["card_sprite"][0]), int(CONFIG["layout"]["card_sprite"][1]))
        sprite_path = self.load_sprite(card.name, False, CONFIG["layout"]["card_sprite"])
        if sprite_path:
            self._draw_image(
                card.rect.x + 31 + card_sprite_size[0] // 2,
                card.rect.y + 16 + card_sprite_size[1] // 2,
                sprite_path,
            )
        else:
            self._draw_panel(Rect(card.rect.x + 31, card.rect.y + 16, card_sprite_size[0], card_sprite_size[1]), fill=(245, 245, 245), border=(40, 40, 40), border_width=2)
            self._draw_center_label(card.rect.x + 73, card.rect.y + 58, card.name.upper()[:10], (30, 30, 30), size=9, style="bold")
        self._draw_top_left_label(card.rect.x + 8, card.rect.y + 100, card.name, (24, 24, 24), size=12)
        self._draw_top_left_label(card.rect.x + 8, card.rect.y + 124, card.poke_type.upper(), type_color_rgb(card.poke_type), size=11, style="bold")
        self._draw_button(card.button)

    def _draw_move_card(self, card: MoveCardState) -> None:
        base_fill = type_color_rgb(card.move_type)
        fill = base_fill if card.enabled else blend_with_white(base_fill, 0.45)
        text_color = (255, 255, 255) if sum(base_fill) < 380 else (24, 24, 24)
        self._draw_panel(card.rect, fill=fill, border=(50, 50, 50), border_width=2)
        self._register_hitbox(card.rect, card.event_id, card.enabled)

        left_col_x = card.rect.x + MOVE_CARD_LAYOUT["left_col_x"]
        right_col_x = card.rect.x + MOVE_CARD_LAYOUT["right_col_x"]
        right_col_width = MOVE_CARD_LAYOUT["right_col_width"]

        self._draw_top_left_label(
            left_col_x,
            card.rect.y + MOVE_CARD_LAYOUT["name_y"],
            card.name_text,
            text_color,
            size=11,
            style="bold",
        )
        if card.accuracy_text:
            accuracy_text = self._truncate_line(card.accuracy_text, right_col_width, size=8, style="bold")
            accuracy_width, _ = self._measure_text_size(accuracy_text, size=8, style="bold")
            accuracy_left = right_col_x + max(0, right_col_width - accuracy_width)
            self._draw_top_left_label(
                accuracy_left,
                card.rect.y + MOVE_CARD_LAYOUT["accuracy_y"],
                accuracy_text,
                text_color,
                size=8,
                style="bold",
            )
        self._draw_top_left_label(left_col_x, card.rect.y + MOVE_CARD_LAYOUT["power_y"], card.power_text, text_color, size=9)
        self._draw_top_left_label(left_col_x, card.rect.y + MOVE_CARD_LAYOUT["meta_y"], card.meta_text, text_color, size=9)
        self._draw_wrapped_top_left_block(
            right_col_x,
            card.rect.y + MOVE_CARD_LAYOUT["effect_y"],
            card.effect_text,
            MOVE_CARD_LAYOUT["right_col_width"],
            text_color,
            size=8,
            max_lines=MOVE_CARD_LAYOUT["effect_max_lines"],
        )

    def _draw_hud(
        self,
        hud: PokemonHudState,
        x: int,
        y: int,
        width: int,
        prefix: str,
        prefix_color: Tuple[int, int, int],
    ) -> None:
        self._draw_panel(Rect(x, y, width, 96), fill=(244, 244, 236), border=(50, 50, 50), border_width=3)
        self._draw_top_left_label(x + 12, y + 14, prefix, prefix_color, size=12, style="bold")
        status_suffix = f" ({hud.status.upper()})" if hud.status else ""
        self._draw_top_left_label(x + 60, y + 14, f"{hud.name.upper()}  |  {hud.poke_type.upper()}{status_suffix}", (24, 24, 24), size=12)
        bar_width = 260 if prefix == "FOE" else 300
        ratio = hud.hp_display / hud.max_hp if hud.max_hp else 0.0
        self._draw_progress_bar(Rect(x + 12, y + 42, bar_width, 16), ratio, prefix_color)
        hp_text = f"HP {int(max(0, hud.hp_display))}/{hud.max_hp}" if hud.hp_display > 0 else f"HP 0/{hud.max_hp}  |  FAINTED"
        self._draw_top_left_label(x + 12, y + 66, hp_text, (68, 68, 68), size=11)

    def _draw_field_panel(self, origin: Tuple[int, int]) -> None:
        field_w, field_h = CONFIG["layout"]["field_size"]
        self._draw_panel(Rect(origin[0], origin[1], field_w, field_h), fill=(218, 234, 255), border=(50, 50, 50), border_width=3)
        self._draw_panel(Rect(origin[0], origin[1] + 232, field_w, field_h - 232), fill=(198, 228, 171), border=(198, 228, 171), border_width=0)
        self._draw_panel(Rect(origin[0], origin[1] + 282, field_w, field_h - 282), fill=(172, 212, 142), border=(172, 212, 142), border_width=0)

    def _draw_standing_spots(self, origin: Tuple[int, int]) -> None:
        for x1, y1, x2, y2 in ((612, 214, 932, 280), (52, 328, 364, 392)):
            oval = Oval(Point(origin[0] + x1, origin[1] + y1), Point(origin[0] + x2, origin[1] + y2))
            oval.setFill(rgb_to_hex((126, 188, 103)))
            oval.setOutline(rgb_to_hex((84, 126, 69)))
            oval.setWidth(2)
            self._draw_object(oval)

    def _draw_sprite(self, sprite: SpriteState, field_origin: Tuple[int, int]) -> None:
        sprite_path = self.load_sprite(sprite.name, sprite.is_back, sprite.size)
        draw_left = field_origin[0] + sprite.pos[0]
        draw_top = field_origin[1] + sprite.pos[1]
        anchor_x = draw_left + sprite.size[0] // 2
        anchor_y = draw_top + sprite.size[1] // 2
        if sprite_path:
            image_width, image_height = self._get_image_size(sprite_path)
            scale = 1
            if image_width > 0 and image_height > 0:
                scale = int(max(1, min(sprite.size[0] // image_width, sprite.size[1] // image_height)))
            self._draw_image(anchor_x, anchor_y, sprite_path, scale=scale)
        else:
            self._draw_panel(Rect(draw_left, draw_top, sprite.size[0], sprite.size[1]), fill=(245, 245, 245), border=(40, 40, 40), border_width=3)
            self._draw_center_label(anchor_x, anchor_y, sprite.name.upper()[:10], (30, 30, 30), size=10, style="bold")

    def _draw_button(self, button: ButtonState) -> None:
        fill = button.fill if button.enabled else blend_with_white(button.fill, 0.45)
        text_color = button.text_color if button.enabled else (120, 120, 120)
        self._draw_panel(button.rect, fill=fill, border=button.border_color, border_width=2)
        self._draw_center_label(button.rect.x + button.rect.width // 2, button.rect.y + button.rect.height // 2, button.label, text_color, size=11, style="bold", y_nudge=BUTTON_TEXT_NUDGE)
        self._register_hitbox(button.rect, button.event_id, button.enabled)

    def _draw_progress_bar(self, rect: Rect, ratio: float, fill_color: Tuple[int, int, int]) -> None:
        ratio = max(0.0, min(1.0, ratio))
        self._draw_panel(rect, fill=(58, 58, 66), border=(58, 58, 66), border_width=1)
        inner_width = int((rect.width - 2) * ratio)
        if inner_width > 0:
            self._draw_panel(Rect(rect.x + 1, rect.y + 1, inner_width, rect.height - 2), fill=fill_color, border=fill_color, border_width=0)

    def _draw_scrim(self) -> None:
        self._draw_panel(Rect(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT), fill=(22, 22, 22), border=(22, 22, 22), border_width=0)

    def _draw_panel(self, rect: Rect, fill: Tuple[int, int, int], border: Tuple[int, int, int], border_width: int = 1) -> None:
        box = Rectangle(Point(rect.x, rect.y), Point(rect.x + rect.width, rect.y + rect.height))
        box.setFill(rgb_to_hex(fill))
        box.setOutline(rgb_to_hex(border))
        box.setWidth(border_width)
        self._draw_object(box)

    def _draw_center_label(
        self,
        center_x: int,
        center_y: int,
        value: str,
        color: Tuple[int, int, int],
        size: int = 12,
        style: str = "normal",
        y_nudge: float = CENTER_TEXT_NUDGE,
    ) -> None:
        text = Text(Point(center_x, center_y + y_nudge), value)
        text.setTextColor(rgb_to_hex(color))
        text.setSize(size)
        text.setStyle(style)
        self._draw_object(text)

    def _draw_top_left_label(
        self,
        left: int,
        top: int,
        value: str,
        color: Tuple[int, int, int],
        size: int = 12,
        style: str = "normal",
    ) -> None:
        line_width, line_height = self._measure_text_size(value, size, style)
        center_x = left + line_width / 2.0
        center_y = top + line_height / 2.0 + TOP_LEFT_TEXT_NUDGE
        self._draw_center_label(int(round(center_x)), int(round(center_y)), value, color, size=size, style=style, y_nudge=0.0)

    def _draw_top_left_block(
        self,
        left: int,
        top: int,
        lines: List[str],
        color: Tuple[int, int, int],
        size: int = 12,
        style: str = "normal",
    ) -> None:
        line_height = self._line_height(size)
        for index, line in enumerate(lines or [""]):
            line_width, _ = self._measure_text_size(line, size, style)
            center_x = left + line_width / 2.0
            center_y = top + index * line_height + line_height / 2.0 + TOP_LEFT_TEXT_NUDGE
            self._draw_center_label(int(round(center_x)), int(round(center_y)), line, color, size=size, style=style, y_nudge=0.0)

    def _draw_wrapped_top_left_block(
        self,
        left: int,
        top: int,
        value: str,
        max_width: int,
        color: Tuple[int, int, int],
        size: int = 12,
        style: str = "normal",
        max_lines: Optional[int] = None,
    ) -> None:
        lines = self._wrap_text_lines(value, max_width, size=size, style=style, max_lines=max_lines)
        self._draw_top_left_block(left, top, lines, color, size=size, style=style)

    def _draw_line(self, x1: int, y1: int, x2: int, y2: int, color: Tuple[int, int, int], width: int) -> None:
        line = Line(Point(x1, y1), Point(x2, y2))
        line.setOutline(rgb_to_hex(color))
        line.setWidth(width)
        self._draw_object(line)

    def _draw_image(self, x: int, y: int, image_path: str, scale: int = 1) -> None:
        image = graphics.create_scaled_image(Point(x, y), image_path, scale)
        self._draw_object(image)

    def _register_hitbox(self, rect: Rect, event_id: str, enabled: bool) -> None:
        self._hitboxes.append((rect, event_id, enabled))

    def _draw_object(self, item: Drawable) -> None:
        item.draw(self._get_win())
        self._drawn_items.append(item)

    def _wrap_text_lines(
        self,
        value: str,
        max_width: int,
        size: int = 12,
        style: str = "normal",
        max_lines: Optional[int] = None,
    ) -> List[str]:
        max_width = max(1, int(max_width))
        lines: List[str] = []
        truncated = False
        for paragraph in value.splitlines() or [""]:
            if not paragraph:
                lines.append("")
                continue
            wrapped = self._wrap_paragraph_to_width(paragraph, max_width, size, style)
            for line in wrapped or [""]:
                if max_lines is not None and len(lines) >= max_lines:
                    truncated = True
                    break
                lines.append(line)
            if truncated:
                break
        if truncated and lines:
            lines[-1] = self._truncate_line(lines[-1], max_width, size, style)
        return lines

    def _wrap_paragraph_to_width(self, paragraph: str, max_width: int, size: int, style: str) -> List[str]:
        words = paragraph.split()
        if not words:
            return [""]

        lines: List[str] = []
        current = ""
        for word in words:
            if not current:
                if self._measure_text_size(word, size, style)[0] <= max_width:
                    current = word
                else:
                    broken = self._break_long_word(word, max_width, size, style)
                    lines.extend(broken[:-1])
                    current = broken[-1]
                continue

            candidate = f"{current} {word}"
            if self._measure_text_size(candidate, size, style)[0] <= max_width:
                current = candidate
                continue

            lines.append(current)
            if self._measure_text_size(word, size, style)[0] <= max_width:
                current = word
            else:
                broken = self._break_long_word(word, max_width, size, style)
                lines.extend(broken[:-1])
                current = broken[-1]

        if current:
            lines.append(current)
        return lines

    def _break_long_word(self, word: str, max_width: int, size: int, style: str) -> List[str]:
        parts: List[str] = []
        current = ""
        for char in word:
            candidate = current + char
            if current and self._measure_text_size(candidate, size, style)[0] > max_width:
                parts.append(current)
                current = char
            else:
                current = candidate
        if current:
            parts.append(current)
        return parts or [word]

    def _truncate_line(self, line: str, max_width: int, size: int, style: str) -> str:
        ellipsis = "..."
        text = line.rstrip()
        while text and self._measure_text_size(text + ellipsis, size, style)[0] > max_width:
            text = text[:-1].rstrip()
        return (text + ellipsis) if text else ellipsis

    def _measure_text_size(self, value: str, size: int, style: str) -> Tuple[int, int]:
        try:
            return _graphics_measure_text(value, size=size, style=style)
        except Exception:
            if not value:
                return (0, self._line_height(size))
            factor = 0.60 if "bold" in style else 0.56
            return (int(round(len(value) * size * factor)), self._line_height(size))

    def _line_height(self, size: int) -> int:
        try:
            return int(_graphics_measure_text("Ag", size=size, style="normal")[1])
        except Exception:
            return int(size + 5)


def build_selection_cards(selected_names: List[str]) -> List[SelectionCardState]:
    cards: List[SelectionCardState] = []
    card_width = 146
    card_height = 178
    gap_x = 10
    gap_y = 10
    start_x = 32
    start_y = 96

    for idx, name in enumerate(POKEMON_NAMES):
        row = idx // 6
        col = idx % 6
        rect = Rect(start_x + col * (card_width + gap_x), start_y + row * (card_height + gap_y), card_width, card_height)
        selected = name in selected_names
        button = ButtonState(
            label="Selected" if selected else "Select",
            rect=Rect(rect.x + 12, rect.y + 144, 118, 28),
            event_id=f"select:{name}",
            enabled=True,
            fill=(245, 245, 238) if not selected else (212, 234, 212),
        )
        cards.append(
            SelectionCardState(
                name=name,
                poke_type=POKEMON_DB[name]["type"],
                selected=selected,
                rect=rect,
                button=button,
            )
        )
    return cards
