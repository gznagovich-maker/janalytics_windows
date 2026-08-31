from typing import List, Dict, Any
from collections import Counter
from database.connection import SessionLocal
from database.models_v2 import MatchV2, MatchTeamV2, TeamVariantV2, PokemonBuild, PokemonSpeciesV2, ItemV2, TeamVariantBuild, PokemonBuildMove

class BatchGeneratorService:
    @staticmethod
    def get_available_formats() -> List[str]:
        session = SessionLocal()
        try:
            formats = session.query(MatchV2.format).distinct().all()
            return [f[0] for f in formats if f[0]]
        finally:
            session.close()

    @staticmethod
    def generate_threats_from_format(format_name: str, min_usage_pct: float, top_n_species: int = 50) -> List[Dict[str, Any]]:
        session = SessionLocal()
        try:
            match_teams = session.query(MatchTeamV2)\
                .join(MatchV2, MatchTeamV2.match_id == MatchV2.id)\
                .filter(MatchV2.format == format_name).all()
                
            variant_ids = set()
            for mt in match_teams:
                if mt.team_variant_id:
                    variant_ids.add(mt.team_variant_id)
            
            import collections
            variant_to_build_ids = collections.defaultdict(list)
            build_ids = set()
            if variant_ids:
                tvbs = session.query(TeamVariantBuild).filter(TeamVariantBuild.team_variant_id.in_(variant_ids)).all()
                for tvb in tvbs:
                    if tvb.build_id:
                        build_ids.add(tvb.build_id)
                        variant_to_build_ids[tvb.team_variant_id].append(tvb.build_id)
            
            all_builds = session.query(PokemonBuild).options(
                selectinload(PokemonBuild.item),
                selectinload(PokemonBuild.ability)
            ).filter(PokemonBuild.id.in_(build_ids)).all()
            build_dict = {b.id: b for b in all_builds}
            
            total_matches = session.query(MatchV2).filter(MatchV2.format == format_name).count()
            if total_matches == 0:
                return []
                
            builds = []
            for mt in match_teams:
                if mt.team_variant_id and mt.team_variant_id in variant_to_build_ids:
                    for b_id in variant_to_build_ids[mt.team_variant_id]:
                        if b_id in build_dict:
                            b = build_dict[b_id]
                            sp_name = b.species.name if getattr(b, 'species', None) else (b.species_id or "Sconosciuto")
                            item_name = "Sconosciuto"
                            if b.item_id:
                                item_name = b.item.name if getattr(b, 'item', None) else b.item_id.capitalize()
                                
                            ability_name = "Sconosciuta"
                            if b.ability_id:
                                ability_name = b.ability.name if getattr(b, 'ability', None) else b.ability_id.capitalize()
                            
                            parsed_moves = [ms.move.name if ms.move else ms.move_id for ms in sorted(b.move_slots, key=lambda x: x.slot)]
                            
                            builds.append({
                                "name": sp_name,
                                "nature": b.nature,
                                "item": item_name,
                                "ability": ability_name,
                                "moves": parsed_moves
                            })
                        
            # Contiamo le usage
            usage_counts = Counter(b["name"] for b in builds)
            threats = []
            
            # Ordina le specie per utilizzo decrescente
            sorted_species = [name for name, count in usage_counts.most_common(top_n_species)]
            
            for pokemon_name in sorted_species:
                count = usage_counts[pokemon_name]
                usage_pct = (count / (total_matches * 2)) * 100 # x2 perchè ci sono 2 team per match
                if usage_pct < min_usage_pct:
                    continue
                    
                poke_builds = [b for b in builds if b["name"] == pokemon_name]
                
                # Keep Natures with >15% usage
                nature_counts = Counter(b["nature"] for b in poke_builds if b["nature"])
                total_natures = sum(nature_counts.values()) if nature_counts else 1
                top_natures = [n for n, c in nature_counts.items() if (c / total_natures) >= 0.15]
                if not top_natures: top_natures = [nature_counts.most_common(1)[0][0]] if nature_counts else ["Hardy"]
                if not top_natures: top_natures = ["Hardy"]
                
                # Top 3 items
                item_counts = Counter(b["item"] for b in poke_builds if b["item"] and b["item"] not in ("Nessuno", "Sconosciuto"))
                top_items = [i for i, c in item_counts.most_common(3)]
                if not top_items: top_items = ["Nessuno"]
                
                # Top 3 abilities
                ability_counts = Counter(b["ability"] for b in poke_builds if b["ability"] and b["ability"] not in ("Nessuno", "Sconosciuta"))
                top_abilities = [a for a, c in ability_counts.most_common(3)]
                if not top_abilities: top_abilities = ["Nessuno"]
                
                # Top 6 moves
                all_moves = []
                for b in poke_builds:
                    all_moves.extend(b["moves"])
                move_counts = Counter(all_moves)
                top_moves = [m for m, c in move_counts.most_common(6)]
                
                # Generiamo le 4 varianti
                for nature in top_natures:
                    for item in top_items:
                        threats.append({
                            "name": pokemon_name,
                            "options": {
                                "nature": nature,
                                "item": item if item != "Nessuno" else None,
                                "ability": top_abilities[0] if top_abilities[0] != "Nessuno" else None,
                                "evs": {"hp": 4, "atk": 252, "def": 0, "spa": 252, "spd": 0, "spe": 252}
                            },
                            "moves": top_moves,
                            "source": "format"
                        })
                        
            return threats
        finally:
            session.close()

    @staticmethod
    def generate_threats_from_teams(teams_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        threats = []
        for team in teams_data:
            members = team.get("members", [])
            for member in members:
                # member è un oggetto TeamMember
                threats.append({
                    "name": member.species,
                    "options": {
                        "nature": member.nature,
                        "item": member.item,
                        "evs": member.evs if member.evs else {}
                    },
                    "common_moves": [m for m in member.moves if m],
                    "source": "team"
                })
        return threats
