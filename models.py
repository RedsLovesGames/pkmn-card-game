from dataclasses import dataclass
from typing import Dict, List, Literal, Optional

from data import CONFIG, MOVES_DB, POKEMON_DB


class Move:
    """One move used during battle.

    The JSON file stores the raw data. This class turns that raw data
    into an object that is easier to work with in Python.
    """
    def __init__(self, name: str):
        """Load one move's stats and extra effects from the move database."""
        data = MOVES_DB[name]
        self.name = name
        self.power = data["power"]
        self.category = data["category"]
        self.is_struggle = bool(data.get("is_struggle", False))
        self.fixed = bool(data.get("fixed", False))
        self.recharge = bool(data.get("recharge", False))
        self.always_hits = bool(data.get("always_hits", False))
        self.type = data["type"]

        # Optional secondary effects (status, stat changes, healing, etc.)
        self.secondary: Dict = dict(data.get("secondary", {}))
        self.accuracy = data.get("accuracy", 100)
        self.pp = data.get("pp", 15)
        self.max_pp = self.pp


class Pokemon:
    """One Pokemon used during battle.

    Each Pokemon starts with base stats from the JSON file, plus extra
    runtime values like current HP and status effects.
    """
    def __init__(self, name: str):
        """Load one Pokemon and create Move objects for its move list."""
        data = POKEMON_DB[name]
        self.name = name
        self.type = data["type"]
        self.max_hp = int(data["hp"])
        self.current_hp = int(data["hp"])
        self._base_att = int(data["attack"])
        self._base_dfn = int(data["defense"])
        self._base_spc = int(data["special"])
        self._base_speed = int(data["speed"])
        self.level = int(CONFIG["battle"]["level"])
        self.moves = [Move(move_name) for move_name in data["moves"]]
        self.needs_recharge = False
        self.status: Optional[str] = None
        self.flinched = False
        self.stat_stages = {
            "attack": 0,
            "defense": 0,
            "special": 0,
            "speed": 0,
        }

    @staticmethod
    def _apply_stage(base_value: int, stage: int) -> int:
        if stage >= 0:
            numerator = 2 + stage
            denominator = 2
        else:
            numerator = 2
            denominator = 2 - stage
        return max(1, int(base_value * numerator / denominator))

    @property
    def att(self) -> int:
        return self._apply_stage(self._base_att, self.stat_stages["attack"])

    @property
    def dfn(self) -> int:
        return self._apply_stage(self._base_dfn, self.stat_stages["defense"])

    @property
    def spc(self) -> int:
        return self._apply_stage(self._base_spc, self.stat_stages["special"])

    @property
    def speed(self) -> int:
        return self._apply_stage(self._base_speed, self.stat_stages["speed"])

    @property
    def alive(self) -> bool:
        return self.current_hp > 0

    @property
    def hp_ratio(self) -> float:
        if self.max_hp <= 0:
            return 0.0
        ratio = self.current_hp / self.max_hp
        return max(0.0, min(1.0, ratio))

    def apply_damage(self, amount: int) -> int:
        self.current_hp = max(0, self.current_hp - amount)
        return self.current_hp

    def heal(self, amount: int) -> int:
        self.current_hp = min(self.max_hp, self.current_hp + amount)
        return self.current_hp

    def change_stat_stage(self, stat_name: str, delta: int) -> bool:
        if stat_name not in self.stat_stages:
            return False
        current_stage = self.stat_stages[stat_name]
        next_stage = max(-6, min(6, current_stage + delta))
        if next_stage == current_stage:
            return False
        self.stat_stages[stat_name] = next_stage
        return True


@dataclass
class BattleAction:
    side: Literal["player", "enemy"]
    kind: Literal["attack", "recharge"]
    user: Pokemon
    target: Pokemon
    move: Optional[Move]
    can_flinch_target: bool = False

    @property
    def actor_name(self) -> str:
        if self.side == "enemy":
            return f"Enemy {self.user.name.upper()}"
        return self.user.name.upper()
