from __future__ import annotations

import heapq
import random
import time
from typing import Callable, List, Optional, Tuple

from data import CONFIG
from logic import (
    _apply_secondary_effect,
    _build_action,
    _build_random_enemy_team,
    _check_status_effects,
    _resolve_turn_order,
    calculate_damage,
)
from models import BattleAction, Move, Pokemon
from ui import (
    BattleScreenState,
    ButtonState,
    GraphicsRenderer,
    MoveCardState,
    PokemonHudState,
    Rect,
    ResultOverlayState,
    SelectionScreenState,
    SpriteState,
    SwitchOptionState,
    SwitchOverlayState,
    build_selection_cards,
)


STATE_SELECT = "select"
STATE_BATTLE = "battle"

OUTCOME_CONTINUE = "continue"
OUTCOME_TURN_END = "turn_end"
OUTCOME_FORCE_SWITCH = "force_switch"
OUTCOME_BATTLE_END = "battle_end"

PLAYER_SIDE = "player"
ENEMY_SIDE = "enemy"

BATTLE_CONFIG = CONFIG["battle"]
LAYOUT = CONFIG["layout"]
PAUSE = BATTLE_CONFIG["pause"]
RUNTIME_CONFIG = CONFIG.get("runtime", {})
DEFAULT_TARGET_FPS = 24

TimelineEvent = Tuple[float, int, Callable[[], None]]
ActionCallback = Callable[[str], None]


