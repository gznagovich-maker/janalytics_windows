import re
import copy
from typing import List, Optional

from src.domain.models import Match, MatchState, Player, Pokemon, ActionEffectData
from src.domain.base_action import TurnAction
from src.domain.passive_action import GenericAction
from src.factories.action_factory import ActionFactory

def _to_id(text: str) -> str:
    return re.sub(r'[^a-z0-9]', '', str(text).lower()) if text else ""

class ShowdownParser:
    def __init__(self):
        self.match = Match()
        self.current_turn = 0
        self.last_action: Optional[TurnAction] = None

    def parse(self, log_content: str) -> Match:
        for line in log_content.strip().split('\n'):
            if not line.startswith('|'):
                continue

            parts = line.split('|')
            if len(parts) < 2:
                continue

            tag = parts[1]
            self._route_tag(tag, parts, line)

        return self.match

    def _route_tag(self, tag: str, parts: List[str], line: str):
        if tag == 'player':
            self._parse_player(parts)
        elif tag in ('showteam', 'battleteam', 'poke'):
            self._parse_team(tag, parts, line)
        elif tag == 'tier':
            self.match.format = parts[2] if len(parts) > 2 else "Unknown"
        elif tag == 'turn':
            self._parse_turn(parts)
        elif tag in ('move', 'switch', 'terastallize', 'cant', 'detailschange', 'drag', 'replace'):
            self._parse_active_action(tag, parts)
        elif tag.startswith('-') or tag == 'faint':
            self._parse_passive_event(tag, parts)
        elif tag == 'win':
            self.match.winner_name = parts[2] if len(parts) > 2 else None
        elif tag == 'tie':
            self.match.winner_name = 'tie'

    def _parse_player(self, parts: List[str]):
        if len(parts) >= 4:
            p_id, name = parts[2], parts[3]
            rating = None
            if len(parts) >= 6 and parts[5].isdigit():
                rating = int(parts[5])
                
            if name:
                if p_id not in self.match.players:
                    self.match.players[p_id] = Player(player_id=p_id, name=name, rating=rating)
                else:
                    self.match.players[p_id].name = name
                    if rating is not None:
                        self.match.players[p_id].rating = rating

    def _add_or_update_pokemon(self, p_id: str, new_pkmn: Pokemon):
        if p_id not in self.match.players:\
            self.match.players[p_id] = Player(player_id=p_id, name=f"Player {p_id}")
            
        team = self.match.players[p_id].team
        
        for pkmn in team:
            id_existing = _to_id(pkmn.species)
            id_new = _to_id(new_pkmn.species)
            
            if not id_existing or not id_new:
                continue
                
            if id_existing == id_new or id_existing in id_new or id_new in id_existing:
                # Prefer the more visually formatted or longer name
                # E.g. Landorus-Therian > landorustherian
                if len(new_pkmn.species) > len(pkmn.species) or ("-" in new_pkmn.species and "-" not in pkmn.species):
                    pkmn.species = new_pkmn.species
                
                if not pkmn.ability and new_pkmn.ability:
                    pkmn.ability = new_pkmn.ability
                if (not pkmn.item or pkmn.item == 'item') and new_pkmn.item:
                    pkmn.item = new_pkmn.item
                if not pkmn.tera_type and new_pkmn.tera_type:
                    pkmn.tera_type = new_pkmn.tera_type
                if not getattr(pkmn, 'nature', "") and getattr(new_pkmn, 'nature', ""):
                    pkmn.nature = new_pkmn.nature
                if not pkmn.moves and new_pkmn.moves:
                    pkmn.moves = new_pkmn.moves
                return
                
        team.append(new_pkmn)

    def _parse_team(self, tag: str, parts: List[str], line: str):
        p_id = parts[2] if tag in ('battleteam', 'poke') else line.split('|', 3)[2]

        if tag == 'showteam':
            parts_showteam = line.split('|', 3)
            if len(parts_showteam) >= 4:
                payload = parts_showteam[3]
                for pkmn_data in payload.split(']'):
                    if not pkmn_data: continue
                    attrs = pkmn_data.split('|')
                    species = attrs[1] if len(attrs) > 1 and attrs[1] else attrs[0]
                    pkmn = Pokemon(
                        species=species,
                        ability=attrs[3] if len(attrs) > 3 else "",
                        item=attrs[2] if len(attrs) > 2 else "",
                        moves=attrs[4].split(',') if len(attrs) > 4 and attrs[4] else [],
                        nature=attrs[5] if len(attrs) > 5 else ""
                    )
                    self._add_or_update_pokemon(p_id, pkmn)

        elif tag == 'battleteam':
            team_payload = parts[3:]
            for pkmn_data in team_payload:
                if not pkmn_data: continue
                attrs = pkmn_data.split(',')
                if len(attrs) >= 5:
                    pkmn = Pokemon(
                        species=attrs[0],
                        ability=attrs[1],
                        item=attrs[2],
                        moves=attrs[3].split('/'),
                        tera_type=attrs[4]
                    )
                    self._add_or_update_pokemon(p_id, pkmn)

        elif tag == 'poke':
            p_id = parts[2]
            species = parts[3].split(',')[0].strip()
            item = parts[4] if len(parts) > 4 else ""
            pkmn = Pokemon(
                species=species,
                ability="",
                item=item,
                moves=[]
            )
            self._add_or_update_pokemon(p_id, pkmn)

    def _parse_turn(self, parts: List[str]):
        self.current_turn = int(parts[2])
        self.match.turns[self.current_turn] = []
        self.last_action = None

    def _parse_active_action(self, tag: str, parts: List[str]):
        if self.current_turn not in self.match.turns:
            self.match.turns[self.current_turn] = []

        if tag in ('switch', 'drag', 'replace', 'detailschange'):
            slot_raw = parts[2]
            slot_id = slot_raw.split(':')[0]
            p_id = slot_id[:2]
            incoming_species = parts[3].split(',')[0].strip()
            
            if p_id in self.match.players:
                if tag in ('switch', 'drag', 'replace'):
                    for pkmn in self.match.players[p_id].team:
                        id_team = _to_id(pkmn.species)
                        id_inc = _to_id(incoming_species)
                        if id_team and id_inc and (id_team == id_inc or id_team in id_inc or id_inc in id_team):
                            self.match.players[p_id].active_pokemon[slot_id] = pkmn
                            break
                elif tag == 'detailschange':
                    if slot_id in self.match.players[p_id].active_pokemon:
                        self.match.players[p_id].active_pokemon[slot_id].species = incoming_species

        elif tag == 'terastallize':
            slot_raw = parts[2]
            slot_id = slot_raw.split(':')[0]
            p_id = slot_id[:2]
            tera_type = parts[3]
            
            if p_id in self.match.players and slot_id in self.match.players[p_id].active_pokemon:
                self.match.players[p_id].active_pokemon[slot_id].tera_type = tera_type

        self.last_action = ActionFactory.create(tag, parts, self.match.global_state)
        self.match.turns[self.current_turn].append(self.last_action)

    def _parse_passive_event(self, tag: str, parts: List[str]):
        if self.current_turn not in self.match.turns:
            self.match.turns[self.current_turn] = []

        if not self.last_action:
            self.last_action = GenericAction(
                _actor="",
                _action_type="upkeep",
                _target="",
                _details="",
                _board_state=copy.deepcopy(self.match.global_state)
            )
            self.match.turns[self.current_turn].append(self.last_action)

        clean_tag = tag.lstrip('-')

        if clean_tag not in self.last_action.tags:
            self.last_action.tags[clean_tag] = []
        self.last_action.tags[clean_tag].append(parts[2:])

        self._update_internal_state(clean_tag, parts)
        self._update_global_state(clean_tag, parts)

        if hasattr(self.last_action, '_board_state'):
            self.last_action._board_state = copy.deepcopy(self.match.global_state)

    def _update_internal_state(self, clean_tag: str, parts: List[str]):
        if clean_tag in ('damage', 'heal'):
            target_id = parts[2].split(':')[0]
            hp_raw = parts[3]
            p_id = target_id[:2]
            hp_match = re.search(r'(\d+(\.\d+)?)(/100)?', hp_raw)
            if hp_match and p_id in self.match.players:
                pct = float(hp_match.group(1))
                if target_id in self.match.players[p_id].active_pokemon:
                    old_pct = self.match.players[p_id].active_pokemon[target_id].current_hp_pct
                    self.match.players[p_id].active_pokemon[target_id].current_hp_pct = pct
                    
                    if getattr(self, 'last_action', None):
                        diff = old_pct - pct
                        if target_id not in self.last_action.effects:
                            target_species = self.match.players[p_id].active_pokemon[target_id].species
                            self.last_action.effects[target_id] = ActionEffectData(target=f"{p_id}: {target_species}")
                        self.last_action.effects[target_id].damage_percent += diff

        elif clean_tag in ('boost', 'unboost'):
            target_id = parts[2].split(':')[0]
            stat = parts[3]
            amount_str = parts[4]
            amount = int(amount_str) if clean_tag == 'boost' else -int(amount_str)
            p_id = target_id[:2]
            if p_id in self.match.players and target_id in self.match.players[p_id].active_pokemon:
                self.match.players[p_id].active_pokemon[target_id].stat_stages[stat] += amount
                
                if getattr(self, 'last_action', None):
                    if target_id not in self.last_action.effects:
                        target_species = self.match.players[p_id].active_pokemon[target_id].species
                        self.last_action.effects[target_id] = ActionEffectData(target=f"{p_id}: {target_species}")
                    self.last_action.effects[target_id].stat_changes[stat] = amount

        elif clean_tag == 'faint':
            target_id = parts[2].split(':')[0]
            p_id = target_id[:2]
            if p_id in self.match.players and target_id in self.match.players[p_id].active_pokemon:
                self.match.players[p_id].active_pokemon[target_id].status = "fainted"

            if target_id == 'p1a':
                self.match.global_state.p1p1 = None
            elif target_id == 'p1b':
                self.match.global_state.p1p2 = None
            elif target_id == 'p2a':
                self.match.global_state.p2p1 = None
            elif target_id == 'p2b':
                self.match.global_state.p2p2 = None

        elif clean_tag in ('status', 'curestatus'):
            target_id = parts[2].split(':')[0]
            status_name = parts[3] if len(parts) > 3 else ""
            p_id = target_id[:2]
            if p_id in self.match.players and target_id in self.match.players[p_id].active_pokemon:
                self.match.players[p_id].active_pokemon[target_id].status = status_name if clean_tag == 'status' else ""
                
                if clean_tag == 'status' and getattr(self, 'last_action', None):
                    if target_id not in self.last_action.effects:
                        target_species = self.match.players[p_id].active_pokemon[target_id].species
                        self.last_action.effects[target_id] = ActionEffectData(target=f"{p_id}: {target_species}")
                    self.last_action.effects[target_id].status_inflicted = status_name

        elif clean_tag == 'crit':
            target_id = parts[2].split(':')[0]
            if getattr(self, 'last_action', None):
                if target_id not in self.last_action.effects:
                    p_id = target_id[:2]
                    target_species = self.match.players[p_id].active_pokemon[target_id].species
                    self.last_action.effects[target_id] = ActionEffectData(target=f"{p_id}: {target_species}")
                self.last_action.effects[target_id].is_crit = True

        elif clean_tag in ('supereffective', 'resisted', 'immune'):
            target_id = parts[2].split(':')[0]
            if getattr(self, 'last_action', None):
                if target_id not in self.last_action.effects:
                    p_id = target_id[:2]
                    target_species = self.match.players[p_id].active_pokemon[target_id].species
                    self.last_action.effects[target_id] = ActionEffectData(target=f"{p_id}: {target_species}")
                self.last_action.effects[target_id].effectiveness = clean_tag

        elif clean_tag == 'ability':
            target_id = parts[2].split(':')[0]
            ability_name = parts[3] if len(parts) > 3 else ""
            p_id = target_id[:2]
            
            if getattr(self, 'last_action', None):
                actor_id = self.last_action.actor.split(':')[0] if self.last_action.actor and ':' in self.last_action.actor else None
                if actor_id == target_id:
                    self.last_action.ability_activated = ability_name
                else:
                    if target_id not in self.last_action.effects:
                        target_species = self.match.players[p_id].active_pokemon[target_id].species if p_id in self.match.players and target_id in self.match.players[p_id].active_pokemon else "Unknown"
                        self.last_action.effects[target_id] = ActionEffectData(target=f"{p_id}: {target_species}")
                    self.last_action.effects[target_id].ability_activated = ability_name

            if p_id in self.match.players and target_id in self.match.players[p_id].active_pokemon:
                species = self.match.players[p_id].active_pokemon[target_id].species
                self.match.players[p_id].active_pokemon[target_id].ability = ability_name
                for pkmn in self.match.players[p_id].team:
                    if pkmn.species == species:
                        if not pkmn.ability:
                            pkmn.ability = ability_name
                        break

        elif clean_tag in ('item', 'enditem'):
            target_id = parts[2].split(':')[0]
            item_name = parts[3] if len(parts) > 3 else ""
            p_id = target_id[:2]
            
            if clean_tag == 'enditem' and getattr(self, 'last_action', None):
                actor_id = self.last_action.actor.split(':')[0] if self.last_action.actor and ':' in self.last_action.actor else None
                if actor_id == target_id:
                    self.last_action.item_consumed = item_name
                else:
                    if target_id not in self.last_action.effects:
                        target_species = self.match.players[p_id].active_pokemon[target_id].species if p_id in self.match.players and target_id in self.match.players[p_id].active_pokemon else "Unknown"
                        self.last_action.effects[target_id] = ActionEffectData(target=f"{p_id}: {target_species}")
                    self.last_action.effects[target_id].item_consumed = item_name

            if p_id in self.match.players and target_id in self.match.players[p_id].active_pokemon:
                species = self.match.players[p_id].active_pokemon[target_id].species
                self.match.players[p_id].active_pokemon[target_id].item = item_name
                for pkmn in self.match.players[p_id].team:
                    if pkmn.species == species:
                        if not pkmn.item or pkmn.item == 'item':
                            pkmn.item = item_name
                        break

        elif clean_tag == 'activate':
            if len(parts) > 3 and 'Protect' in parts[3]:
                target_id = parts[2].split(':')[0]
                p_id = target_id[:2]
                if getattr(self, 'last_action', None):
                    if target_id not in self.last_action.effects:
                        target_species = self.match.players[p_id].active_pokemon[target_id].species if p_id in self.match.players and target_id in self.match.players[p_id].active_pokemon else "Unknown"
                        self.last_action.effects[target_id] = ActionEffectData(target=f"{p_id}: {target_species}")
                    self.last_action.effects[target_id].is_protected = True

    def _update_global_state(self, clean_tag: str, parts: List[str]):
        if clean_tag in ('weather', 'fieldstart', 'fieldend'):
            condition = parts[2]
            if clean_tag == 'weather':
                self.match.global_state.weather = condition if condition != 'none' else None
            else:
                is_active = (clean_tag == 'fieldstart')
                if 'Trick Room' in condition:
                    self.match.global_state.trick_room = is_active
                else:
                    self.match.global_state.terrain = condition if is_active else None

        elif clean_tag in ('sidestart', 'sideend'):
            side_info = parts[2]
            condition = parts[3] if len(parts) > 3 else ""
            p_id = side_info.split(':')[0]

            if 'Tailwind' in condition:
                is_active = (clean_tag == 'sidestart')
                if p_id == 'p1':
                    self.match.global_state.tailwind_p1 = is_active
                elif p_id == 'p2':
                    self.match.global_state.tailwind_p2 = is_active


def parse_showdown_log(log_content: str) -> Match:
    parser = ShowdownParser()
    return parser.parse(log_content)
