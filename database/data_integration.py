import json
import urllib.request
import re
import os
from typing import Dict, Any, Optional
from database.connection import SessionLocal
from database.models import PokemonSpecies, Move, Item, Ability

CACHE_FILE = "pokeapi_cache.json"

class PokeDataIntegrator:
    def __init__(self, cache_file: str = CACHE_FILE):
        self.cache_file = cache_file
        self.cache = self._load_cache()
        self.session = SessionLocal()

    def _load_cache(self) -> Dict[str, Any]:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f)
        except Exception as e:
            print(f"Error saving cache: {e}")

    def normalize_to_showdown(self, identifier: str) -> str:
        """Convert any string/PokeAPI ID to Showdown ID format."""
        return re.sub(r'[^a-z0-9]', '', identifier.lower())

    def normalize_to_pokeapi(self, name: str) -> str:
        """Convert a standard Name to PokeAPI ID format."""
        text = name.lower()
        # Handle special cases
        text = text.replace("'", "")
        text = text.replace(".", "")
        text = text.replace(":", "")
        text = re.sub(r'[^a-z0-9]+', '-', text)
        return text.strip('-')

    def _fetch_pokeapi(self, endpoint: str, identifier: str) -> Optional[Dict[str, Any]]:
        """Fetch from PokeAPI with caching."""
        cache_key = f"{endpoint}/{identifier}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        url = f"https://pokeapi.co/api/v2/{endpoint}/{identifier}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                self.cache[cache_key] = data
                self._save_cache()
                return data
        except Exception as e:
            # Silently fail, it might just be a 404 for Showdown specific items
            return None

    def get_pokemon(self, identifier: str) -> Dict[str, Any]:
        """Fetch unified Pokemon data."""
        sd_id = self.normalize_to_showdown(identifier)
        db_pkmn = self.session.query(PokemonSpecies).filter(PokemonSpecies.id == sd_id).first()
        
        result = {}
        pokeapi_id = identifier
        
        if db_pkmn:
            result['showdown'] = {
                'id': db_pkmn.id,
                'name': db_pkmn.name,
                'types': db_pkmn.types,
                'base_stats': db_pkmn.base_stats,
                'sprite_url': db_pkmn.sprite_url,
                'artwork_url': db_pkmn.artwork_url
            }
            pokeapi_id = self.normalize_to_pokeapi(db_pkmn.name)

        api_data = self._fetch_pokeapi('pokemon', pokeapi_id)
        if api_data:
            result['pokeapi'] = {
                'id': api_data['id'],
                'height': api_data['height'],
                'weight': api_data['weight'],
                'sprites': api_data['sprites'],
            }
            # Fetch species for flavor text
            species_data = self._fetch_pokeapi('pokemon-species', pokeapi_id)
            if species_data:
                for entry in species_data.get('flavor_text_entries', []):
                    if entry.get('language', {}).get('name') == 'en':
                        result['pokeapi']['flavor_text'] = entry['flavor_text'].replace('\n', ' ')
                        break
                        
        return result

    def get_move(self, identifier: str) -> Dict[str, Any]:
        sd_id = self.normalize_to_showdown(identifier)
        db_move = self.session.query(Move).filter(Move.id == sd_id).first()
        
        result = {}
        pokeapi_id = identifier
        
        if db_move:
            result['showdown'] = {
                'id': db_move.id,
                'name': db_move.name,
                'type': db_move.type,
                'category': db_move.category,
                'base_power': db_move.base_power,
                'accuracy': db_move.accuracy,
                'priority': db_move.priority,
                'desc': db_move.short_desc
            }
            pokeapi_id = self.normalize_to_pokeapi(db_move.name)

        api_data = self._fetch_pokeapi('move', pokeapi_id)
        if api_data:
            result['pokeapi'] = {
                'id': api_data['id'],
                'pp': api_data['pp'],
                'effect_chance': api_data['effect_chance'],
                'stat_changes': api_data.get('stat_changes', []),
                'target': api_data['target']['name']
            }
            
        return result

    def get_item(self, identifier: str) -> Dict[str, Any]:
        sd_id = self.normalize_to_showdown(identifier)
        db_item = self.session.query(Item).filter(Item.id == sd_id).first()
        
        result = {}
        pokeapi_id = identifier
        
        if db_item:
            result['showdown'] = {
                'id': db_item.id,
                'name': db_item.name,
                'desc': db_item.short_desc,
                'sprite_url': db_item.sprite_url
            }
            pokeapi_id = self.normalize_to_pokeapi(db_item.name)

        api_data = self._fetch_pokeapi('item', pokeapi_id)
        if api_data:
            result['pokeapi'] = {
                'id': api_data.get('id'),
                'cost': api_data.get('cost'),
                'fling_power': api_data.get('fling_power'),
                'category': api_data.get('category', {}).get('name')
            }
            
        return result

    def get_ability(self, identifier: str) -> Dict[str, Any]:
        sd_id = self.normalize_to_showdown(identifier)
        db_ability = self.session.query(Ability).filter(Ability.id == sd_id).first()
        
        result = {}
        pokeapi_id = identifier
        
        if db_ability:
            result['showdown'] = {
                'id': db_ability.id,
                'name': db_ability.name,
                'desc': db_ability.short_desc
            }
            pokeapi_id = self.normalize_to_pokeapi(db_ability.name)

        api_data = self._fetch_pokeapi('ability', pokeapi_id)
        if api_data:
            result['pokeapi'] = {
                'id': api_data['id'],
                'is_main_series': api_data['is_main_series'],
                'generation': api_data['generation']['name']
            }
            
        return result

    def get_field_condition(self, identifier: str) -> Dict[str, Any]:
        """
        Field conditions (Weather, Terrain) are not directly represented as single entities in PokeAPI.
        We will rely mostly on Showdown mappings and fetch related moves/abilities from PokeAPI if needed.
        """
        sd_id = self.normalize_to_showdown(identifier)
        result = {
            'showdown': {
                'id': sd_id,
                'name': identifier,
                'type': 'field_condition',
                'desc': 'Relying on Showdown definitions.'
            }
        }
        
        # We can map standard weathers to their setter moves to get PokeAPI info
        weather_move_map = {
            'raindance': 'rain-dance',
            'sunnyday': 'sunny-day',
            'sandstorm': 'sandstorm',
            'hail': 'hail',
            'snowscape': 'snowscape',
            'electricterrain': 'electric-terrain',
            'grassyterrain': 'grassy-terrain',
            'psychicterrain': 'psychic-terrain',
            'mistyterrain': 'misty-terrain',
            'trickroom': 'trick-room',
            'tailwind': 'tailwind'
        }
        
        if sd_id in weather_move_map:
            api_data = self._fetch_pokeapi('move', weather_move_map[sd_id])
            if api_data:
                result['pokeapi'] = {
                    'related_move_id': api_data['id'],
                    'related_move_name': api_data['name'],
                    'effect_entries': api_data.get('effect_entries', [])
                }
                
        return result

    def close(self):
        self.session.close()

if __name__ == "__main__":
    integrator = PokeDataIntegrator()
    print("Testing data integrator...")
    
    # Test Pokemon
    pkmn = integrator.get_pokemon("mr mime")
    print(f"Pokemon: {pkmn.get('showdown', {}).get('name', 'N/A')} | PokeAPI ID: {pkmn.get('pokeapi', {}).get('id', 'N/A')}")
    
    # Test Move
    move = integrator.get_move("solar-beam")
    print(f"Move: {move.get('showdown', {}).get('name', 'N/A')} | Base Power: {move.get('showdown', {}).get('base_power', 'N/A')}")
    
    # Test Item
    item = integrator.get_item("Choice Band")
    print(f"Item: {item.get('showdown', {}).get('name', 'N/A')} | Cost: {item.get('pokeapi', {}).get('cost', 'N/A')}")
    
    integrator.close()
