import json
from collections import Counter, defaultdict
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from database.models_v2 import MatchTeamV2, MatchV2, TurnV2, TurnActionV2, TeamVariantV2

def analizza_archetipo_statico(species_list: list[str]) -> list[str]:
    """
    Deriva l'archetipo da un'analisi statica della composizione (specie) del team.
    Restituisce una lista di archetipi statici.
    """
    archetypes = []
    species = set(s.lower() for s in species_list)
    
    if "torkoal" in species or "pelipper" in species or "politoed" in species or "ninetales" in species:
        archetypes.append("Weather")
    
    if "farigiraf" in species or "indeedee" in species or "indeedeef" in species:
        if "armarouge" in species or "ursalunabloodmoon" in species or "ursaluna" in species:
            archetypes.append("Trick Room")
            
    if "tornadus" in species or "whimsicott" in species or "talonflame" in species or "murkrow" in species:
        archetypes.append("Tailwind")
        
    if "dondozo" in species and "tatsugiri" in species:
        archetypes.append("Dondozo")
        
    if "psyspam" in species or ("indeedee" in species and "armarouge" in species):
        archetypes.append("Psyspam")
        
    if not archetypes:
        archetypes.append("Balance")
        
    return archetypes

def get_match_team_archetypes(team: MatchTeamV2, session) -> list[str]:
    match = team.match
    if not match or not match.turns:
        return []
        
    N = len(match.turns)
    if N == 0:
        return []
        
    variant = team.variant
    if not variant:
        return []
        
    set_ids = set(tvb.build_id for tvb in variant.builds if tvb.build_id)
    
    # Variabili metriche
    weather_setters_in_team = 0
    weather_name = ""
    team_weathers = set()
    boost_stages = 0
    team_set_trickroom = False
    team_set_tailwind = False
    
    for turn in match.turns:
        for action in turn.actions:
            tags = action.raw_tags
            if tags and isinstance(tags, dict):
                # 1. METEO DINAMICO (Attribution)
                if "weather" in tags:
                    tag_str_lower = str(tags["weather"]).lower()
                    if "[upkeep]" not in tag_str_lower and "none" not in tag_str_lower and "clearskies" not in tag_str_lower:
                        w_val = str(tags["weather"]).replace("'", "").replace("[", "").replace("]", "")
                        current_weather = w_val.split(",")[0].strip() if "," in w_val else w_val
                        
                        if action.actor_build_id in set_ids:
                            team_weathers.add(current_weather)
                        else:
                            if f"[of] {team.player_slot}" in tag_str_lower:
                                team_weathers.add(current_weather)
                            elif action.details and f"[of] {team.player_slot}" in action.details.lower():
                                team_weathers.add(current_weather)
                                
                # 2. SETUP SWEEP (Attribution)
                if "boost" in tags:
                    for evt in tags["boost"]:
                        if len(evt) >= 1 and evt[0].startswith(team.player_slot):
                            try:
                                boost_stages += int(evt[2]) if len(evt) >= 3 else 1
                            except ValueError:
                                boost_stages += 1
                
                if "setboost" in tags:
                    for evt in tags["setboost"]:
                        if len(evt) >= 1 and evt[0].startswith(team.player_slot):
                            boost_stages += 2
                            
                # 3. TRICK ROOM e TAILWIND (Attribution)
                if "fieldstart" in tags:
                    for evt in tags["fieldstart"]:
                        evt_str = str(evt).lower()
                        if "trick room" in evt_str:
                            if action.actor_build_id in set_ids or f"[of] {team.player_slot}" in evt_str:
                                team_set_trickroom = True
                                
                if "sidestart" in tags:
                    for evt in tags["sidestart"]:
                        evt_str = str(evt).lower()
                        if "tailwind" in evt_str:
                            if action.actor_build_id in set_ids or f"[of] {team.player_slot}" in evt_str or f"['{team.player_slot}" in evt_str:
                                team_set_tailwind = True
                
    assigned_match_archetypes = []
    
    if team_set_trickroom:
        assigned_match_archetypes.append("Trick Room")
    if boost_stages >= 2:
        assigned_match_archetypes.append("Setup Sweep")
    for w in team_weathers:
        assigned_match_archetypes.append(f"{w} Team" if w else "Weather Team")
    if team_set_tailwind:
        assigned_match_archetypes.append("Tailwind Offense")
    
    if not assigned_match_archetypes and N >= 8:
        assigned_match_archetypes.append("Balance")
        
    if not assigned_match_archetypes:
        assigned_match_archetypes.append("Unclassified")
        
    return assigned_match_archetypes

