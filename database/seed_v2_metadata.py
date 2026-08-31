import os
import json
import re
from typing import Dict, Any

from database.connection import SessionLocal
from database.models_v2 import PokemonSpeciesV2, MoveV2, AbilityV2, ItemV2

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '', text)
    return text

def js_to_dict(js_str: str) -> Dict[str, Any]:
    start = js_str.find('{')
    end = js_str.rfind('}')
    if start == -1 or end == -1: return {}
    obj_str = js_str[start:end+1]
    
    obj_str = re.sub(r'([{,]\s*)([a-zA-Z0-9_]+)\s*:', r'\1"\2":', obj_str)
    obj_str = re.sub(r',\s*}', '}', obj_str)
    obj_str = re.sub(r',\s*\]', ']', obj_str)
    
    try:
        return json.loads(obj_str)
    except Exception as e:
        print(f"JSON decode error: {e}")
        return {}

def seed_v2_metadata():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    with SessionLocal() as session:
        print("1/5 Loading Pokedex & Abilities...")
        pokedex_path = os.path.join(base_dir, "pokedex.json")
        if os.path.exists(pokedex_path):
            with open(pokedex_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for pkmn_id, pkmn_data in data.items():
                num = pkmn_data.get("num", 0)
                if num <= 0: continue
                
                name = pkmn_data.get("name", "")
                base_stats = pkmn_data.get("baseStats", {})
                types = pkmn_data.get("types", [])
                
                # Extract abilities list
                abilities_dict = pkmn_data.get("abilities", {})
                abilities_list = list(abilities_dict.values())
                abilities_json = json.dumps(abilities_list) if abilities_list else None
                
                session.merge(PokemonSpeciesV2(
                    id=pkmn_id,
                    num=num,
                    name=name,
                    base_species_id=slugify(pkmn_data.get("baseSpecies", "")),
                    forme=pkmn_data.get("forme", ""),
                    type1=types[0] if len(types) > 0 else None,
                    type2=types[1] if len(types) > 1 else None,
                    bst_hp=base_stats.get("hp", 0),
                    bst_atk=base_stats.get("atk", 0),
                    bst_def=base_stats.get("def", 0),
                    bst_spa=base_stats.get("spa", 0),
                    bst_spd=base_stats.get("spd", 0),
                    bst_spe=base_stats.get("spe", 0),
                    abilities_json=abilities_json
                ))
            session.commit()
            print("Pokedex loaded.")
        else:
            print("pokedex.json not found!")

        print("2/5 Loading Moves...")
        moves_path = os.path.join(base_dir, "moves.json")
        if os.path.exists(moves_path):
            with open(moves_path, "r", encoding="utf-8") as f:
                moves_data = json.load(f)
            
            for m_id, m_data in moves_data.items():
                if str(m_id).isdigit(): continue
                acc = m_data.get('accuracy')
                acc_val = acc if isinstance(acc, int) else 0
                
                session.merge(MoveV2(
                    id=m_id,
                    name=m_data.get('name', ''),
                    type=m_data.get('type', ''),
                    category=m_data.get('category', ''),
                    base_power=m_data.get('basePower', 0),
                    accuracy=acc_val,
                    priority=m_data.get('priority', 0),
                    target=m_data.get('target', ''),
                    short_desc=m_data.get('shortDesc', m_data.get('desc', ''))
                ))
            session.commit()
            print("Moves loaded.")
        else:
            print("moves.json not found!")

        print("3/4 Loading Abilities...")
        abilities_path = os.path.join(base_dir, "abilities.js")
        if os.path.exists(abilities_path):
            with open(abilities_path, "r", encoding="utf-8") as f:
                abilities_data = js_to_dict(f.read())
                
            for a_id, a_data in abilities_data.items():
                if str(a_id).isdigit(): continue
                session.merge(AbilityV2(
                    id=a_id,
                    name=a_data.get('name', ''),
                    short_desc=a_data.get('shortDesc', a_data.get('desc', ''))
                ))
            session.commit()
            print("Abilities loaded.")
        else:
            print("abilities.js not found!")

        print("4/5 Loading Items...")
        items_path = os.path.join(base_dir, "items.js")
        if os.path.exists(items_path):
            with open(items_path, "r", encoding="utf-8") as f:
                items_data = js_to_dict(f.read())
                
            for i_id, i_data in items_data.items():
                if str(i_id).isdigit(): continue
                session.merge(ItemV2(
                    id=i_id,
                    name=i_data.get('name', ''),
                    short_desc=i_data.get('shortDesc', i_data.get('desc', ''))
                ))
            session.commit()
            print("Items loaded.")
        else:
            print("items.js not found!")

        print("5/5 Loading Learnsets...")
        import urllib.request
        try:
            req = urllib.request.Request('https://play.pokemonshowdown.com/data/learnsets.js', headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                learnsets_js = response.read().decode('utf-8')
                
            print("Parsing learnsets.js (may take a few seconds)...")
            learnsets_data = js_to_dict(learnsets_js)
            
            # Map learnsets to DB
            species_db = session.query(PokemonSpeciesV2).all()
            for pkmn in species_db:
                lset_info = learnsets_data.get(pkmn.id, {})
                learnset = lset_info.get("learnset", {})
                if learnset:
                    # learnset keys are the move IDs
                    moves_list = list(learnset.keys())
                    pkmn.learnset_json = json.dumps(moves_list)
            
            session.commit()
            print("Learnsets loaded.")
        except Exception as e:
            print(f"Failed to load learnsets: {e}")

if __name__ == "__main__":
    from database.connection import init_db
    init_db()
    seed_v2_metadata()
