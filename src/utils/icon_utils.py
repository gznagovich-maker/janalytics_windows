import os
import re
import urllib.request

def to_id(text: str) -> str:
    """Converte un nome (es. 'Ninetales-Alola') nell'ID base (es. 'ninetalesalola')."""
    return re.sub(r'[^a-z0-9]', '', str(text).lower()) if text else ""

import json

# Cache del pokedex per risolvere i nomi formattati
_POKEDEX_CACHE = None

def _get_pokedex_name(compact_id: str) -> str:
    global _POKEDEX_CACHE
    if _POKEDEX_CACHE is None:
        pokedex_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "pokedex.json"))
        try:
            with open(pokedex_path, "r", encoding="utf-8") as f:
                _POKEDEX_CACHE = json.load(f)
        except Exception:
            _POKEDEX_CACHE = {}
            
    data = _POKEDEX_CACHE.get(compact_id)
    if data and "name" in data:
        return data["name"]
    return compact_id

def get_pokemon_icon_path(species_name: str) -> str:
    """
    Restituisce il percorso dell'icona per il Pokémon, scaricandola se necessario.
    Usa l'ID compatto per mappare il file in modo robusto, e scarica da Showdown.
    """
    if not species_name or species_name in ("Vuoto", ""):
        return None
        
    compact_id = to_id(species_name)
    
    # Mapping manuale per forme specifiche (es. form male) che l'utenza/parser potrebbe indicare
    # ma che per il pokedex base e Showdown corrispondono alla forma senza suffisso.
    MANUAL_FALLBACKS = {
        "meowsticm": "meowstic",
        "indeedeem": "indeedee",
        "basculegionm": "basculegion",
        "oinkolognem": "oinkologne",
        "urshifusinglestrike": "urshifu",
        "lycanrocmidday": "lycanroc",
    }
    if compact_id in MANUAL_FALLBACKS:
        compact_id = MANUAL_FALLBACKS[compact_id]
        
    icon_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "icons"))
    os.makedirs(icon_dir, exist_ok=True)
    
    icon_path = os.path.join(icon_dir, f"{compact_id}.png")
    
    if not os.path.exists(icon_path):
        # Tenta di recuperare il nome formattato (es. Typhlosion-Hisui) dal pokedex.json
        # Questo è vitale se l'UI passa l'ID 'typhlosionhisui' perdendo i trattini
        proper_name = _get_pokedex_name(compact_id)
        raw_name = proper_name.lower()
        
        c1 = raw_name.replace(" ", "") # es. tapukoko, ninetales-alola
        
        # Gestisce i casi tipo Charizard-Mega-X -> charizard-megax
        c2 = ""
        if "-" in c1:
            parts = c1.split("-")
            c2 = parts[0] + "-" + "".join(parts[1:])
            
        urls_to_try = [
            f"https://play.pokemonshowdown.com/sprites/dex/{c1}.png",
            f"https://play.pokemonshowdown.com/sprites/dex/{c2}.png",
            f"https://play.pokemonshowdown.com/sprites/dex/{compact_id}.png",
            f"https://play.pokemonshowdown.com/sprites/gen5/{c1}.png",
            f"https://play.pokemonshowdown.com/sprites/gen5/{compact_id}.png",
        ]
        
        downloaded = False
        for url in urls_to_try:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=3) as r:
                    with open(icon_path, "wb") as f:
                        f.write(r.read())
                downloaded = True
                break
            except Exception:
                pass
                
        if not downloaded:
            # Fallback to baseSpecies if the specific form icon does not exist
            base_species = _POKEDEX_CACHE.get(compact_id, {}).get("baseSpecies")
            if base_species:
                base_path = get_pokemon_icon_path(base_species)
                if base_path and os.path.exists(base_path):
                    import shutil
                    shutil.copy2(base_path, icon_path)
                    return icon_path.replace("\\", "/")
                    
            print(f"[sprite] Fallito il download per {species_name} (ID: {compact_id}) usando {urls_to_try[0]}")
            return None
            
    return icon_path.replace("\\", "/")
