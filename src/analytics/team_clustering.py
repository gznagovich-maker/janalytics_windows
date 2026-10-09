import json
from typing import List, Dict, Any, Set
from sqlalchemy.orm import joinedload, selectinload
from database.connection import SessionLocal
from database.models_v2 import MatchV2, MatchTeamV2, TeamVariantV2, TeamVariantBuild, PokemonBuild, TurnV2, TurnActionV2

def get_team_archetypes_and_groupings(max_distance: int = 2, format_filter: str = "Tutti", trainer_filter: str = "", min_elo: int = 0) -> list:
    session = SessionLocal()
    
    query = session.query(MatchTeamV2).join(MatchV2).options(
        joinedload(MatchTeamV2.match).joinedload(MatchV2.turns).joinedload(TurnV2.actions),
        joinedload(MatchTeamV2.match).joinedload(MatchV2.teams),
        joinedload(MatchTeamV2.variant).joinedload(TeamVariantV2.builds).joinedload(TeamVariantBuild.build),
        joinedload(MatchTeamV2.trainer)
    )
    
    if format_filter and format_filter != "Tutti":
        query = query.filter(MatchV2.format == format_filter)
    if trainer_filter:
        query = query.filter(MatchTeamV2.trainer_id.ilike(f"%{trainer_filter}%"))
        
    teams = query.all()
    
    def normalize_species(sp: str) -> str:
        if not sp: return ""
        sp = sp.lower()
        if sp == "floettemega": return "floetteeternal"
        if sp == "sinistchamasterpiece": return "sinistcha"
        if sp.endswith("megax"): return sp[:-5]
        if sp.endswith("megay"): return sp[:-5]
        if sp.endswith("mega"): return sp[:-4]
        return sp
        
    processed_teams = []
    
    for team in teams:
        match = team.match
        if not match: continue
        N = len(match.turns)
        if N == 0: continue
        
        rating = team.trainer.rating if team.trainer and team.trainer.rating else None
        if min_elo > 0 and (rating is None or rating < min_elo):
            continue
            
        species_ids = set()
        if team.variant and team.variant.builds:
            for tvb in team.variant.builds:
                if tvb.build and tvb.build.species_id:
                    species_ids.add(normalize_species(tvb.build.species_id))
        species_ids = frozenset(species_ids)
        
        is_winner = 1 if match.winner_id == team.trainer_id else 0
        
        p1_name = "P1"
        p2_name = "P2"
        for t in match.teams:
            if t.player_slot == "p1": p1_name = t.trainer_id
            if t.player_slot == "p2": p2_name = t.trainer_id
            
        processed_teams.append({
            "team_id": team.id,
            "team_variant_id": team.team_variant_id,
            "match_id": match.id,
            "match_title": f"{p1_name} VS {p2_name}",
            "species_ids": species_ids,
            "is_winner": is_winner,
            "trainer_rating": rating
        })

    variants_dict = {}
    for pt in processed_teams:
        sp_set = pt["species_ids"]
        if sp_set not in variants_dict:
            variants_dict[sp_set] = {
                "species_ids": sp_set,
                "wins": 0,
                "total": 0,
                "team_ids": [],
                "match_ids": [],
                "ratings": [],
                "configs": {}
            }
        
        rating = pt["trainer_rating"]
        if rating is not None:
            variants_dict[sp_set]["ratings"].append(rating)
            
        variants_dict[sp_set]["wins"] += pt["is_winner"]
        variants_dict[sp_set]["total"] += 1
        variants_dict[sp_set]["team_ids"].append(pt["team_id"])
        
        # We keep match_ids just in case, but configs will store the hierarchical data
        variants_dict[sp_set]["match_ids"].append({
            "id": pt["match_id"],
            "title": pt["match_title"]
        })
        
        config_id = pt["team_variant_id"]
        if config_id not in variants_dict[sp_set]["configs"]:
            variants_dict[sp_set]["configs"][config_id] = {
                "matches": [],
                "ratings": []
            }
            
        variants_dict[sp_set]["configs"][config_id]["matches"].append({
            "id": pt["match_id"],
            "title": pt["match_title"],
            "rating": rating
        })
        if rating is not None:
            variants_dict[sp_set]["configs"][config_id]["ratings"].append(rating)
            
    variants_list = list(variants_dict.values())
    
    from src.analytics.archetypes import analizza_archetipo_team
    for v in variants_list:
        sp_list = list(v["species_ids"])
        arch_string = analizza_archetipo_team(sp_list, v["team_ids"], session)
        v["archetypes"] = [arch_string]
        
        v["avg_elo"] = int(round(sum(v["ratings"]) / len(v["ratings"]))) if v["ratings"] else 0
        for config_id, config_data in v["configs"].items():
            config_data["avg_elo"] = int(round(sum(config_data["ratings"]) / len(config_data["ratings"]))) if config_data["ratings"] else 0
    
    n_variants = len(variants_list)
    adj = {i: [] for i in range(n_variants)}
    
    for i in range(n_variants):
        for j in range(i + 1, n_variants):
            intersect = len(variants_list[i]["species_ids"].intersection(variants_list[j]["species_ids"]))
            distance = 6 - intersect
            if distance <= max_distance:
                adj[i].append(j)
                adj[j].append(i)
                
    components = []
    for i in range(n_variants):
        comp = [i] + adj[i]
        components.append((i, comp))
            
    groupings = []
    for core_idx, comp in components:
        comp_variants = [variants_list[idx] for idx in comp]
        
        core_species = list(variants_list[core_idx]["species_ids"])
        
        total_wins = sum(v["wins"] for v in comp_variants)
        total_matches = sum(v["total"] for v in comp_variants)
        win_rate = round((total_wins / total_matches) * 100, 2) if total_matches > 0 else 0
        
        total_ratings = []
        all_archetypes = set()
        for v in comp_variants:
            all_archetypes.update(v["archetypes"])
            total_ratings.extend(v["ratings"])
            if isinstance(v["archetypes"], set):
                v["archetypes"] = list(v["archetypes"])
            if isinstance(v["species_ids"], frozenset) or isinstance(v["species_ids"], set):
                v["species_ids"] = sorted(list(v["species_ids"]))
                
        avg_elo = int(round(sum(total_ratings) / len(total_ratings))) if total_ratings else 0
            
        groupings.append({
            "core_species": core_species,
            "win_rate": win_rate,
            "total_matches": total_matches,
            "avg_elo": avg_elo,
            "num_variants": len(comp_variants) - 1,
            "archetypes": list(all_archetypes),
            "variants": comp_variants
        })
        
    groupings.sort(key=lambda x: x["total_matches"], reverse=True)
    session.close()
    return groupings

if __name__ == "__main__":
    res = get_team_archetypes_and_groupings()
    print(f"Trovati {len(res)} raggruppamenti.")