def analizza_archetipo_team(species_list: list[str], lista_match_ids: list[int], session) -> str:
    """
    Analizza i replay di una squadra e la sua composizione, restituendo una 
    stringa HTML con gli archetipi Statici in azzurro e Dinamici in giallo.
    """
    # 1. Calcolo Statico
    static_archs = analizza_archetipo_statico(species_list)
    static_str = ", ".join(static_archs)
    
    # 2. Calcolo Dinamico
    archetipi_weights = defaultdict(float)
    valid_matches = 0
    
    stmt = select(MatchTeamV2).options(
        joinedload(MatchTeamV2.match).joinedload(MatchV2.turns).joinedload(TurnV2.actions),
        joinedload(MatchTeamV2.variant).joinedload(TeamVariantV2.builds)
    ).filter(MatchTeamV2.id.in_(lista_match_ids))
    
    teams_db = session.scalars(stmt).unique().all()
    
    for team in teams_db:
        assigned_match_archetypes = get_match_team_archetypes(team, session)
        if not assigned_match_archetypes:
            continue
            
        valid_matches += 1
        
        weight = 1.0 / len(assigned_match_archetypes)
        for arch in assigned_match_archetypes:
            archetipi_weights[arch] += weight
            
    parts = []
    if valid_matches > 0:
        sorted_archs = sorted(archetipi_weights.items(), key=lambda x: x[1], reverse=True)
        for arch, weight in sorted_archs:
            pct = round((weight / valid_matches) * 100)
            if pct > 0:
                arch_clean = arch.replace(" ", "")
                parts.append(f"{arch_clean}:{pct}%")
            
    if not parts:
        parts.append("Unclassified:100%")
        
    dynamic_str = " ".join(parts)
    
    html = f"<span style='color: deepskyblue;'>{static_str}</span> <br> <span style='color: #FFD700;'>{dynamic_str}</span>"
    return html

def generate_unrecognized_actions_log(session) -> str:
    log_lines = []
    
    matches = session.query(MatchV2).all()
    for m in matches:
        for t in m.turns:
            for a in t.actions:
                tags = a.raw_tags
                if not tags or not isinstance(tags, dict):
                    continue
                
                if "weather" in tags:
                    tag_lower = str(tags["weather"]).lower()
                    if "[upkeep]" not in tag_lower and "none" not in tag_lower and "clearskies" not in tag_lower:
                        if not ("[of] p1" in tag_lower or "[of] p2" in tag_lower):
                            if not a.actor_build_id:
                                log_lines.append(f"Match {m.id} | Turn {t.turn_number} | Unrecognized Weather: {tags['weather']} | Action Details: {a.details}")
                                
                if "sidestart" in tags:
                    for evt in tags["sidestart"]:
                        evt_lower = str(evt).lower()
                        if "tailwind" in evt_lower:
                            if not (evt_lower.startswith("p1") or evt_lower.startswith("p2") or evt_lower.startswith("['p1") or evt_lower.startswith("['p2")):
                                if not a.actor_build_id:
                                    log_lines.append(f"Match {m.id} | Turn {t.turn_number} | Unrecognized Tailwind: {evt} | Action Details: {a.details}")
                                    
                if "fieldstart" in tags:
                    for evt in tags["fieldstart"]:
                        evt_lower = str(evt).lower()
                        if "trick room" in evt_lower:
                            if not ("[of] p1" in evt_lower or "[of] p2" in evt_lower):
                                if not a.actor_build_id:
                                    log_lines.append(f"Match {m.id} | Turn {t.turn_number} | Unrecognized Trick Room: {evt} | Action Details: {a.details}")
                                    
                if "boost" in tags:
                    for evt in tags["boost"]:
                        evt_lower = str(evt).lower()
                        if not (evt_lower.startswith("p1") or evt_lower.startswith("p2") or evt_lower.startswith("['p1") or evt_lower.startswith("['p2")):
                            log_lines.append(f"Match {m.id} | Turn {t.turn_number} | Unrecognized Boost: {evt} | Action Details: {a.details}")
    
    if not log_lines:
        return "Nessuna azione non riconosciuta trovata."
        
    return "LOG AZIONI NON RICONOSCIUTE\n" + "="*40 + "\n" + "\n".join(log_lines)
