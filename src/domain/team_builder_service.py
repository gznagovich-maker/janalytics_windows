from typing import List, Dict, Any, Optional
import re
from database.connection import SessionLocal
from database.models import PokemonSpecies, Move
from src.domain.type_chart import TYPE_DATA, get_multiplier
from src.analytics.team_clustering import get_team_archetypes_and_groupings

class TeamMember:
    def __init__(self):
        self.species: str = ""
        self.item: str = ""
        self.ability: str = ""
        self.tera_type: str = ""
        self.nature: str = ""
        self.evs: Dict[str, int] = {}
        self.ivs: Dict[str, int] = {}
        self.moves: List[str] = []
        self.is_champions_mode: bool = True
        
        # Data loaded from DB
        self.types: List[str] = []
        self.moves_data: List[Dict[str, Any]] = []

def parse_pokepaste(paste_text: str, corrections: Optional[Dict[str, str]] = None) -> List[TeamMember]:
    if corrections is None:
        corrections = {}
        
    members = []
    current_member = None
    
    lines = paste_text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            if current_member and current_member.species:
                if sum(current_member.evs.values()) > 66:
                    current_member.is_champions_mode = False
                members.append(current_member)
                current_member = None
            continue
            
        if current_member is None:
            current_member = TeamMember()
            
            # Species and Item
            if '@' in line:
                species_part, item_part = line.split('@', 1)
                raw_species = species_part.strip()
                current_member.item = item_part.strip()
            else:
                raw_species = line
                
            # Handle gender modifier at the end: (M), (F), or (N)
            gender = ""
            if raw_species.endswith('(M)'):
                gender = "M"
                raw_species = raw_species[:-3].strip()
            elif raw_species.endswith('(F)'):
                gender = "F"
                raw_species = raw_species[:-3].strip()
            elif raw_species.endswith('(N)'):
                gender = "N"
                raw_species = raw_species[:-3].strip()
                
            # Handle nickname: Nickname (Species)
            if raw_species.endswith(')'):
                idx = raw_species.rfind('(')
                if idx != -1:
                    raw_species = raw_species[idx+1:-1].strip()
                    
            # Apply specific female form suffixes if necessary, based on generic Showdown behavior
            if gender == "F" and raw_species.lower() in ["indeedee", "meowstic", "basculegion", "oinkologne"]:
                raw_species = raw_species + "-F"
                
            current_member.species = raw_species
            continue
            
        if line.startswith('Ability:'):
            current_member.ability = line.split(':', 1)[1].strip()
        elif line.startswith('Tera Type:'):
            current_member.tera_type = line.split(':', 1)[1].strip()
        elif line.startswith('EVs:'):
            ev_str = line.replace('EVs:', '').strip()
            parts = ev_str.split('/')
            for p in parts:
                p = p.strip()
                if ' ' in p:
                    val, stat = p.split(' ', 1)
                    current_member.evs[stat.strip()] = int(val.strip())
        elif line.startswith('IVs:'):
            iv_str = line.replace('IVs:', '').strip()
            parts = iv_str.split('/')
            for p in parts:
                p = p.strip()
                if ' ' in p:
                    val, stat = p.split(' ', 1)
                    current_member.ivs[stat.strip()] = int(val.strip())
        elif line.endswith('Nature'):
            current_member.nature = line.replace('Nature', '').strip()
        elif line.startswith('-'):
            move = line[1:].strip()
            current_member.moves.append(move)
            
    if current_member and current_member.species:
        if sum(current_member.evs.values()) > 66:
            current_member.is_champions_mode = False
        members.append(current_member)
        
    from database.models_v2 import PokemonSpeciesV2, MoveV2, AbilityV2, ItemV2
    from src.domain.exceptions import EntityNotFoundError
    from database.hash_utils import to_id
    
    # Enrich with DB data & Strict Validation
    with SessionLocal() as session:
        for member in members:
            # --- SPECIES ---
            raw_species = corrections.get(member.species, member.species)
            species_clean = to_id(raw_species)
            
            species_db = session.query(PokemonSpeciesV2).filter(PokemonSpeciesV2.id == species_clean).first()
            if not species_db:
                raise EntityNotFoundError('species', member.species, member.species)
            
            member.species = species_db.name
            types = []
            if species_db.type1: types.append(species_db.type1)
            if species_db.type2: types.append(species_db.type2)
            member.types = types
            
            # --- ABILITY ---
            if member.ability:
                raw_ability = corrections.get(member.ability, member.ability)
                ability_clean = to_id(raw_ability)
                ability_db = session.query(AbilityV2).filter(AbilityV2.id == ability_clean).first()
                if not ability_db:
                    raise EntityNotFoundError('ability', member.ability, member.species)
                member.ability = ability_db.name
                
            # --- ITEM ---
            if member.item:
                raw_item = corrections.get(member.item, member.item)
                item_clean = to_id(raw_item)
                item_db = session.query(ItemV2).filter(ItemV2.id == item_clean).first()
                if not item_db:
                    raise EntityNotFoundError('item', member.item, member.species)
                member.item = item_db.name
            
            # --- MOVES ---
            new_moves = []
            for move_name in member.moves:
                raw_move = corrections.get(move_name, move_name)
                move_clean = to_id(raw_move)
                
                # Exception for Hidden Power
                if move_clean.startswith('hiddenpower'):
                    move_clean = 'hiddenpower'
                    
                move_db = session.query(MoveV2).filter(MoveV2.id == move_clean).first()
                if not move_db:
                    raise EntityNotFoundError('move', move_name, member.species)
                    
                member.moves_data.append({
                    "name": move_db.name,
                    "type": move_db.type,
                    "category": move_db.category
                })
                new_moves.append(move_db.name)
            member.moves = new_moves
                    
    return members

