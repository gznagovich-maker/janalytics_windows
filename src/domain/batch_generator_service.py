from typing import List, Dict, Any
from collections import Counter
from database.connection import SessionLocal
from database.models_v2 import MatchV2, MatchTeamV2, TeamVariantV2, PokemonBuild, PokemonSpeciesV2, ItemV2, TeamVariantBuild, PokemonBuildMove

from src.domain.team_builder_service import parse_pokepaste
from sqlalchemy.orm import selectinload

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
    def generate_defensive_threats(format_name: str, min_usage_pct: float = 1.0, top_n_species: int = 20) -> List[Dict[str, Any]]:
        session = SessionLocal()
        try:
            total_matches = session.query(MatchV2).filter(MatchV2.format == format_name).count()
            if total_matches == 0:
                return []
                
            match_teams = session.query(MatchTeamV2).join(MatchV2).filter(MatchV2.format == format_name).all()
            variant_ids = {mt.team_variant_id for mt in match_teams if mt.team_variant_id}
            
            if not variant_ids:
                return []
                
            variant_builds = session.query(TeamVariantBuild).filter(TeamVariantBuild.team_variant_id.in_(variant_ids)).all()
            build_ids = {vb.build_id for vb in variant_builds}
            
            # Use selectinload to eagerly load related entities
            builds_db = session.query(PokemonBuild).options(
                selectinload(PokemonBuild.species),
                selectinload(PokemonBuild.item),
                selectinload(PokemonBuild.ability),
                selectinload(PokemonBuild.move_slots).selectinload(PokemonBuildMove.move)
            ).filter(PokemonBuild.id.in_(build_ids)).all()
            
            build_dict = {b.id: b for b in builds_db}
            
            variant_to_build_ids = {}
            for vb in variant_builds:
                variant_to_build_ids.setdefault(vb.team_variant_id, []).append(vb.build_id)
                
            builds = []
            species_cache = {}
            for mt in match_teams:
                if mt.team_variant_id and mt.team_variant_id in variant_to_build_ids:
                    for b_id in variant_to_build_ids[mt.team_variant_id]:
                        if b_id in build_dict:
                            b = build_dict[b_id]
                            sp_name = b.species.name if getattr(b, 'species', None) else (b.species_id or "Sconosciuto")
                            
                            if sp_name not in species_cache and getattr(b, 'species', None):
                                species_cache[sp_name] = b.species
                                
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
                        
            usage_counts = Counter(b["name"] for b in builds)
            threats = []
            
            sorted_species = [name for name, count in usage_counts.most_common(top_n_species)]
            
            # Map Natures to boosted stats
            nature_boosts = {
                "Lonely": "atk", "Brave": "atk", "Adamant": "atk", "Naughty": "atk",
                "Bold": "def", "Relaxed": "def", "Impish": "def", "Lax": "def",
                "Timid": "spe", "Hasty": "spe", "Jolly": "spe", "Naive": "spe",
                "Modest": "spa", "Mild": "spa", "Quiet": "spa", "Rash": "spa",
                "Calm": "spd", "Gentle": "spd", "Sassy": "spd", "Careful": "spd",
                "Hardy": None, "Docile": None, "Serious": None, "Bashful": None, "Quirky": None
            }
            
            for pokemon_name in sorted_species:
                count = usage_counts[pokemon_name]
                usage_pct = (count / (total_matches * 2)) * 100
                if usage_pct < min_usage_pct:
                    continue
                    
                poke_builds = [b for b in builds if b["name"] == pokemon_name]
                
                # Top 3 Natures
                nature_counts = Counter(b["nature"] for b in poke_builds if b["nature"])
                top_natures = [n for n, c in nature_counts.most_common(3)]
                if not top_natures: top_natures = ["Hardy"]
                
                # Top 2 items
                item_counts = Counter(b["item"] for b in poke_builds if b["item"] and b["item"] not in ("Nessuno", "Sconosciuto"))
                top_items = [i for i, c in item_counts.most_common(2)]
                if not top_items: top_items = ["Nessuno"]
                
                # Top ability
                ability_counts = Counter(b["ability"] for b in poke_builds if b["ability"] and b["ability"] not in ("Nessuno", "Sconosciuta"))
                top_abilities = [a for a, c in ability_counts.most_common(1)]
                ability = top_abilities[0] if top_abilities else "Nessuno"
                
                # Top moves
                all_moves = []
                for b in poke_builds:
                    all_moves.extend(b["moves"])
                move_counts = Counter(all_moves)
                top_moves = [m for m, c in move_counts.most_common(4)]
                
                # Get base stats to calculate lowest defense
                sp_model = species_cache.get(pokemon_name)
                bst_def = sp_model.bst_def if sp_model else 100
                bst_spd = sp_model.bst_spd if sp_model else 100
                
                lowest_def = "def" if bst_def <= bst_spd else "spd"
                
                for nature in top_natures:
                    for item in top_items:
                        # 66 EV Rules: 32 HP, 32 Nature Stat, 2 Lowest Def
                        evs = {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}
                        boosted_stat = nature_boosts.get(nature)
                        
                        if boosted_stat:
                            evs[boosted_stat] = 32
                        else:
                            # Neutral nature -> fallback to 32 in Atk or SpA (just as dummy)
                            evs["atk"] = 32
                            
                        # Assign remaining 2 to lowest def
                        evs[lowest_def] = 2
                        
                        # Fix for same stat getting both 32 and 2
                        if boosted_stat == lowest_def:
                            evs[lowest_def] = 32
                            other_def = "spd" if lowest_def == "def" else "def"
                            evs[other_def] = 2
                            
                        # Also pass base stats to the optimizer
                        base_stats = {
                            "hp": sp_model.bst_hp if sp_model else 100,
                            "atk": sp_model.bst_atk if sp_model else 100,
                            "def": sp_model.bst_def if sp_model else 100,
                            "spa": sp_model.bst_spa if sp_model else 100,
                            "spd": sp_model.bst_spd if sp_model else 100,
                            "spe": sp_model.bst_spe if sp_model else 100
                        }
                        
                        threats.append({
                            "name": pokemon_name,
                            "options": {
                                "nature": nature,
                                "item": item if item != "Nessuno" else None,
                                "ability": ability if ability != "Nessuno" else None,
                                "evs": evs
                            },
                            "baseStats": base_stats,
                            "moves": top_moves,
                            "source": "format"
                        })
                        
            return threats
        finally:
            session.close()

    @staticmethod
    def generate_threats_from_paste(paste_text: str) -> List[Dict[str, Any]]:
        members = parse_pokepaste(paste_text, corrections={})
        threats = []
        
        # Lookup baseStats from DB for speed tier comparisons
        session = SessionLocal()
        try:
            species_names = [m.species for m in members if m.species]
            species_models = {}
            if species_names:
                sp_rows = session.query(PokemonSpeciesV2).filter(
                    PokemonSpeciesV2.name.in_(species_names)
                ).all()
                species_models = {sp.name: sp for sp in sp_rows}
            
            for member in members:
                evs_raw = member.evs if member.evs else {}
                evs = {
                    "hp": evs_raw.get("HP", 0),
                    "atk": evs_raw.get("Atk", 0),
                    "def": evs_raw.get("Def", 0),
                    "spa": evs_raw.get("SpA", 0),
                    "spd": evs_raw.get("SpD", 0),
                    "spe": evs_raw.get("Spe", 0)
                }
                
                # Retrieve base stats from DB (needed for speed tier)
                sp_model = species_models.get(member.species)
                base_stats = {
                    "hp": sp_model.bst_hp if sp_model else 100,
                    "atk": sp_model.bst_atk if sp_model else 100,
                    "def": sp_model.bst_def if sp_model else 100,
                    "spa": sp_model.bst_spa if sp_model else 100,
                    "spd": sp_model.bst_spd if sp_model else 100,
                    "spe": sp_model.bst_spe if sp_model else 100
                }
                
                # Showdown paste EVs are standard (0-252).
                # It's up to the parser and optimizer to scale them if needed, but we keep them as is.
                threats.append({
                    "name": member.species,
                    "options": {
                        "nature": member.nature if member.nature else "Serious",
                        "item": member.item if member.item else "Nessuno",
                        "ability": member.ability if member.ability else "Sconosciuta",
                        "evs": evs
                    },
                    "baseStats": base_stats,
                    "moves": member.moves,
                    "source": "paste"
                })
        finally:
            session.close()
        return threats

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

    @staticmethod
    def generate_threats_from_vgcpaste_imports(imported_teams) -> List[Dict[str, Any]]:
        """
        Converte i team importati dalla sezione VGCPastes nel formato
        Dict usato dagli optimizer (Offense/Bulk).

        Args:
            imported_teams: Lista di ImportedTeam dal GSheet import service.

        Returns:
            Lista di Dict con chiavi: name, options, baseStats, moves, source.
        """
        threats = []
        seen_keys = set()

        session = SessionLocal()
        try:
            # Pre-cache delle species per le base stats
            all_species = set()
            for team in imported_teams:
                for member in team.members:
                    all_species.add(member.species)

            species_cache = {}
            if all_species:
                sp_rows = session.query(PokemonSpeciesV2).filter(
                    PokemonSpeciesV2.name.in_(list(all_species))
                ).all()
                species_cache = {sp.name: sp for sp in sp_rows}

            for team in imported_teams:
                for member in team.members:
                    # Deduplicazione: stessa specie + stessi EVs + stessa natura
                    evs_raw = member.evs if member.evs else {}
                    dedup_key = (
                        member.species,
                        member.nature or "Serious",
                        member.item or "",
                        tuple(sorted(evs_raw.items())),
                    )
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    # Converti le chiavi EVs al formato lowercase usato dagli optimizer
                    ev_key_map = {
                        "HP": "hp", "Atk": "atk", "Def": "def",
                        "SpA": "spa", "SpD": "spd", "Spe": "spe",
                        "hp": "hp", "atk": "atk", "def": "def",
                        "spa": "spa", "spd": "spd", "spe": "spe",
                    }
                    evs = {}
                    for k, v in evs_raw.items():
                        mapped = ev_key_map.get(k, k.lower())
                        evs[mapped] = v

                    # Base stats dal DB
                    sp_model = species_cache.get(member.species)
                    base_stats = {
                        "hp": sp_model.bst_hp if sp_model else 100,
                        "atk": sp_model.bst_atk if sp_model else 100,
                        "def": sp_model.bst_def if sp_model else 100,
                        "spa": sp_model.bst_spa if sp_model else 100,
                        "spd": sp_model.bst_spd if sp_model else 100,
                        "spe": sp_model.bst_spe if sp_model else 100,
                    }

                    threats.append({
                        "name": member.species,
                        "options": {
                            "nature": member.nature or "Serious",
                            "item": member.item if member.item else None,
                            "ability": member.ability if member.ability else None,
                            "evs": evs,
                        },
                        "baseStats": base_stats,
                        "moves": [m for m in member.moves if m],
                        "source": "vgcpaste",
                    })
        finally:
            session.close()

        return threats
