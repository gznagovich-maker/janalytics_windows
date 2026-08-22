from typing import List, Dict

TYPE_DATA = {
    "Normal": {"weaknesses": ["Fighting"], "resistances": [], "immunities": ["Ghost"]},
    "Fire": {"weaknesses": ["Water", "Ground", "Rock"], "resistances": ["Fire", "Grass", "Ice", "Bug", "Steel", "Fairy"], "immunities": []},
    "Water": {"weaknesses": ["Electric", "Grass"], "resistances": ["Fire", "Water", "Ice", "Steel"], "immunities": []},
    "Grass": {"weaknesses": ["Fire", "Ice", "Poison", "Flying", "Bug"], "resistances": ["Water", "Grass", "Electric", "Ground"], "immunities": []},
    "Electric": {"weaknesses": ["Ground"], "resistances": ["Electric", "Flying", "Steel"], "immunities": []},
    "Ice": {"weaknesses": ["Fire", "Fighting", "Rock", "Steel"], "resistances": ["Ice"], "immunities": []},
    "Fighting": {"weaknesses": ["Flying", "Psychic", "Fairy"], "resistances": ["Bug", "Rock", "Dark"], "immunities": []},
    "Poison": {"weaknesses": ["Ground", "Psychic"], "resistances": ["Grass", "Fighting", "Poison", "Bug", "Fairy"], "immunities": []},
    "Ground": {"weaknesses": ["Water", "Grass", "Ice"], "resistances": ["Poison", "Rock"], "immunities": ["Electric"]},
    "Flying": {"weaknesses": ["Electric", "Ice", "Rock"], "resistances": ["Grass", "Fighting", "Bug"], "immunities": ["Ground"]},
    "Psychic": {"weaknesses": ["Bug", "Ghost", "Dark"], "resistances": ["Fighting", "Psychic"], "immunities": []},
    "Bug": {"weaknesses": ["Fire", "Flying", "Rock"], "resistances": ["Grass", "Fighting", "Ground"], "immunities": []},
    "Rock": {"weaknesses": ["Water", "Grass", "Fighting", "Ground", "Steel"], "resistances": ["Normal", "Fire", "Poison", "Flying"], "immunities": []},
    "Ghost": {"weaknesses": ["Ghost", "Dark"], "resistances": ["Poison", "Bug"], "immunities": ["Normal", "Fighting"]},
    "Dragon": {"weaknesses": ["Ice", "Dragon", "Fairy"], "resistances": ["Fire", "Water", "Grass", "Electric"], "immunities": []},
    "Dark": {"weaknesses": ["Fighting", "Bug", "Fairy"], "resistances": ["Ghost", "Dark"], "immunities": ["Psychic"]},
    "Steel": {"weaknesses": ["Fire", "Fighting", "Ground"], "resistances": ["Normal", "Grass", "Ice", "Flying", "Psychic", "Bug", "Rock", "Dragon", "Steel", "Fairy"], "immunities": ["Poison"]},
    "Fairy": {"weaknesses": ["Poison", "Steel"], "resistances": ["Fighting", "Bug", "Dark"], "immunities": ["Dragon"]}
}

def get_multiplier(def_types: List[str], atk_type: str) -> float:
    mult = 1.0
    atk = atk_type.capitalize()
    for dt in def_types:
        dt = dt.capitalize()
        if dt not in TYPE_DATA: continue
        if atk in TYPE_DATA[dt]["weaknesses"]:
            mult *= 2.0
        elif atk in TYPE_DATA[dt]["resistances"]:
            mult *= 0.5
        elif atk in TYPE_DATA[dt]["immunities"]:
            mult *= 0.0
    return mult

def calculate_core_matchups(core_pokemon_types: List[List[str]]) -> Dict[str, List[str]]:
    weaknesses = []
    resistances = []
    all_types = list(TYPE_DATA.keys())
    
    for atk in all_types:
        score = 0
        for pk_types in core_pokemon_types:
            mult = get_multiplier(pk_types, atk)
            if mult > 1:
                score -= 1
            elif mult < 1:
                score += 1
        
        if score < 0:
            weaknesses.append(atk)
        elif score > 0:
            resistances.append(atk)
            
    return {"weaknesses": weaknesses, "resistances": resistances}