def get_all_species_names() -> List[str]:
    from database.models_v2 import PokemonSpeciesV2
    with SessionLocal() as session:
        species = session.query(PokemonSpeciesV2.name).order_by(PokemonSpeciesV2.name).all()
        return [s[0] for s in species]

def get_species_types(name: str) -> List[str]:
    from database.models_v2 import PokemonSpeciesV2
    with SessionLocal() as session:
        species = session.query(PokemonSpeciesV2).filter(PokemonSpeciesV2.name == name).first()
        if not species: return []
        t = []
        if species.type1: t.append(species.type1)
        if species.type2: t.append(species.type2)
        return t

def get_all_items() -> List[str]:
    from database.models_v2 import ItemV2
    with SessionLocal() as session:
        items = session.query(ItemV2.name).order_by(ItemV2.name).all()
        return [i[0] for i in items]

def get_all_abilities() -> List[str]:
    from database.models_v2 import AbilityV2
    with SessionLocal() as session:
        abs_list = session.query(AbilityV2.name).order_by(AbilityV2.name).all()
        return [a[0] for a in abs_list]

def get_all_items_details() -> List[Dict[str, str]]:
    from database.models_v2 import ItemV2
    from database.connection import SessionLocal
    with SessionLocal() as session:
        items = session.query(ItemV2).order_by(ItemV2.name).all()
        return [{"name": i.name, "desc": i.short_desc} for i in items]

def get_all_moves() -> List[str]:
    from database.models_v2 import MoveV2
    with SessionLocal() as session:
        mvs = session.query(MoveV2.name).order_by(MoveV2.name).all()
        return [m[0] for m in mvs]

def calculate_vgc_stat(base: int, iv: int, ev: int, nature_mult: float, is_hp: bool) -> int:
    """Calcola la statistica reale al livello 50 per il VGC."""
    import math
    if is_hp:
        return math.floor(((2 * base + iv + math.floor(ev / 4)) * 50) / 100) + 10 + 50
    else:
        stat = math.floor(((2 * base + iv + math.floor(ev / 4)) * 50) / 100) + 5
        return math.floor(stat * nature_mult)

def get_pokeapi_legal_moves_and_abilities(species_name: str) -> Dict[str, List[str]]:
    # Deprecated
    return {"abilities": [], "moves": []}

def get_legal_moves_details(species_name: str) -> List[Dict[str, Any]]:
    import json
    from database.models_v2 import PokemonSpeciesV2, MoveV2
    from database.connection import SessionLocal
    
    details_list = []
    with SessionLocal() as session:
        pkmn = session.query(PokemonSpeciesV2).filter(PokemonSpeciesV2.name == species_name).first()
        if not pkmn: return []
        
        if not pkmn.learnset_json:
            return []
            
        try:
            move_ids = json.loads(pkmn.learnset_json)
        except:
            move_ids = []
            
        if move_ids:
            # Query all these moves
            moves = session.query(MoveV2).filter(MoveV2.id.in_(move_ids)).all()
            for mv in moves:
                details_list.append({
                    "name": mv.name,
                    "type": mv.type,
                    "category": mv.category,
                    "basePower": mv.base_power,
                    "accuracy": mv.accuracy,
                    "desc": mv.short_desc,
                    "priority": mv.priority,
                    "target": mv.target,
                    "flags": {},
                    "boosts": None,
                    "secondary": None
                })
                
    details_list.sort(key=lambda x: x["name"])
    return details_list

