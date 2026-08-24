import json
from collections import Counter, defaultdict
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from database.models import Team, Match, Turn, TurnAction

def analizza_archetipo_statico():
    """
    Funzione futura: deriverà l'archetipo da un'analisi statica della composizione 
    del team (mosse, abilità, statistiche base note) prima dell'inizio del match.
    (Lasciata vuota per implementazioni future come richiesto dal design).
    """
    pass

def get_match_team_archetypes(team: Team) -> list[str]:
    match = team.match
    if not match or not match.turns:
        return []
        
    N = len(match.turns)
    if N == 0:
        return []
        
    build_ids = {pb.id for pb in team.pokemon_builds}
    
    # Variabili metriche
    weather_setters_in_team = 0
    weather_name = ""
    team_weathers = set()
    
    boost_stages = 0
    
    team_set_trickroom = False
    team_set_tailwind = False
    
    for turn in match.turns:
        if team.player_slot == "p1" and turn.p1_tailwind:
            team_set_tailwind = True
        elif team.player_slot == "p2" and turn.p2_tailwind:
            team_set_tailwind = True
            
        for action in turn.actions:
            if action.action_type in ("switch", "drag"):
                if action.actor_build_id in build_ids:
                    pass # Non più usato per il balance, ma lo lasciamo in caso
            
            # Parsing dei tags
            if action.tags and isinstance(action.tags, dict):
                # 1. METEO DINAMICO (Attribution)
                if "weather" in action.tags:
                    tag_str_lower = str(action.tags["weather"]).lower()
                    if "[upkeep]" not in tag_str_lower and "none" not in tag_str_lower and "clearskies" not in tag_str_lower:
                        w_val = str(action.tags["weather"]).replace("'", "").replace("[", "").replace("]", "")
                        current_weather = w_val.split(",")[0].strip() if "," in w_val else w_val
                        
                        # Verifica CHI ha settato il meteo
                        if action.actor_build_id in build_ids:
                            team_weathers.add(current_weather)
                        else:
                            if f"[of] {team.player_slot}" in tag_str_lower:
                                team_weathers.add(current_weather)
                            elif action.details and f"[of] {team.player_slot}" in action.details.lower():
                                team_weathers.add(current_weather)
                                
                # 2. SETUP SWEEP (Attribution)
                if "boost" in action.tags:
                    for evt in action.tags["boost"]:
                        # evt[0] contiene ad es. 'p1a: Garchomp'
                        if len(evt) >= 1 and evt[0].startswith(team.player_slot):
                            try:
                                boost_stages += int(evt[2]) if len(evt) >= 3 else 1
                            except ValueError:
                                boost_stages += 1
                
                if "setboost" in action.tags:
                    for evt in action.tags["setboost"]:
                        if len(evt) >= 1 and evt[0].startswith(team.player_slot):
                            boost_stages += 2
                            
                # 3. TRICK ROOM e TAILWIND (Attribution da fieldstart/sideend)
                if "fieldstart" in action.tags:
                    for evt in action.tags["fieldstart"]:
                        evt_str = str(evt).lower()
                        if "trick room" in evt_str:
                            if action.actor_build_id in build_ids or f"[of] {team.player_slot}" in evt_str:
                                team_set_trickroom = True
                                
                if "sidestart" in action.tags:
                    for evt in action.tags["sidestart"]:
                        evt_str = str(evt).lower()
                        if "tailwind" in evt_str:
                            if action.actor_build_id in build_ids or f"[of] {team.player_slot}" in evt_str or f"['{team.player_slot}" in evt_str:
                                team_set_tailwind = True
                
    # Gerarchia di classificazione rimossa per favorire archetipi frazionati simultanei
    assigned_match_archetypes = []
    
    if team_set_trickroom:
        assigned_match_archetypes.append("Trick Room")
    if boost_stages >= 2:
        assigned_match_archetypes.append("Setup Sweep")
    for w in team_weathers:
        assigned_match_archetypes.append(f"{w} Team" if w else "Weather Team")
    if team_set_tailwind:
        assigned_match_archetypes.append("Tailwind Offense")
    
    # Balance se non ha attivato altri archetipi aggressivi e il match è durato tanto
    if not assigned_match_archetypes and N >= 8:
        assigned_match_archetypes.append("Balance")
        
    if not assigned_match_archetypes:
        assigned_match_archetypes.append("Unclassified")
        
    return assigned_match_archetypes

