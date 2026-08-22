import json
from typing import List, Dict, Any, Set
from sqlalchemy.orm import joinedload
from database.connection import SessionLocal
from database.models import Match, Team, PokemonBuild, Turn, TurnAction

SETUP_MOVES = {
    "swordsdance", "nastyplot", "dragondance", "quiverdance", 
    "calmmind", "bulkup", "coil", "irondefense", "amnesia", 
    "shiftgear", "tailglow"
}

def get_team_archetypes_and_groupings(max_distance: int = 2, format_filter: str = "Tutti", trainer_filter: str = "") -> list:
    session = SessionLocal()
    
    query = session.query(Team).join(Match).options(
        joinedload(Team.pokemon_builds).joinedload(PokemonBuild.species),
        joinedload(Team.pokemon_builds).joinedload(PokemonBuild.ability),
        joinedload(Team.match).joinedload(Match.turns).joinedload(Turn.actions),
        joinedload(Team.match).joinedload(Match.teams)
    )
    
    if format_filter and format_filter != "Tutti":
        query = query.filter(Match.format == format_filter)
    if trainer_filter:
        query = query.filter(Team.trainer_id.ilike(f"%{trainer_filter}%"))
        
    teams = query.all()
    
    processed_teams = []
    
    for team in teams:
        match = team.match
        if not match: continue
        N = len(match.turns)
        if N == 0: continue
        
        def normalize_species(sp: str) -> str:
            sp = sp.lower()
            if sp == "floettemega": return "floetteeternal"
            if sp == "sinistchamasterpiece": return "sinistcha"
            if sp.endswith("megax"): return sp[:-5]
            if sp.endswith("megay"): return sp[:-5]
            if sp.endswith("mega"): return sp[:-4]
            return sp
            
        species_ids = frozenset([normalize_species(pb.species_id) for pb in team.pokemon_builds if pb.species_id])
        abilities = set([pb.ability.name.lower().replace(" ", "") for pb in team.pokemon_builds if pb.ability and pb.ability.name])
        moves_list = set()
        
        for pb in team.pokemon_builds:
            if pb.moves:
                for m in pb.moves.split(","):
                    moves_list.add(m.strip().lower())
        
        i_farigiraf = 1 if any("farigiraf" in sp for sp in species_ids) else 0
        i_torkoal = 1 if any("torkoal" in sp for sp in species_ids) else 0
        i_tornadus = 1 if any("tornadus" in sp for sp in species_ids) else 0
        i_whimsicott = 1 if any("whimsicott" in sp for sp in species_ids) else 0
        
        i_drizzle = 1 if "drizzle" in abilities or "primordialsea" in abilities else 0
        is_winner = 1 if match.winner_id == team.trainer_id else 0
        
        p1_name = "P1"
        p2_name = "P2"
        for t in match.teams:
            if t.player_slot == "p1": p1_name = t.trainer_id
            if t.player_slot == "p2": p2_name = t.trainer_id
            
        processed_teams.append({
            "team_id": team.id,
            "match_id": match.id,
            "match_title": f"{p1_name} VS {p2_name}",
            "species_ids": species_ids,
            "is_winner": is_winner
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
                "match_ids": []
            }
        variants_dict[sp_set]["wins"] += pt["is_winner"]
        variants_dict[sp_set]["total"] += 1
        variants_dict[sp_set]["team_ids"].append(pt["team_id"])
        variants_dict[sp_set]["match_ids"].append({
            "id": pt["match_id"],
            "title": pt["match_title"]
        })
        
    variants_list = list(variants_dict.values())
    
    from src.analytics.archetypes import analizza_archetipo_team
    for v in variants_list:
        sp_name = "-".join(sorted(list(v["species_ids"])))[:15]
        arch_string = analizza_archetipo_team(sp_name, v["team_ids"], session)
        v["archetypes"] = [arch_string]
    
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
        
        all_archetypes = set()
        for v in comp_variants:
            all_archetypes.update(v["archetypes"])
            # Converte i set in liste in modo che iterandoli nella UI abbiano ordine stabile,
            # però facciamolo in un nuovo dictionary o sovrascriviamo se non già lista
            if isinstance(v["archetypes"], set):
                v["archetypes"] = list(v["archetypes"])
            if isinstance(v["species_ids"], frozenset) or isinstance(v["species_ids"], set):
                v["species_ids"] = sorted(list(v["species_ids"]))
            
        groupings.append({
            "core_species": core_species,
            "win_rate": win_rate,
            "total_matches": total_matches,
            "num_variants": len(comp_variants) - 1, # Escludiamo se stesso dal count varianti
            "archetypes": list(all_archetypes),
            "variants": comp_variants
        })
        
    groupings.sort(key=lambda x: x["total_matches"], reverse=True)
    session.close()
    return groupings

if __name__ == "__main__":
    res = get_team_archetypes_and_groupings()
    print(f"Trovati {len(res)} raggruppamenti.")