class BattleApp:
    """Main battle controller backed by a graphics.py renderer."""

    def __init__(self, renderer: Optional[GraphicsRenderer] = None) -> None:
        self.renderer = renderer
        self.target_fps = self._resolve_target_fps()
        self.selected_names: List[str] = []
        self.player_team: List[Pokemon] = []
        self.enemy_team: List[Pokemon] = []
        self.state = STATE_SELECT
        self.running = True

        self.timeline: List[TimelineEvent] = []
        self.event_counter = 0

        self.p_idx = 0
        self.e_idx = 0
        self.busy = False
        self.force_switch = False
        self.player_sprite_pos: List[float] = []
        self.player_sprite_target: List[float] = []
        self.enemy_sprite_pos: List[float] = []
        self.enemy_sprite_target: List[float] = []
        self.player_hp_display = 1
        self.enemy_hp_display = 1
        self.mode_label = ""
        self.battle_log_text = ""
        self.switch_modal_visible = False
        self.result_modal_visible = False
        self.result_text = ""
        self.result_subtext = ""
        self.result_color = (24, 24, 24)
        self._reset_battle_runtime()

    def setup(self) -> None:
        if self.renderer is None:
            self.renderer = GraphicsRenderer()
        self.renderer.create_window()
        self.running = True

    def run(self) -> None:
        while self.running and self.renderer and self.renderer.is_open():
            self.update()
            self._handle_inputs()
            self._render()
            time.sleep(1 / self.target_fps)
        if self.renderer:
            self.renderer.close_window()

    def _resolve_target_fps(self) -> int:
        raw_target_fps = RUNTIME_CONFIG.get("fps", DEFAULT_TARGET_FPS)
        try:
            target_fps = int(raw_target_fps)
        except (TypeError, ValueError):
            target_fps = DEFAULT_TARGET_FPS
        return max(1, target_fps)

    def update(self) -> None:
        now = time.monotonic()
        while self.timeline and self.timeline[0][0] <= now:
            _, _, callback = heapq.heappop(self.timeline)
            callback()
        self._update_animations()

    def queue_call(self, delay: float, callback: Callable[[], None]) -> None:
        self.event_counter += 1
        event_time = time.monotonic() + max(0.0, delay)
        heapq.heappush(self.timeline, (event_time, self.event_counter, callback))

    def _handle_inputs(self) -> None:
        if not self.renderer:
            return
        for event_id in self.renderer.get_input_events():
            self._dispatch_event(event_id)

    def _dispatch_event(self, event_id: str) -> None:
        if event_id == "quit":
            self.running = False
            return

        if self.result_modal_visible:
            if event_id == "result_back":
                self.close_result_and_back()
            return

        if self.switch_modal_visible:
            if event_id == "switch_close" and not self.force_switch:
                self.switch_modal_visible = False
            elif event_id.startswith("switch_choice:"):
                self.confirm_switch(int(event_id.split(":", 1)[1]))
            return

        if self.state == STATE_SELECT:
            self._handle_selection_event(event_id)
        elif self.state == STATE_BATTLE:
            self._handle_battle_event(event_id)

    def _handle_selection_event(self, event_id: str) -> None:
        if event_id.startswith("select:"):
            self.toggle_selection(event_id.split(":", 1)[1])
        elif event_id == "clear_selection":
            self.clear_selection()
        elif event_id == "start_battle":
            self.start_battle()

    def _handle_battle_event(self, event_id: str) -> None:
        if event_id.startswith("move:"):
            self.choose_move(int(event_id.split(":", 1)[1]))
        elif event_id == "switch_menu":
            self.open_switch_menu()
        elif event_id == "back_to_select":
            self.back_to_select()

    def _render(self) -> None:
        if not self.renderer:
            return
        self.renderer.begin_frame()
        if self.state == STATE_SELECT:
            self.renderer.draw_selection_screen(self._build_selection_screen_state())
        elif self.state == STATE_BATTLE:
            self.renderer.draw_battle_screen(self._build_battle_screen_state())

        if self.switch_modal_visible:
            self.renderer.draw_switch_overlay(self._build_switch_overlay_state())
        if self.result_modal_visible:
            self.renderer.draw_result_overlay(self._build_result_overlay_state())
        self.renderer.end_frame()

    def _update_animations(self) -> None:
        self._animate_sprite(self.player_sprite_pos, self.player_sprite_target)
        self._animate_sprite(self.enemy_sprite_pos, self.enemy_sprite_target)
        self._animate_hp()

    def _animate_sprite(self, current: List[float], target: List[float]) -> None:
        for index in range(2):
            if abs(current[index] - target[index]) > 1:
                current[index] += (target[index] - current[index]) * 0.23
            else:
                current[index] = target[index]

    def _animate_hp(self) -> None:
        if self.state != STATE_BATTLE or not self.player_team or not self.enemy_team:
            return
        if not (0 <= self.p_idx < len(self.player_team) and 0 <= self.e_idx < len(self.enemy_team)):
            return

        player = self.player_team[self.p_idx]
        enemy = self.enemy_team[self.e_idx]
        self.player_hp_display = self._step_hp_display(self.player_hp_display, player.current_hp)
        self.enemy_hp_display = self._step_hp_display(self.enemy_hp_display, enemy.current_hp)

    def _step_hp_display(self, current: float, target: int) -> float:
        if current <= target:
            return float(target)
        delta = max(1, int((current - target) // 7) or 1)
        return float(max(target, current - delta))

    def toggle_selection(self, name: str) -> None:
        if name in self.selected_names:
            self.selected_names.remove(name)
        elif len(self.selected_names) < BATTLE_CONFIG["team_size"]:
            self.selected_names.append(name)

    def clear_selection(self) -> None:
        self.selected_names.clear()

    def start_battle(self) -> None:
        if len(self.selected_names) != BATTLE_CONFIG["team_size"]:
            return
        player_team = [Pokemon(name) for name in self.selected_names]
        enemy_team = _build_random_enemy_team(self.selected_names)
        self._enter_battle(player_team, enemy_team)

    def _enter_battle(self, player_team: List[Pokemon], enemy_team: List[Pokemon]) -> None:
        self.player_team = player_team
        self.enemy_team = enemy_team
        self.state = STATE_BATTLE
        self._reset_battle_runtime()
        self.busy = True
        self.mode_label = "Single Battle"
        self._set_active_player(0)
        self._set_active_enemy(0)
        self._set_log(f"Trainer wants to battle!\nThey sent out {self.enemy_team[self.e_idx].name.upper()}!")
        self.queue_call(PAUSE["sendout"], self._end_busy_phase)

    def _reset_battle_runtime(self) -> None:
        self.p_idx = 0
        self.e_idx = 0
        self.busy = False
        self.force_switch = False
        self.player_sprite_pos = list(LAYOUT["player_sprite_start"])
        self.player_sprite_target = list(LAYOUT["player_sprite_start"])
        self.enemy_sprite_pos = list(LAYOUT["enemy_sprite_start"])
        self.enemy_sprite_target = list(LAYOUT["enemy_sprite_start"])
        self.player_hp_display = 1
        self.enemy_hp_display = 1
        self.mode_label = ""
        self.battle_log_text = ""
        self._hide_overlays()
        self._reset_result_state()
        self._clear_timeline()

    def _hide_overlays(self) -> None:
        self.switch_modal_visible = False
        self.result_modal_visible = False

    def _reset_result_state(self) -> None:
        self.result_text = ""
        self.result_subtext = ""
        self.result_color = (24, 24, 24)

    def _clear_timeline(self) -> None:
        self.timeline.clear()
        self.event_counter = 0

    def _set_active_player(self, index: int) -> None:
        self.p_idx = index
        self.player_hp_display = float(self.player_team[index].current_hp)
        self.player_sprite_pos = list(LAYOUT["player_sprite_start"])
        self.player_sprite_target = list(LAYOUT["player_sprite_target"])

    def _set_active_enemy(self, index: int) -> None:
        self.e_idx = index
        self.enemy_hp_display = float(self.enemy_team[index].current_hp)
        self.enemy_sprite_pos = list(LAYOUT["enemy_sprite_start"])
        self.enemy_sprite_target = list(LAYOUT["enemy_sprite_target"])

    def _end_busy_phase(self) -> None:
        self.busy = False

    def _set_log(self, text: str) -> None:
        self.battle_log_text = text

    def _return_to_selection(self, keep_current_team: bool) -> None:
        if keep_current_team and self.player_team:
            self.selected_names = [mon.name for mon in self.player_team]
        self.state = STATE_SELECT
        self._reset_battle_runtime()

    def back_to_select(self) -> None:
        if self.busy or self.force_switch:
            return
        self._return_to_selection(keep_current_team=True)

    def close_result_and_back(self) -> None:
        self._return_to_selection(keep_current_team=False)

    def choose_move(self, move_index: int) -> None:
        if self.busy or self.force_switch or self.state != STATE_BATTLE:
            return

        player = self.player_team[self.p_idx]
        enemy = self.enemy_team[self.e_idx]
        if not player.alive or not enemy.alive:
            return

        player_action = _build_action(PLAYER_SIDE, player, enemy, move_index)
        enemy_action = _build_action(ENEMY_SIDE, enemy, player)
        first_action, second_action = _resolve_turn_order(player_action, enemy_action)
        first_action.can_flinch_target = True
        second_action.can_flinch_target = False
        self.busy = True
        self._perform_action(first_action, lambda outcome: self._after_first_action(outcome, second_action))

    def _after_first_action(self, outcome: str, second_action: BattleAction) -> None:
        if outcome != OUTCOME_CONTINUE:
            self.busy = False
            return
        if not second_action.user.alive or not second_action.target.alive:
            self.busy = False
            return
        self._perform_action(second_action, self._after_second_action)

    def _after_second_action(self, outcome: str) -> None:
        self.busy = False

    def _perform_action(self, action: BattleAction, callback: ActionCallback) -> None:
        if not action.user.alive:
            callback(OUTCOME_CONTINUE)
            return

        if action.kind == "recharge":
            self._perform_recharge_action(action, callback)
            return

        self._perform_attack_action(action, callback)

    def _perform_recharge_action(self, action: BattleAction, callback: ActionCallback) -> None:
        action.user.needs_recharge = False
        self._set_log(f"{action.actor_name} must recharge!")
        self.queue_call(PAUSE["message"], lambda: callback(OUTCOME_CONTINUE))

    def _perform_attack_action(self, action: BattleAction, callback: ActionCallback) -> None:
        move = action.move
        if move is None:
            callback(OUTCOME_CONTINUE)
            return

        status_text = _check_status_effects(action.user, action.side)
        if status_text:
            self._set_log(status_text)
            if self._status_blocks_action(status_text):
                self.queue_call(PAUSE["message"], lambda: callback(OUTCOME_CONTINUE))
                return

        damage, crit, type_mult = calculate_damage(action.user, action.target, move)
        self._set_log(f"{action.actor_name} used\n{move.name.upper()}!")
        move_hits = move.always_hits or random.uniform(0, 100) <= move.accuracy

        def after_animation() -> None:
            if not move_hits:
                self._set_log(f"{action.actor_name} used\n{move.name.upper()}!\nBut it missed!")
                self.queue_call(PAUSE["attack"], lambda: callback(OUTCOME_CONTINUE))
                return

            action.target.apply_damage(damage)
            if move.recharge and action.target.alive and BATTLE_CONFIG["hyper_beam_recharge_if_target_survives"]:
                action.user.needs_recharge = True

            self.queue_call(
                PAUSE["attack"],
                lambda: self._handle_attack_follow_up(action, move, damage, crit, type_mult, callback),
            )

        self._play_attack_animation(action.side, after_animation)

    def _handle_attack_follow_up(
        self,
        action: BattleAction,
        move: Move,
        damage: int,
        crit: bool,
        type_mult: float,
        callback: ActionCallback,
    ) -> None:
        extra_messages: List[str] = []
        if crit:
            extra_messages.append("Critical hit!")
        if type_mult > 1:
            extra_messages.append("It's super effective!")
        elif 0 < type_mult < 1:
            extra_messages.append("It's not very effective...")

        secondary_text = _apply_secondary_effect(
            move,
            action.user,
            action.target,
            damage,
            can_flinch_target=action.can_flinch_target,
        )
        if secondary_text:
            extra_messages.append(secondary_text)

        def after_messages() -> None:
            if action.target.current_hp <= 0:
                self._handle_faint(action.target, callback)
            else:
                callback(OUTCOME_CONTINUE)

        self._show_messages(extra_messages, after_messages)

    def _status_blocks_action(self, status_text: str) -> bool:
        return "Cannot move!" in status_text or "Hurt itself in confusion!" in status_text

    def _play_attack_animation(self, side: str, on_done: Callable[[], None]) -> None:
        player_base = list(LAYOUT["player_sprite_target"])
        enemy_base = list(LAYOUT["enemy_sprite_target"])
        self.player_sprite_target = player_base
        self.enemy_sprite_target = enemy_base

        if side == ENEMY_SIDE:
            self.enemy_sprite_target = [enemy_base[0] - 54, enemy_base[1] + 6]
            self.player_sprite_target = [player_base[0] - 24, player_base[1] + 4]
        else:
            self.player_sprite_target = [player_base[0] + 54, player_base[1] - 6]
            self.enemy_sprite_target = [enemy_base[0] + 24, enemy_base[1] - 4]

        def recoil() -> None:
            self.player_sprite_target = list(LAYOUT["player_sprite_target"])
            self.enemy_sprite_target = list(LAYOUT["enemy_sprite_target"])
            self.queue_call(0.18, on_done)

        self.queue_call(0.16, recoil)

    def _show_messages(self, messages: List[str], on_done: Callable[[], None], index: int = 0) -> None:
        if index >= len(messages):
            on_done()
            return
        self._set_log(messages[index])
        self.queue_call(PAUSE["message"], lambda: self._show_messages(messages, on_done, index + 1))

    def _handle_faint(self, fainted: Pokemon, callback: ActionCallback) -> None:
        self._set_log(f"{fainted.name.upper()}\nfainted!")
        if fainted in self.enemy_team:
            self._handle_enemy_faint(callback)
        else:
            self._handle_player_faint(callback)

    def _handle_enemy_faint(self, callback: ActionCallback) -> None:
        def after_enemy_faint() -> None:
            next_enemy_idx = self.e_idx + 1
            if next_enemy_idx >= len(self.enemy_team):
                self._finish_battle(True)
                callback(OUTCOME_BATTLE_END)
                return

            self._set_active_enemy(next_enemy_idx)
            self._set_log(f"Enemy sent out\n{self.enemy_team[self.e_idx].name.upper()}!")
            self.queue_call(PAUSE["sendout"], lambda: callback(OUTCOME_TURN_END))

        self.queue_call(PAUSE["faint"], after_enemy_faint)

    def _handle_player_faint(self, callback: ActionCallback) -> None:
        if not any(mon.alive for mon in self.player_team):
            self.queue_call(PAUSE["faint"], lambda: self._finish_battle(False))
            callback(OUTCOME_BATTLE_END)
            return

        self.queue_call(PAUSE["faint"], lambda: self._trigger_forced_switch(callback))

    def open_switch_menu(self, force: bool = False) -> None:
        if self.state != STATE_BATTLE:
            return
        if self.busy and not force:
            return
        if not force and not self._has_other_alive_player_mon():
            return

        self.switch_modal_visible = True
        if force and not self._has_other_alive_player_mon():
            self._finish_battle(False)

    def confirm_switch(self, new_index: int) -> None:
        if not (0 <= new_index < len(self.player_team)):
            return
        if new_index == self.p_idx or not self.player_team[new_index].alive:
            return

        was_forced = self.force_switch
        self.force_switch = False
        self.switch_modal_visible = False
        self._set_active_player(new_index)
        self._set_log(f"Go! {self.player_team[self.p_idx].name.upper()}!")
        if was_forced:
            self.busy = False
        else:
            self._handle_enemy_action_after_switch()

    def _handle_enemy_action_after_switch(self) -> None:
        self.busy = True
        enemy_action = _build_action(ENEMY_SIDE, self.enemy_team[self.e_idx], self.player_team[self.p_idx])
        enemy_action.can_flinch_target = False
        self.queue_call(PAUSE["switch"], lambda: self._perform_action(enemy_action, self._after_second_action))

    def _has_other_alive_player_mon(self) -> bool:
        return any(index != self.p_idx and mon.alive for index, mon in enumerate(self.player_team))

    def _trigger_forced_switch(self, callback: ActionCallback) -> None:
        if not any(mon.alive for mon in self.player_team):
            self._finish_battle(False)
            callback(OUTCOME_BATTLE_END)
            return

        self.force_switch = True
        self.busy = False
        self.open_switch_menu(force=True)
        callback(OUTCOME_FORCE_SWITCH)

    def _finish_battle(self, player_won: bool) -> None:
        self.busy = False
        self.force_switch = False
        self._clear_timeline()
        self.switch_modal_visible = False
        self.result_modal_visible = True
        self.result_text = "YOU WIN!" if player_won else "YOU LOSE..."
        self.result_color = (26, 160, 26) if player_won else (196, 44, 62)
        if player_won:
            self.result_subtext = "The opposing trainer is out of Pokemon. Return to team select to battle again."
        else:
            self.result_subtext = "Your team has no Pokemon left that can battle. Return to team select to try another run."

    def _build_selection_screen_state(self) -> SelectionScreenState:
        selected_text = ", ".join(self.selected_names) if self.selected_names else "none"
        return SelectionScreenState(
            title="Select 3 Pokemon",
            summary=f"Chosen: {selected_text}",
            cards=build_selection_cards(self.selected_names),
            start_button=ButtonState(
                "Start Battle",
                Rect(32, 654, 180, 42),
                "start_battle",
                enabled=len(self.selected_names) == BATTLE_CONFIG["team_size"],
                fill=(95, 126, 210),
                text_color=(255, 255, 255),
                border_color=(34, 44, 77),
            ),
            clear_button=ButtonState("Clear", Rect(226, 654, 120, 42), "clear_selection"),
        )

    def _build_battle_screen_state(self) -> BattleScreenState:
        player = self.player_team[self.p_idx]
        enemy = self.enemy_team[self.e_idx]
        can_choose_move = player.alive and enemy.alive and not self.busy and not self.force_switch

        return BattleScreenState(
            mode_label=self.mode_label,
            battle_log_text=self.battle_log_text,
            enemy_hud=PokemonHudState(enemy.name, enemy.type, enemy.status, enemy.current_hp, enemy.max_hp, self.enemy_hp_display),
            player_hud=PokemonHudState(player.name, player.type, player.status, player.current_hp, player.max_hp, self.player_hp_display),
            enemy_sprite=SpriteState(enemy.name, False, tuple(LAYOUT["enemy_sprite"]), (int(self.enemy_sprite_pos[0]), int(self.enemy_sprite_pos[1]))),
            player_sprite=SpriteState(player.name, True, tuple(LAYOUT["player_sprite"]), (int(self.player_sprite_pos[0]), int(self.player_sprite_pos[1]))),
            move_cards=self._build_move_cards(player, can_choose_move),
            switch_button=ButtonState(
                "Switch Pokemon",
                Rect(20, 590, 180, 42),
                "switch_menu",
                enabled=not self.busy and not self.force_switch and self._has_other_alive_player_mon(),
            ),
            back_button=ButtonState(
                "Back to Team Select",
                Rect(214, 590, 200, 42),
                "back_to_select",
                enabled=not self.busy and not self.force_switch,
            ),
            quit_button=ButtonState("Quit", Rect(428, 590, 120, 42), "quit"),
        )

    def _build_move_cards(self, player: Pokemon, enabled: bool) -> List[MoveCardState]:
        move_cards: List[MoveCardState] = []
        move_positions = [(478, 458), (724, 458), (478, 512), (724, 512)]

        for index, move in enumerate(player.moves):
            if player.needs_recharge:
                move_type = "Normal"
                name_text = "RECHARGE"
                power_text = ""
                meta_text = "NORMAL | Status"
                accuracy_text = ""
                effect_text = ""
            else:
                move_type = move.type
                name_text = move.name.upper()
                power_text = f"({move.power} BP)"
                meta_text = f"{move.type.upper()} | {move.category}"
                accuracy_text = "ACC --" if move.always_hits else f"ACC {move.accuracy}%"
                effect_text = move.secondary.get("description", "") if move.secondary else ""

            move_cards.append(
                MoveCardState(
                    rect=Rect(move_positions[index][0], move_positions[index][1], 238, 48),
                    event_id=f"move:{index}",
                    name_text=name_text,
                    power_text=power_text,
                    meta_text=meta_text,
                    accuracy_text=accuracy_text,
                    effect_text=effect_text,
                    move_type=move_type,
                    enabled=enabled,
                )
            )
        return move_cards

    def _build_switch_overlay_state(self) -> SwitchOverlayState:
        options: List[SwitchOptionState] = []
        panel_x = 333
        panel_y = 266
        for index, mon in enumerate(self.player_team):
            status = "FAINTED" if not mon.alive else f"{mon.current_hp}/{mon.max_hp} HP"
            rect = Rect(panel_x, panel_y + index * 44, 330, 34)
            enabled = mon.alive and index != self.p_idx
            options.append(SwitchOptionState(f"{mon.name.upper()}  |  {status}", rect, f"switch_choice:{index}", enabled))

        close_button = None
        if not self.force_switch:
            close_button = ButtonState("Close", Rect(450, 452, 110, 34), "switch_close")

        title = "Bring out which Pokemon?" if self.force_switch else "Choose a Pokemon to switch into"
        return SwitchOverlayState(title=title, options=options, close_button=close_button)

    def _build_result_overlay_state(self) -> ResultOverlayState:
        return ResultOverlayState(
            header=self.result_text,
            subtext=self.result_subtext,
            header_color=self.result_color,
            back_button=ButtonState("Back to Team Select", Rect(405, 382, 190, 40), "result_back"),
        )
