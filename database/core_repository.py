import itertools
from collections import Counter
from typing import List, Dict
from sqlalchemy.orm import Session
from database.models import Match, PokemonSpecies, MatchTeam, TeamVariant, PokemonSet
from src.domain.core_models import CoreTeammates, BuildDetails, PokemonUsageStats, CoreCombo

class MetaAnalysisRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_raw_teams(self, format_id: str) -> Dict[int, List[dict]]:
        """
        Returns a dict of team_id -> List of dictionaries containing pokemon data.
        """
        match_teams = self.session.query(MatchTeam).join(Match).filter(Match.format == format_id).all()
        
        variant_ids = set([mt.team_variant_id for mt in match_teams if mt.team_variant_id])
        team_variants = self.session.query(TeamVariant).filter(TeamVariant.id.in_(variant_ids)).all()
        
        set_ids = set()
        for tv in team_variants:
            if tv.pokemon_set_ids:
                for sid in tv.pokemon_set_ids:
                    set_ids.add(sid)
                    
        sets = self.session.query(PokemonSet).filter(PokemonSet.id.in_(set_ids)).all()
        set_dict = {s.id: s for s in sets}
        variant_dict = {tv.id: tv for tv in team_variants}
        
        teams = {}
        for mt in match_teams:
            tid = mt.id
            teams[tid] = []
            tv = variant_dict.get(mt.team_variant_id)
            if not tv or not tv.pokemon_set_ids:
                continue
                
            for sid in tv.pokemon_set_ids:
                if sid in set_dict:
                    b = set_dict[sid]
                    m = b.moves.split(',') if b.moves else []
                    m.sort()
                    moves_str = ",".join(m)
                    
                    item = b.item_id if b.item_id else "Nessuno"
                    nature = b.nature if b.nature else "Hardy"
                    moves_display = moves_str if moves_str else "Nessuna mossa"
                    
                    teams[tid].append({
                        'species': b.species_id,
                        'item': item,
                        'nature': nature,
                        'moves': moves_display,
                        'build_hash': f"{item}|{nature}|{moves_display}"
                    })
                    
        return teams

    def calculate_cores_for_pokemon(self, target_species: str, valid_teams: List[List[dict]], 
                                    species_types: Dict[str, List[str]], species_counter: Counter,
                                    target_build_hash: str = None) -> CoreTeammates:
        core2 = Counter()
        core3 = Counter()
        core4 = Counter()
        total_valid = 0
        
        for team in valid_teams:
            found = False
            for p in team:
                if p['species'] == target_species:
                    if target_build_hash is None or p['build_hash'] == target_build_hash:
                        found = True
                        break
            
            if not found: continue
            total_valid += 1
            
            companions = [p['species'] for p in team if p['species'] != target_species]
            companions.sort()
            
            for c in companions:
                core2[(c,)] += 1
                
            for c_combo in itertools.combinations(companions, 2):
                core3[c_combo] += 1
                
            for c_combo in itertools.combinations(companions, 3):
                core4[c_combo] += 1
                
        def format_core(counter, total) -> List[CoreCombo]:
            from src.domain.type_chart import calculate_core_matchups
            res = []
            for combo, count in counter.most_common(3):
                pct = (count / total) * 100 if total > 0 else 0
                
                full_core = list(combo) + [target_species]
                core_types_list = [species_types.get(m, []) for m in full_core]
                
                matchups = calculate_core_matchups(core_types_list)
                weaknesses = matchups["weaknesses"]
                resistances = matchups["resistances"]
                
                threats_counter = Counter()
                for w in weaknesses:
                    for pk, pk_types in species_types.items():
                        if w in pk_types:
                            threats_counter[pk] = species_counter.get(pk, 0)
                            
                top_threats = [t[0] for t in threats_counter.most_common(3) if t[1] > 0]
                
                res.append(CoreCombo(
                    pokemon=combo,
                    usage_percent=pct,
                    weaknesses=weaknesses,
                    resistances=resistances,
                    top_threats=top_threats
                ))
            return res
            
        return CoreTeammates(
            core_2=format_core(core2, total_valid),
            core_3=format_core(core3, total_valid),
            core_4=format_core(core4, total_valid)
        )

    def get_all_pokemon_stats(self, format_id: str) -> List[PokemonUsageStats]:
        teams_dict = self.get_raw_teams(format_id)
        teams = list(teams_dict.values())
        total_teams = len(teams)
        if total_teams == 0:
            return []
            
        # Fetch species types
        import json
        species_rows = self.session.query(PokemonSpecies.id, PokemonSpecies.types).all()
        species_types = {}
        for row in species_rows:
            try:
                t = json.loads(row.types) if isinstance(row.types, str) else row.types
                species_types[row.id] = t
            except:
                species_types[row.id] = []
                
        # Calculate global occurrences
        species_counter = Counter()
        for team in teams:
            for p in team:
                species_counter[p['species']] += 1
                
        results = []
        for species, total_occurrences in species_counter.items():
            usage_pct = (total_occurrences / total_teams) * 100
            
            global_cores = self.calculate_cores_for_pokemon(species, teams, species_types, species_counter)
            
            build_counter = Counter()
            build_data_map = {}
            for team in teams:
                for p in team:
                    if p['species'] == species:
                        b_hash = p['build_hash']
                        build_counter[b_hash] += 1
                        if b_hash not in build_data_map:
                            build_data_map[b_hash] = p
                            
            build_details_list = []
            for b_hash, b_count in build_counter.items():
                b_pct = (b_count / total_occurrences) * 100
                b_data = build_data_map[b_hash]
                b_cores = self.calculate_cores_for_pokemon(species, teams, species_types, species_counter, target_build_hash=b_hash)
                
                bd = BuildDetails(
                    item=b_data['item'],
                    nature=b_data['nature'],
                    moves=b_data['moves'],
                    usage_percent=b_pct,
                    occurrences=b_count,
                    cores=b_cores
                )
                build_details_list.append(bd)
                
            # Sort builds by usage descending
            build_details_list.sort(key=lambda x: x.usage_percent, reverse=True)
            
            stats = PokemonUsageStats(
                species_id=species,
                usage_percent=usage_pct,
                total_occurrences=total_occurrences,
                global_cores=global_cores,
                builds=build_details_list
            )
            results.append(stats)
            
        # Sort global results by usage descending
        results.sort(key=lambda x: x.usage_percent, reverse=True)
        return results
