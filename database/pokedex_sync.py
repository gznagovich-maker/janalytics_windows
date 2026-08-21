import json
import urllib.request
import re
import time
from database.connection import SessionLocal
from database.models import PokemonSpecies

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')

def get_pokeapi_pokemon(slug: str):
    url = f"https://pokeapi.co/api/v2/pokemon/{slug}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except Exception:
        return None

def sync_pokedex():
    session = SessionLocal()
    try:
        count = session.query(PokemonSpecies).count()
        if count > 0:
            print(f"Pokédex già sincronizzato. Presenti {count} specie.")
            return

        print("Scarico i dati del Pokédex da Pokémon Showdown...")
        url = "https://play.pokemonshowdown.com/data/pokedex.json"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())

        print("Sincronizzazione in corso con arricchimento da PokéAPI...")
        
        valid_pokemon = [k for k, v in data.items() if v.get("num", 0) > 0]
        total_pokemon = len(valid_pokemon)
        processed = 0
        
        for pkmn_id, pkmn_data in data.items():
            num = pkmn_data.get("num", 0)
            if num <= 0:
                continue

            name = pkmn_data.get("name")
            slug = slugify(name)
            
            artwork_url = None
            
            # Fetch from PokéAPI
            pokeapi_data = get_pokeapi_pokemon(slug)
            if pokeapi_data:
                sprites = pokeapi_data.get("sprites", {})
                
                # Check for official artwork
                other = sprites.get("other", {})
                official = other.get("official-artwork", {})
                artwork_url = official.get("front_default")
                
            if not artwork_url:
                # Fallback to base species official artwork using num
                artwork_url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{num}.png"

            db_species = PokemonSpecies(
                id=pkmn_id,
                num=num,
                name=name,
                base_species=pkmn_data.get("baseSpecies") or name,
                forme=pkmn_data.get("forme", ""),
                types=pkmn_data.get("types", []),
                base_stats=pkmn_data.get("baseStats", {}),
                sprite_url=None,  # Come richiesto, solo artwork ufficiali
                artwork_url=artwork_url
            )
            session.merge(db_species)
            
            processed += 1
            if processed % 50 == 0:
                print(f"  Elaborati {processed}/{total_pokemon} Pokémon...")
                session.commit()
                # Optional: limit rate slightly
                time.sleep(0.5)
            
        session.commit()
        print("Sincronizzazione completata!")
    except Exception as e:
        print(f"Errore nella sincronizzazione del Pokédex: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    from database.connection import init_db
    init_db()
    sync_pokedex()
