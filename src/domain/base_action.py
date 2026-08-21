from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from src.domain.models import MatchState, ActionEffectData

class TurnAction(ABC):
    @property
    @abstractmethod
    def actor(self) -> str:
        pass

    @property
    @abstractmethod
    def board_state(self) -> MatchState:
        pass

    @property
    @abstractmethod
    def tags(self) -> Dict[str, List[List[str]]]:
        pass

    @property
    @abstractmethod
    def effects(self) -> Dict[str, ActionEffectData]:
        pass

    @property
    def ability_activated(self) -> Optional[str]:
        return getattr(self, '_ability_activated', None)

    @ability_activated.setter
    def ability_activated(self, value: Optional[str]):
        self._ability_activated = value

    @property
    def item_consumed(self) -> Optional[str]:
        return getattr(self, '_item_consumed', None)

    @item_consumed.setter
    def item_consumed(self, value: Optional[str]):
        self._item_consumed = value

    @abstractmethod
    def calcolo_reward(self) -> float:
        """Calcola la reward di questa azione."""
        pass

    @property
    @abstractmethod
    def action_type(self) -> str:
        """Restituisce il tipo dell'azione (es. 'move', 'switch')."""
        pass

    @property
    @abstractmethod
    def target(self) -> str:
        """Restituisce il target principale dell'azione per compatibilità con l'interfaccia esistente."""
        pass

    @property
    @abstractmethod
    def details(self) -> str:
        """Restituisce i dettagli dell'azione per compatibilità con l'interfaccia esistente."""
        pass
