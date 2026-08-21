from dataclasses import dataclass, field
from typing import Dict, List
from src.domain.base_action import TurnAction
from src.domain.models import MatchState, ActionEffectData

@dataclass
class SwitchAction(TurnAction):
    _actor: str
    incoming_species: str
    _board_state: MatchState
    _tags: Dict[str, List[List[str]]] = field(default_factory=dict)
    _effects: Dict[str, ActionEffectData] = field(default_factory=dict)

    @property
    def actor(self) -> str:
        return self._actor

    @property
    def board_state(self) -> MatchState:
        return self._board_state

    @property
    def tags(self) -> Dict[str, List[List[str]]]:
        return self._tags

    @property
    def effects(self) -> Dict[str, ActionEffectData]:
        return self._effects

    def calcolo_reward(self) -> float:
        return 0.0

    @property
    def action_type(self) -> str:
        return "switch"

    @property
    def target(self) -> str:
        return self.incoming_species

    @property
    def details(self) -> str:
        return f"Switch to {self.incoming_species}"
