import re
from typing import Dict, Any, Optional
from database.connection import SessionLocal
from database.models_v2 import PokemonSpeciesV2, MoveV2, ItemV2, AbilityV2, Tag

class PokeDataIntegrator:
    def __init__(self):
        self.session = SessionLocal()

    def normalize_to_showdown(self, identifier: str) -> str:
        """Convert any string to Showdown ID format."""
        return re.sub(r'[^a-z0-9]', '', identifier.lower())

    def get_pokemon(self, identifier: str) -> Dict[str, Any]:
        """Fetch unified Pokemon data from V2 DB."""
        sd_id = self.normalize_to_showdown(identifier)
        db_pkmn = self.session.query(PokemonSpeciesV2).filter(PokemonSpeciesV2.id == sd_id).first()
        
        result = {}
        if db_pkmn:
            types = []
            if db_pkmn.type1: types.append(db_pkmn.type1)
            if db_pkmn.type2: types.append(db_pkmn.type2)
            
            result['showdown'] = {
                'id': db_pkmn.id,
                'name': db_pkmn.name,
                'types': types,
                'base_stats': {
                    'hp': db_pkmn.bst_hp,
                    'atk': db_pkmn.bst_atk,
                    'def': db_pkmn.bst_def,
                    'spa': db_pkmn.bst_spa,
                    'spd': db_pkmn.bst_spd,
                    'spe': db_pkmn.bst_spe,
                },
                'sprite_url': db_pkmn.sprite_url,
                'artwork_url': db_pkmn.artwork_url
            }
        return result

    def get_move(self, identifier: str) -> Dict[str, Any]:
        sd_id = self.normalize_to_showdown(identifier)
        db_move = self.session.query(MoveV2).filter(MoveV2.id == sd_id).first()
        
        result = {}
        if db_move:
            result['showdown'] = {
                'id': db_move.id,
                'name': db_move.name,
                'type': db_move.type,
                'category': db_move.category,
                'base_power': db_move.base_power,
                'accuracy': db_move.accuracy,
                'priority': db_move.priority,
                'desc': db_move.short_desc,
                'target': db_move.target
            }
        return result

    def get_item(self, identifier: str) -> Dict[str, Any]:
        sd_id = self.normalize_to_showdown(identifier)
        db_item = self.session.query(ItemV2).filter(ItemV2.id == sd_id).first()
        
        result = {}
        if db_item:
            result['showdown'] = {
                'id': db_item.id,
                'name': db_item.name,
                'desc': db_item.short_desc,
                'sprite_url': db_item.sprite_url
            }
        return result

    def get_ability(self, identifier: str) -> Dict[str, Any]:
        sd_id = self.normalize_to_showdown(identifier)
        db_ability = self.session.query(AbilityV2).filter(AbilityV2.id == sd_id).first()
        
        result = {}
        if db_ability:
            result['showdown'] = {
                'id': db_ability.id,
                'name': db_ability.name,
                'desc': db_ability.short_desc
            }
        return result

    def get_field_condition(self, identifier: str) -> Dict[str, Any]:
        """Fetch field condition data."""
        # Field conditions are in the Tag table with category 'weather' or 'terrain'
        sd_id = self.normalize_to_showdown(identifier)
        db_tag = self.session.query(Tag).filter(
            Tag.name.ilike(f"%{identifier}%"),
            Tag.category.in_(['weather', 'terrain'])
        ).first()
        
        result = {}
        if db_tag:
            result['showdown'] = {
                'id': sd_id,
                'name': db_tag.name,
                'type': db_tag.category,
                'desc': f"{db_tag.name} ({db_tag.category})"
            }
        return result

    def close(self):
        self.session.close()

if __name__ == "__main__":
    integrator = PokeDataIntegrator()
    print("Testing data integrator...")
    
    # Test Pokemon
    pkmn = integrator.get_pokemon("mr mime")
    print(f"Pokemon: {pkmn.get('showdown', {}).get('name', 'N/A')}")
    
    # Test Move
    move = integrator.get_move("solar-beam")
    print(f"Move: {move.get('showdown', {}).get('name', 'N/A')} | Base Power: {move.get('showdown', {}).get('base_power', 'N/A')}")
    
    # Test Item
    item = integrator.get_item("Choice Band")
    print(f"Item: {item.get('showdown', {}).get('name', 'N/A')}")
    
    integrator.close()
