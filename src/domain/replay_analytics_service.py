import json
from typing import Dict, List, Any
from src.domain.math_models import calculate_weighted_hp_diff, calculate_momentum_index

class ReplayAnalyticsService:
    """
    Servizio per il calcolo delle metriche matematiche su un singolo match.
    Implementa un logica di event-sourcing per ricostruire lo stato turn-by-turn.
    """
    
    def __init__(self, match_data: Dict[str, Any]):
        self.match_data = match_data
        
    def generate_turn_series(self) -> Dict[str, List[float]]:
        """
        Scorre i turni e le azioni del match e produce le serie storiche per i grafici.
        Restituisce un dizionario con:
        - 'turns': Lista dei numeri di turno
        - 'delta_hp': Lista del Differenziale HP Ponderato per turno
        - 'momentum': Lista dell'Indice di Vantaggio per turno
        """
        turns = []
        delta_hp_series = []
        momentum_series = []
        
        # Stato temporaneo (Event Sourcing)
        # HP in percentuale, partono da 100 per chi è in campo
        current_hp = {}
        # Boost in stadi
        current_boosts = {}
        
        # Inizializziamo tutti i pokemon conosciuti a 100 HP e 0 boost
        teams = self.match_data.get("teams", {})
        for p_slot, team in teams.items():
            for poke in team.get("pokemon", []):
                poke_name = poke.get("species")
                if poke_name:
                    current_hp[poke_name] = 100.0
                    current_boosts[poke_name] = {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}
                
        # Scorrimento turni
        for turn in self.match_data.get("turns", []):
            turn_num = turn.get("turn_number")
            
            # BUG FIX: board_state è a livello di TURNO, non di azione
            board = turn.get("board_state", {})
            
            p1_active = [board.get("p1a", {}).get("species"), board.get("p1b", {}).get("species")]
            p2_active = [board.get("p2a", {}).get("species"), board.get("p2b", {}).get("species")]
            
            for action in turn.get("actions", []):
                # Applica danni / cure tramite effects
                for eff in action.get("effects", []):
                    target = eff.get("target")
                    if not target or target == "?":
                        continue
                    damage = eff.get("damage_pct") or 0
                    try:
                        damage = float(damage)
                    except (TypeError, ValueError):
                        damage = 0
                    if damage != 0 and target in current_hp:
                        current_hp[target] = max(0.0, min(100.0, current_hp[target] - damage))
                        
                # Applica stat boost/drop dai raw_tags
                # DB format: {"boost": [["p1a: Ogerpon", "atk", "1"]], "unboost": [...]}
                # Ogni elemento è già una lista di stringhe, NON una stringa da splittare
                raw_tags = action.get("raw_tags", {})
                if isinstance(raw_tags, dict):
                    # BUG FIX: chiavi senza trattino ("boost" non "-boost")
                    for tag_key, sign in (("boost", 1), ("unboost", -1)):
                        boost_list = raw_tags.get(tag_key, [])
                        if not isinstance(boost_list, list):
                            continue
                        for ev in boost_list:
                            # ev è già una lista: ["p1a: Ogerpon", "atk", "1"]
                            if not isinstance(ev, list) or len(ev) < 3:
                                continue
                            slot_str = ev[0].split(":")[0].strip()
                            target_species = board.get(slot_str, {}).get("species")
                            stat = ev[1].strip().lower()
                            try:
                                val = int(ev[2]) * sign
                                if target_species in current_boosts and stat in current_boosts[target_species]:
                                    current_boosts[target_species][stat] = max(-6, min(6, current_boosts[target_species][stat] + val))
                            except (ValueError, TypeError):
                                pass
                                
                    # Gestione faint
                    faint_list = raw_tags.get("faint", [])
                    if isinstance(faint_list, list):
                        for ev in faint_list:
                            if isinstance(ev, list) and ev:
                                slot_str = ev[0].split(":")[0].strip()
                                target_species = board.get(slot_str, {}).get("species")
                                if target_species and target_species in current_hp:
                                    current_hp[target_species] = 0.0
                                
            # Calcolo metriche di fine turno
            hp_p1_total = sum(current_hp.get(p, 0.0) for p in p1_active if p and p != "Vuoto")
            hp_p2_total = sum(current_hp.get(p, 0.0) for p in p2_active if p and p != "Vuoto")
            
            boosts_p1 = {}
            for p in p1_active:
                if p and p != "Vuoto":
                    for s, v in current_boosts.get(p, {}).items():
                        boosts_p1[s] = boosts_p1.get(s, 0) + v
                        
            boosts_p2 = {}
            for p in p2_active:
                if p and p != "Vuoto":
                    for s, v in current_boosts.get(p, {}).items():
                        boosts_p2[s] = boosts_p2.get(s, 0) + v
                        
            w_diff = calculate_weighted_hp_diff(hp_p1_total, hp_p2_total, boosts_p1, boosts_p2)
            
            # BUG FIX: tailwind è in field_conditions, non direttamente nel turno
            fc = turn.get("field_conditions", {})
            p1_tw = fc.get("tailwind_p1", False) or fc.get("tailwind", False)
            p2_tw = fc.get("tailwind_p2", False)
            speed_adv = 1.0 if p1_tw else (-1.0 if p2_tw else 0.0)
            hazard_ctrl = 0.0
            type_matchup = 1.0
            
            momentum = calculate_momentum_index(w_diff / 200.0, speed_adv, hazard_ctrl, type_matchup)
            
            turns.append(turn_num)
            delta_hp_series.append(w_diff)
            momentum_series.append(momentum)
            
        return {
            "turns": turns,
            "delta_hp": delta_hp_series,
            "momentum": momentum_series
        }