def get_legal_abilities_details(species_name: str) -> List[Dict[str, str]]:
    import json
    from database.models_v2 import PokemonSpeciesV2, AbilityV2
    from database.connection import SessionLocal
    
    with SessionLocal() as session:
        pkmn = session.query(PokemonSpeciesV2).filter(PokemonSpeciesV2.name == species_name).first()
        if not pkmn or not pkmn.abilities_json:
            return []
            
        try:
            abilities_names = json.loads(pkmn.abilities_json)
        except:
            abilities_names = []
            
        abs_db = session.query(AbilityV2).filter(AbilityV2.name.in_(abilities_names)).all()
        abs_map = {a.name: a.short_desc for a in abs_db}
        
    return [{"name": name, "desc": abs_map.get(name, "Nessuna descrizione disponibile.")} for name in abilities_names]

def get_historical_abilities(species_name: str) -> List[str]:
    from database.models import PokemonBuild, Ability
    with SessionLocal() as session:
        species_db = session.query(PokemonSpecies).filter(PokemonSpecies.name == species_name).first()
        if not species_db:
            return []
        builds = session.query(PokemonBuild.ability_id).filter(PokemonBuild.species_id == species_db.id).distinct().all()
        ab_ids = [b[0] for b in builds if b[0]]
        if not ab_ids:
            return []
        abs_names = session.query(Ability.name).filter(Ability.id.in_(ab_ids)).all()
        return [a[0] for a in abs_names]

def get_historical_moves(species_name: str) -> List[str]:
    from database.models import PokemonBuild
    with SessionLocal() as session:
        species_db = session.query(PokemonSpecies).filter(PokemonSpecies.name == species_name).first()
        if not species_db:
            return []
        builds = session.query(PokemonBuild.moves).filter(PokemonBuild.species_id == species_db.id).distinct().all()
        move_ids = set()
        for b in builds:
            if b[0]:
                for mid in b[0].split(','):
                    move_ids.add(mid.strip())
        if not move_ids:
            return []
        mvs_names = session.query(Move.name).filter(Move.id.in_(move_ids)).all()
        return [m[0] for m in mvs_names]

def calculate_defensive_matchup(members: List[TeamMember]) -> Dict[str, float]:
    """Returns a dict mapping Type -> Net Score (Weaknesses - Resistances) across the team."""
    matchup_scores = {t: 0.0 for t in TYPE_DATA.keys()}
    
    for atk_type in TYPE_DATA.keys():
        score = 0
        for member in members:
            if not member.types: continue
            mult = get_multiplier(member.types, atk_type)
            if mult > 1:
                score -= 1 # Weakness
            elif mult < 1 and mult > 0:
                score += 1 # Resistance
            elif mult == 0:
                score += 2 # Immunity counts as strong resistance
        matchup_scores[atk_type] = score
        
    return matchup_scores

def calculate_offensive_matchup(members: List[TeamMember]) -> Dict[str, Dict[str, int]]:
    """Returns a dict containing 'Physical' and 'Special' dictionaries. 
    Each maps Defending Type -> number of super effective hits from the team."""
    
    results = {
        "Physical": {t: 0 for t in TYPE_DATA.keys()},
        "Special": {t: 0 for t in TYPE_DATA.keys()}
    }
    
    for member in members:
        for move in member.moves_data:
            category = move.get("category")
            if category not in ["Physical", "Special"]:
                continue
                
            move_type = move.get("type")
            
            for def_type in TYPE_DATA.keys():
                mult = get_multiplier([def_type], move_type)
                if mult > 1:
                    results[category][def_type] += 1
                    
    return results

def get_archetype_matchup(members: List[TeamMember]) -> Dict[str, Any]:
    """Finds the team archetype in DB and returns its win rates against other archetypes."""
    if not members:
        return {}
        
    species_names = [m.species for m in members if m.species]
    if len(species_names) < 3:
        return {}
        
    try:
        groupings = get_team_archetypes_and_groupings(max_distance=2, format_filter="Tutti", trainer_filter="")
    except Exception:
        return {}
        
    best_match = None
    best_overlap = 0
    
    for group in groupings:
        core_species = set(group["core_species"])
        my_species = set(species_names)
        overlap = len(core_species.intersection(my_species))
        
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = group
            
    if best_match and best_overlap >= 3:
        return {
            "core_species": best_match["core_species"],
            "total_matches": best_match["total_matches"],
            "win_rate": best_match["win_rate"],
            "archetypes": best_match.get("variants", [{}])[0].get("archetypes", [])
        }
        
    return {}