def analizza_archetipo_team(team_id: str, lista_match_ids: list[int], session) -> str:
    """
    Analizza i replay di una squadra usando Event Sourcing Puro.
    
    team_id: Stringa identificativa della variante in analisi (es. "Variante 1").
    lista_match_ids: Lista di interi corrispondenti agli ID dei Team nel database 
                     (nella nostra architettura, ogni Team rappresenta la singola 
                     apparizione di una squadra in un match).
    """
    archetipi_weights = defaultdict(float)
    valid_matches = 0
    
    # Query ottimizzata SQLAlchemy 2.0 (Eager loading in bulk)
    stmt = select(Team).options(
        joinedload(Team.match).joinedload(Match.turns).joinedload(Turn.actions),
        joinedload(Team.pokemon_builds)
    ).filter(Team.id.in_(lista_match_ids))
    
    teams_db = session.scalars(stmt).unique().all()
    
    for team in teams_db:
        assigned_match_archetypes = get_match_team_archetypes(team)
        if not assigned_match_archetypes:
            continue
            
        valid_matches += 1
        
        # Ponderazione: un team può giocare 50% setup e 50% rain nello stesso match
        weight = 1.0 / len(assigned_match_archetypes)
        for arch in assigned_match_archetypes:
            archetipi_weights[arch] += weight
            
    # Formattazione Output Richiesta
    if valid_matches == 0:
        return f"Team {team_id} : Nessun Dato"
        
    parts = []
    
    # Ordinamento decrescente per peso
    sorted_archs = sorted(archetipi_weights.items(), key=lambda x: x[1], reverse=True)
    for arch, weight in sorted_archs:
        pct = round((weight / valid_matches) * 100)
        if pct > 0:
            arch_clean = arch.replace(" ", "")
            parts.append(f"{arch_clean}:{pct}%")
            
    if not parts:
        parts.append("Unclassified:100%")
        
    return f"Team {team_id} : " + " ".join(parts)


def generate_unrecognized_actions_log(session) -> str:
    """
    Scansiona tutto il database per estrarre azioni (weather, setup, tailwind, trickroom) 
    che non possono essere attribuite a P1 o P2.
    """
    log_lines = []
    
    matches = session.query(Match).all()
    for m in matches:
        for t in m.turns:
            for a in t.actions:
                if not a.tags or not isinstance(a.tags, dict):
                    continue
                
                # Check weather
                if "weather" in a.tags:
                    tag_lower = str(a.tags["weather"]).lower()
                    if "[upkeep]" not in tag_lower and "none" not in tag_lower and "clearskies" not in tag_lower:
                        if not ("[of] p1" in tag_lower or "[of] p2" in tag_lower):
                            if not a.actor_build_id:
                                log_lines.append(f"Match {m.id} | Turn {t.turn_number} | Unrecognized Weather: {a.tags['weather']} | Action Details: {a.details}")
                                
                # Check sidestart
                if "sidestart" in a.tags:
                    for evt in a.tags["sidestart"]:
                        evt_lower = str(evt).lower()
                        if "tailwind" in evt_lower:
                            if not (evt_lower.startswith("p1") or evt_lower.startswith("p2") or evt_lower.startswith("['p1") or evt_lower.startswith("['p2")):
                                if not a.actor_build_id:
                                    log_lines.append(f"Match {m.id} | Turn {t.turn_number} | Unrecognized Tailwind: {evt} | Action Details: {a.details}")
                                    
                # Check fieldstart (Trick Room)
                if "fieldstart" in a.tags:
                    for evt in a.tags["fieldstart"]:
                        evt_lower = str(evt).lower()
                        if "trick room" in evt_lower:
                            if not ("[of] p1" in evt_lower or "[of] p2" in evt_lower):
                                if not a.actor_build_id:
                                    log_lines.append(f"Match {m.id} | Turn {t.turn_number} | Unrecognized Trick Room: {evt} | Action Details: {a.details}")
                                    
                # Check boost
                if "boost" in a.tags:
                    for evt in a.tags["boost"]:
                        evt_lower = str(evt).lower()
                        if not (evt_lower.startswith("p1") or evt_lower.startswith("p2") or evt_lower.startswith("['p1") or evt_lower.startswith("['p2")):
                            log_lines.append(f"Match {m.id} | Turn {t.turn_number} | Unrecognized Boost: {evt} | Action Details: {a.details}")
    
    if not log_lines:
        return "Nessuna azione non riconosciuta trovata."
        
    return "LOG AZIONI NON RICONOSCIUTE\n" + "="*40 + "\n" + "\n".join(log_lines)

