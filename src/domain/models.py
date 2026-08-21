from dataclasses import dataclass, field
from typing import List, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.base_action import TurnAction


@dataclass
class ActionEffectData:
    target: str
    damage_percent: float = 0.0
    stat_changes: Dict[str, int] = field(default_factory=dict)
    status_inflicted: Optional[str] = None
    is_crit: bool = False
    effectiveness: Optional[str] = None
    ability_activated: Optional[str] = None
    item_consumed: Optional[str] = None
    is_protected: bool = False


@dataclass
class Pokemon:
    species: str
    ability: str
    item: str
    moves: List[str]
    nature: str = ""
    tera_type: str = ""
    current_hp_pct: float = 100.0
    status: str = ""
    stat_stages: Dict[str, int] = field(
        default_factory=lambda: {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0, "eva": 0, "acc": 0}
    )

    def validate_champions_format(self, evs: Dict[str, int]) -> bool:
        if sum(evs.values()) > 66 or any(v > 32 for v in evs.values()):
            return False
        return True


@dataclass
class MatchState:
    weather: Optional[str] = None
    terrain: Optional[str] = None
    trick_room: bool = False
    tailwind_p1: bool = False
    tailwind_p2: bool = False
    p1p1: Optional[str] = None
    p1p2: Optional[str] = None
    p2p1: Optional[str] = None
    p2p2: Optional[str] = None


@dataclass
class Player:
    player_id: str
    name: str
    rating: Optional[int] = None
    team: List['Pokemon'] = field(default_factory=list)
    active_pokemon: Dict[str, 'Pokemon'] = field(default_factory=dict)


@dataclass
class Match:
    format: str = "Unknown"
    players: Dict[str, Player] = field(default_factory=dict)
    global_state: MatchState = field(default_factory=MatchState)
    turns: Dict[int, List['TurnAction']] = field(default_factory=dict)
