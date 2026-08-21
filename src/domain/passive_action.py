from dataclasses import dataclass, field
from typing import Dict, List
from src.domain.base_action import TurnAction
from src.domain.models import MatchState, ActionEffectData

@dataclass
class AbilityTrigger(TurnAction):
    _actor: str
    ability_name: str
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
        return "ability"

    @property
    def target(self) -> str:
        return ""

    @property
    def details(self) -> str:
        return self.ability_name


@dataclass
class StatusAction(TurnAction):
    _actor: str
    status_name: str
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
        return "status"

    @property
    def target(self) -> str:
        return self.actor

    @property
    def details(self) -> str:
        return self.status_name


@dataclass
class GenericAction(TurnAction):
    _actor: str
    _action_type: str
    _target: str
    _details: str
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
        return self._action_type

    @property
    def target(self) -> str:
        return self._target

    @property
    def details(self) -> str:
        return self._details
