import json
import urllib.request
import re
import time
from database.connection import SessionLocal
from database.models import Ability, Item, Move

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')

def get_pokeapi_item(item_slug: str):
    url = f"https://pokeapi.co/api/v2/item/{item_slug}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        return None

def js_to_dict(js_str):
    start = js_str.find('{')
    end = js_str.rfind('}')
    if start == -1 or end == -1: return {}
    obj_str = js_str[start:end+1]
    
    # 1. Quota le chiavi non quotate (es. name: -> "name":)
    obj_str = re.sub(r'([{,]\s*)([a-zA-Z0-9_]+)\s*:', r'\1"\2":', obj_str)
    
    # Rimuovi virgole trailing
    obj_str = re.sub(r',\s*}', '}', obj_str)
    obj_str = re.sub(r',\s*\]', ']', obj_str)
    
    try:
        return json.loads(obj_str)
    except Exception as e:
        print('JSON decode error in metadata:', e)
        return {}

def sync_metadata():
    session = SessionLocal()
    try:
        print("Sincronizzazione Metadati (Strumenti, Abilità, Mosse)...")
        
        # Abilità
        if session.query(Ability).count() == 0:
            print("Scarico le Abilità...")
            url = "https://play.pokemonshowdown.com/data/abilities.js"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                abilities_data = js_to_dict(response.read().decode())
                for a_id, a_data in abilities_data.items():
                    # Ignora chiavi numeriche se presenti
                    if str(a_id).isdigit(): continue
                    session.merge(Ability(
                        id=a_id,
                        name=a_data.get('name', ''),
                        short_desc=a_data.get('shortDesc', a_data.get('desc', 'Nessuna descrizione.'))
                    ))
            session.commit()
            print("Abilità sincronizzate.")

        # Strumenti
        if session.query(Item).count() == 0:
            print("Scarico gli Strumenti e recupero dettagli da PokéAPI...")
            url = "https://play.pokemonshowdown.com/data/items.js"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                items_data = js_to_dict(response.read().decode())
                
                total_items = len([i for i in items_data.keys() if not str(i).isdigit()])
                processed = 0
                
                for i_id, i_data in items_data.items():
                    if str(i_id).isdigit(): continue
                    name = i_data.get('name', '')
                    short_desc = i_data.get('shortDesc', i_data.get('desc', 'Nessuna descrizione.'))
                    
                    slug = slugify(name)
                    effect = None
                    sprite_url = None
                    
                    # Fetch from PokéAPI
                    pokeapi_data = get_pokeapi_item(slug)
                    if pokeapi_data:
                        # Extract effect
                        for entry in pokeapi_data.get('effect_entries', []):
                            if entry.get('language', {}).get('name') == 'en':
                                effect = entry.get('effect', '')
                                break
                        # Extract sprite
                        sprites = pokeapi_data.get('sprites', {})
                        sprite_url = sprites.get('default')
                        
                    if not sprite_url:
                        # Fallback sprite
                        sprite_url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/items/{slug}.png"

                    session.merge(Item(
                        id=i_id,
                        name=name,
                        short_desc=short_desc,
                        effect=effect,
                        sprite_url=sprite_url
                    ))
                    
                    processed += 1
                    if processed % 50 == 0:
                        print(f"  Elaborati {processed}/{total_items} strumenti...")
                        session.commit()
                        time.sleep(1) # Riduci il carico su PokéAPI

            session.commit()
            print("Strumenti sincronizzati.")

        # Mosse (Formato JSON nativo)
        if session.query(Move).count() == 0:
            print("Scarico le Mosse...")
            url = "https://play.pokemonshowdown.com/data/moves.json"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                moves_data = json.loads(response.read().decode())
                for m_id, m_data in moves_data.items():
                    if str(m_id).isdigit(): continue
                    acc = m_data.get('accuracy')
                    acc_val = acc if isinstance(acc, int) else 0 # 0 significa infallibile (true in showdown)
                    session.merge(Move(
                        id=m_id,
                        name=m_data.get('name', ''),
                        type=m_data.get('type', ''),
                        category=m_data.get('category', ''),
                        base_power=m_data.get('basePower', 0),
                        accuracy=acc_val,
                        priority=m_data.get('priority', 0),
                        short_desc=m_data.get('shortDesc', m_data.get('desc', 'Nessuna descrizione.'))
                    ))
            session.commit()
            print("Mosse sincronizzate.")
            
    except Exception as e:
        print(f"Errore nella sincronizzazione dei metadati: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    from database.connection import init_db
    init_db()
    sync_metadata()
