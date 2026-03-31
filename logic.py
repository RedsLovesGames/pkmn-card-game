import random
from typing import List, Optional, Tuple

from data import CONFIG, POKEMON_NAMES, TYPE_DATA
from models import BattleAction, Move, Pokemon


def clamp(value: float, low: float, high: float) -> float:
    """Keep a number inside a minimum and maximum range."""
    return max(low, min(high, value))


def recursive_valid_switch(team: List[Pokemon], current_index: int, candidate_index: int = 0) -> Optional[int]:
    """Find the first Pokemon the player can switch into."""
    for index in range(candidate_index, len(team)):
        mon = team[index]
        if index != current_index and mon.alive:
            return index
    return None


def calculate_damage(attacker: Pokemon, defender: Pokemon, move: Move) -> Tuple[int, bool, float]:
    """Calculate the result of one attack.

    Returns three values:
    1. The amount of damage dealt
    2. Whether the hit was a critical hit
    3. The type effectiveness multiplier
    """
    if getattr(move, "is_struggle", False) or move.fixed:
        return move.power, False, 1.0

    attack = attacker.att if move.category == "Physical" else attacker.spc
    defense = defender.dfn if move.category == "Physical" else defender.spc
    if move.name == "Explosion":
        defense = max(1, defense // 2)

    move_type = move.type.lower()
    attacker_type = attacker.type.lower()
    defender_type = defender.type.lower()

    critical = random.random() < CONFIG["battle"]["crit_chance"]
    stab = CONFIG["battle"]["stab_multiplier"] if move_type == attacker_type else 1.0
    type_mult = TYPE_DATA.get(move_type, {}).get(defender_type, 1.0)

    rand_mod = random.uniform(CONFIG["battle"]["random_min"], CONFIG["battle"]["random_max"])

    damage = max(1, int(round(
        (
            (
                (2 * attacker.level // 5 + 2) * move.power * attack // defense
            ) // 50
        ) + 2
    ) * stab * type_mult * (CONFIG["battle"]["crit_multiplier"] if critical else 1.0) * rand_mod))

    return damage, critical, type_mult


def _build_random_enemy_team(selected_names: List[str], team_size: int) -> List[Pokemon]:
    """Create a random enemy team, avoiding the player picks when possible."""
    pool = [name for name in POKEMON_NAMES if name not in selected_names]
    if len(pool) < team_size:
        pool = list(POKEMON_NAMES)
    chosen = random.sample(pool, team_size)
    return [Pokemon(name) for name in chosen]


def _apply_secondary_effect(
    move: Move,
    user: Pokemon,
    target: Pokemon,
    damage: int,
    can_flinch_target: bool = False,
) -> Optional[str]:
    """Apply bonus effects from a move, such as burn or healing."""
    secondary = move.secondary
    if not secondary or random.random() > secondary.get("chance", 1.0):
        return None

    effect = secondary.get("effect")
    if not effect:
        return None
    
    # Status application effects
    status_result = _apply_status_effects(effect, target, damage)
    if status_result:
        return status_result
    
    # Healing and other effects
    return _apply_other_effects(effect, user, target, damage, secondary, can_flinch_target=can_flinch_target)


def _apply_status_effects(effect: str, target: Pokemon, damage: int) -> Optional[str]:
    """Apply a status condition such as burn, paralysis, freeze, or confusion."""
    if effect == "burn":
        target.status = "burn"
        return f"{target.name.upper()} was burned!"
    elif effect == "paralyze":
        target.status = "paralyze"
        return f"{target.name.upper()} was paralyzed!"
    elif effect == "freeze":
        target.status = "freeze"
        return f"{target.name.upper()} was frozen solid!"
    elif effect == "confuse":
        target.status = "confuse"
        return f"{target.name.upper()} became confused!"
    return None


def _apply_other_effects(
    effect: str,
    user: Pokemon,
    target: Pokemon,
    damage: int,
    secondary: dict,
    can_flinch_target: bool = False,
) -> Optional[str]:
    """Apply move effects that are not status conditions."""
    if effect == "drain":
        heal_amount = int(round(damage * secondary.get("drain", 0.5)))
        user.heal(heal_amount)
        return f"{user.name.upper()} regained {heal_amount} HP!"
    if effect == "lower_def":
        if target.change_stat_stage("defense", -int(secondary.get("stages", 1))):
            return f"{target.name.upper()}'s Defense fell!"
        return None
    if effect == "lower_special":
        if target.change_stat_stage("special", -int(secondary.get("stages", 1))):
            return f"{target.name.upper()}'s Special fell!"
        return None
    if effect == "flinch":
        if can_flinch_target and target.alive:
            target.flinched = True
        return None
    if effect == "status":
        chosen = random.choice(["burn", "paralyze", "freeze"])
        target.status = chosen
        return f"{target.name.upper()} is now {chosen}!"

    # Generic fallback message from description
    return secondary.get("text") or secondary.get("description")


def _check_status_effects(user: Pokemon, side: str) -> Optional[str]:
    """Check whether a status effect changes this turn's action.

    Returns:
    - `"skip"` if the Pokemon loses its turn
    - `"hurt_self"` if it damages itself instead
    - `None` if it can keep going normally
    """
    if not user.status:
        actor_name = f"Enemy {user.name.upper()}" if side == "enemy" else user.name.upper()
        if user.flinched:
            user.flinched = False
            return f"{actor_name} flinched!\nCannot move!"
        return None

    actor_name = f"Enemy {user.name.upper()}" if side == "enemy" else user.name.upper()
    if user.flinched:
        user.flinched = False
        return f"{actor_name} flinched!\nCannot move!"

    # Each status handler decides whether the move can proceed this turn.
    if user.status == "burn":
        return _apply_burn_damage(user, actor_name)
    elif user.status == "paralyze":
        return _apply_paralyze_effect(actor_name)
    elif user.status == "confuse":
        return _apply_confusion_effect(user, actor_name)
    elif user.status == "freeze":
        return _apply_freeze_effect(user, actor_name)

    return None


def _apply_burn_damage(user: Pokemon, actor_name: str) -> Optional[str]:
    """Deal burn damage at the start of the turn."""
    burn_damage = max(1, int(round(user.max_hp / 8)))
    user.apply_damage(burn_damage)
    return f"{actor_name} is hurt by the burn!\n-{burn_damage} HP"


def _apply_paralyze_effect(actor_name: str) -> Optional[str]:
    """Sometimes stop the Pokemon from moving because of paralysis."""
    if random.random() < 0.25:  # 25% chance to be fully paralyzed
        return f"{actor_name} is paralyzed!\nCannot move!"
    return None


def _apply_confusion_effect(user: Pokemon, actor_name: str) -> Optional[str]:
    """Sometimes make the Pokemon hurt itself because of confusion."""
    if random.random() < 0.33:  # 33% chance confusion activates
        confuse_damage = max(1, int(round(user.current_hp * 0.125)))  # 12.5% self-damage
        user.apply_damage(confuse_damage)
        return f"{actor_name} is confused!\nHurt itself in confusion!\n-{confuse_damage} HP"
    return None


def _apply_freeze_effect(user: Pokemon, actor_name: str) -> Optional[str]:
    """Check whether a frozen Pokemon thaws out or loses its turn."""
    if random.random() < 0.2:  # 20% chance to thaw
        user.status = None
        return f"{actor_name} thawed out!"
    return f"{actor_name} is frozen solid!\nCannot move!"


def _resolve_turn_order(player_action: BattleAction, enemy_action: BattleAction) -> Tuple[BattleAction, BattleAction]:
    """Decide which side acts first.

    Faster Pokemon go first. If speeds match, pick randomly.
    """
    player_speed = player_action.user.speed
    enemy_speed = enemy_action.user.speed
    if player_speed > enemy_speed:
        return player_action, enemy_action
    if enemy_speed > player_speed:
        return enemy_action, player_action
    return (player_action, enemy_action) if random.random() < 0.5 else (enemy_action, player_action)


def _build_action(side: str, user: Pokemon, target: Pokemon, move_index: Optional[int] = None) -> BattleAction:
    """Create one typed battle action for the given user."""
    if user.needs_recharge:
        return BattleAction(side=side, kind="recharge", user=user, target=target, move=None)

    move = user.moves[move_index] if move_index is not None else random.choice(user.moves)
    return BattleAction(side=side, kind="attack", user=user, target=target, move=move)
