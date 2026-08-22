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
                # Usiamo la stringa species per l'ID in questo caso, o l'ID vero e proprio
                poke_name = poke.get("species")
                current_hp[poke_name] = 100.0
                current_boosts[poke_name] = {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}
                
        # Scorrimento turni
        for turn in self.match_data.get("turns", []):
            turn_num = turn.get("turn_number")
            
            p1_active = []
            p2_active = []
            
            for action in turn.get("actions", []):
                board = action.get("board_state", {})
                
                # Tracciamo chi c'è in campo alla fine dell'azione
                p1_active = [board.get("p1a", {}).get("name"), board.get("p1b", {}).get("name")]
                p2_active = [board.get("p2a", {}).get("name"), board.get("p2b", {}).get("name")]
                
                tags = action.get("tags", {})
                # Applica danni / cure
                if "damage_pct" in tags:
                    target = action.get("target")
                    if target in current_hp:
                        current_hp[target] = max(0.0, current_hp[target] - tags["damage_pct"])
                if "heal_pct" in tags:
                    target = action.get("target")
                    if target in current_hp:
                        current_hp[target] = min(100.0, current_hp[target] + tags["heal_pct"])
                        
                # Applica stat boost/drop (esempio)
                # Nei tags potremmo avere "stat_boost": {"atk": 1} 
                if "stat_boost" in tags:
                    target = action.get("target")
                    boost_dict = tags["stat_boost"]
                    if target in current_boosts:
                        for stat, val in boost_dict.items():
                            if stat in current_boosts[target]:
                                current_boosts[target][stat] = max(-6, min(6, current_boosts[target][stat] + val))
                if "stat_unboost" in tags:
                    target = action.get("target")
                    boost_dict = tags["stat_unboost"]
                    if target in current_boosts:
                        for stat, val in boost_dict.items():
                            if stat in current_boosts[target]:
                                current_boosts[target][stat] = max(-6, min(6, current_boosts[target][stat] - val))
                                
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
            
            # Euristiche per il momentum (semplificate)
            speed_adv = 1.0 if turn.get("p1_tailwind") else ( -1.0 if turn.get("p2_tailwind") else 0.0 )
            hazard_ctrl = 0.0 # Richiederebbe tracciamento hazards
            type_matchup = 1.0 # Neutrale di base, richiederebbe type chart incrociata
            
            momentum = calculate_momentum_index(w_diff / 200.0, speed_adv, hazard_ctrl, type_matchup)
            
            turns.append(turn_num)
            delta_hp_series.append(w_diff)
            momentum_series.append(momentum)
            
        return {
            "turns": turns,
            "delta_hp": delta_hp_series,
            "momentum": momentum_series
        }
