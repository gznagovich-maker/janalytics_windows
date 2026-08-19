import re
import copy
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class Pokemon:
    species: str
    ability: str
    item: str
    moves: List[str]
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
class TurnAction:
    action_type: str
    actor: str
    target: str
    details: str
    board_state: MatchState
    tags: Dict[str, List[List[str]]] = field(default_factory=dict)


@dataclass
class Player:
    player_id: str
    name: str
    team: List[Pokemon] = field(default_factory=list)
    active_pokemon: Dict[str, Pokemon] = field(default_factory=dict)


@dataclass
class Match:
    players: Dict[str, Player] = field(default_factory=dict)
    global_state: MatchState = field(default_factory=MatchState)
    turns: Dict[int, List[TurnAction]] = field(default_factory=dict)


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
        elif tag in ('showteam', 'battleteam'):
            self._parse_team(tag, parts, line)
        elif tag == 'turn':
            self._parse_turn(parts)
        elif tag in ('move', 'switch', 'terastallize', 'cant', 'detailschange'):
            self._parse_active_action(tag, parts)
        elif tag.startswith('-') or tag == 'faint':
            self._parse_passive_event(tag, parts)

    def _parse_player(self, parts: List[str]):
        if len(parts) >= 4:
            p_id, name = parts[2], parts[3]
            if name:
                if p_id not in self.match.players:
                    self.match.players[p_id] = Player(player_id=p_id, name=name)
                else:
                    self.match.players[p_id].name = name

    def _parse_team(self, tag: str, parts: List[str], line: str):
        p_id = parts[2] if tag == 'battleteam' else line.split('|', 3)[2]

        if p_id not in self.match.players:
            self.match.players[p_id] = Player(player_id=p_id, name=f"Player {p_id}")

        if tag == 'showteam':
            parts_showteam = line.split('|', 3)
            if len(parts_showteam) >= 4:
                payload = parts_showteam[3]
                for pkmn_data in payload.split(']'):
                    if not pkmn_data: continue
                    attrs = pkmn_data.split('|')
                    pkmn = Pokemon(
                        species=attrs[0],
                        ability=attrs[3] if len(attrs) > 3 else "",
                        item=attrs[2] if len(attrs) > 2 else "",
                        moves=attrs[4].split(',') if len(attrs) > 4 and attrs[4] else []
                    )
                    self.match.players[p_id].team.append(pkmn)

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
                    self.match.players[p_id].team.append(pkmn)

    def _parse_turn(self, parts: List[str]):
        self.current_turn = int(parts[2])
        self.match.turns[self.current_turn] = []
        self.last_action = None

    def _parse_active_action(self, tag: str, parts: List[str]):
        if self.current_turn not in self.match.turns:
            self.match.turns[self.current_turn] = []

        actor = parts[2] if len(parts) > 2 else ""
        target = parts[3] if len(parts) > 3 else ""
        details = parts[4] if len(parts) > 4 else ""

        if tag in ('switch', 'detailschange'):
            slot_raw = parts[2]
            slot_id = slot_raw.split(':')[0]
            p_id = slot_id[:2]
            incoming_species = parts[3].split(',')[0].strip()

            outgoing = ""
            if slot_id == 'p1a':
                outgoing = self.match.global_state.p1p1 or ""
                self.match.global_state.p1p1 = incoming_species
            elif slot_id == 'p1b':
                outgoing = self.match.global_state.p1p2 or ""
                self.match.global_state.p1p2 = incoming_species
            elif slot_id == 'p2a':
                outgoing = self.match.global_state.p2p1 or ""
                self.match.global_state.p2p1 = incoming_species
            elif slot_id == 'p2b':
                outgoing = self.match.global_state.p2p2 or ""
                self.match.global_state.p2p2 = incoming_species

            actor = outgoing
            target = incoming_species

            if p_id in self.match.players:
                if tag == 'switch':
                    for pkmn in self.match.players[p_id].team:
                        if pkmn.species == incoming_species:
                            self.match.players[p_id].active_pokemon[slot_id] = pkmn
                            break
                elif tag == 'detailschange':
                    if slot_id in self.match.players[p_id].active_pokemon:
                        self.match.players[p_id].active_pokemon[slot_id].species = incoming_species

        self.last_action = TurnAction(
            action_type=tag,
            actor=actor,
            target=target,
            details=details,
            board_state=copy.deepcopy(self.match.global_state)
        )
        self.match.turns[self.current_turn].append(self.last_action)

    def _parse_passive_event(self, tag: str, parts: List[str]):
        if self.current_turn not in self.match.turns:
            self.match.turns[self.current_turn] = []

        if not self.last_action:
            self.last_action = TurnAction(
                action_type="upkeep",
                actor="",
                target="",
                details="",
                board_state=copy.deepcopy(self.match.global_state)
            )
            self.match.turns[self.current_turn].append(self.last_action)

        clean_tag = tag.lstrip('-')

        if clean_tag not in self.last_action.tags:
            self.last_action.tags[clean_tag] = []
        self.last_action.tags[clean_tag].append(parts[2:])

        self._update_internal_state(clean_tag, parts)
        self._update_global_state(clean_tag, parts)

        self.last_action.board_state = copy.deepcopy(self.match.global_state)

    def _update_internal_state(self, clean_tag: str, parts: List[str]):
        if clean_tag in ('damage', 'heal'):
            target_id = parts[2].split(':')[0]
            hp_raw = parts[3]
            p_id = target_id[:2]
            hp_match = re.search(r'(\d+(\.\d+)?)(/100)?', hp_raw)
            if hp_match and p_id in self.match.players:
                pct = float(hp_match.group(1))
                if target_id in self.match.players[p_id].active_pokemon:
                    self.match.players[p_id].active_pokemon[target_id].current_hp_pct = pct

        elif clean_tag in ('boost', 'unboost'):
            target_id = parts[2].split(':')[0]
            stat = parts[3]
            amount_str = parts[4]
            amount = int(amount_str) if clean_tag == 'boost' else -int(amount_str)
            p_id = target_id[:2]
            if p_id in self.match.players and target_id in self.match.players[p_id].active_pokemon:
                self.match.players[p_id].active_pokemon[target_id].stat_stages[stat] += amount

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