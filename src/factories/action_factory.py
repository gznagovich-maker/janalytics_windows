import copy
from typing import List
from src.domain.base_action import TurnAction
from src.domain.move_action import MoveAction
from src.domain.switch_action import SwitchAction
from src.domain.passive_action import GenericAction
from src.domain.models import MatchState

class ActionFactory:
    @staticmethod
    def create(tag: str, parts: List[str], current_state: MatchState) -> TurnAction:
        if tag == 'move':
            actor = parts[2] if len(parts) > 2 else ""
            move_name = parts[3] if len(parts) > 3 else ""
            target = parts[4] if len(parts) > 4 else ""
            return MoveAction(
                _actor=actor,
                move_name=move_name,
                target_pokemon=target,
                _board_state=copy.deepcopy(current_state)
            )
        
        elif tag in ('switch', 'detailschange'):
            slot_raw = parts[2]
            slot_id = slot_raw.split(':')[0]
            incoming_species = parts[3].split(',')[0].strip()

            outgoing = ""
            if slot_id == 'p1a':
                outgoing = current_state.p1p1 or ""
                current_state.p1p1 = incoming_species
            elif slot_id == 'p1b':
                outgoing = current_state.p1p2 or ""
                current_state.p1p2 = incoming_species
            elif slot_id == 'p2a':
                outgoing = current_state.p2p1 or ""
                current_state.p2p1 = incoming_species
            elif slot_id == 'p2b':
                outgoing = current_state.p2p2 or ""
                current_state.p2p2 = incoming_species
                
            return SwitchAction(
                _actor=outgoing,
                incoming_species=incoming_species,
                _board_state=copy.deepcopy(current_state)
            )
            
        else:
            actor = parts[2] if len(parts) > 2 else ""
            target = parts[3] if len(parts) > 3 else ""
            details = parts[4] if len(parts) > 4 else ""
            
            return GenericAction(
                _actor=actor,
                _action_type=tag,
                _target=target,
                _details=details,
                _board_state=copy.deepcopy(current_state)
            )
