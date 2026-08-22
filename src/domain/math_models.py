"""
Modulo per i Modelli Matematici e le Metriche Avanzate
Contiene le funzioni per il calcolo delle metriche descritte nell'Analisi Quantitativa.
"""

from typing import Dict, List, Optional
import math

# 1. Analisi Temporale: Snapshot di Stato
def calculate_weighted_hp(hp_percent: float, stat_boosts: Dict[str, int]) -> float:
    """
    Calcola l'HP effettivo (potenziale) di un Pokémon basandosi sui suoi modificatori di statistica (boost).
    
    Spiegazione Matematica:
    Gli HP crudi non riflettono il potenziale offensivo/difensivo. Viene introdotto un moltiplicatore
    M(s) basato sulle fasi (da -6 a +6) delle statistiche chiave (es. atk, def, spa, spd, spe).
    M(s) = (2+s)/2 per s >= 0
    M(s) = 2/(2+|s|) per s < 0
    
    Esempio:
    Un Pokémon al 50% HP ma con +2 in Attacco (s=2) avrà un HP Ponderato di 50 * (4/2) = 100.
    In questo modo, riflette un'effettiva pericolosità maggiore rispetto a uno al 50% senza boost.
    """
    multiplier = 1.0
    for stat, s in stat_boosts.items():
        if stat in ['atk', 'def', 'spa', 'spd', 'spe']:
            if s >= 0:
                m_s = (2 + s) / 2
            else:
                m_s = 2 / (2 + abs(s))
            multiplier += (m_s - 1.0)
    
    # Evitiamo valori negativi se i drop sono troppi
    multiplier = max(0.2, multiplier)
    return hp_percent * multiplier

def calculate_weighted_hp_diff(p1_active_hp: float, p2_active_hp: float, 
                               p1_boosts: Dict[str, int], p2_boosts: Dict[str, int]) -> float:
    """
    Calcola il Differenziale HP Ponderato tra due Pokémon in campo.
    """
    w_hp1 = calculate_weighted_hp(p1_active_hp, p1_boosts)
    w_hp2 = calculate_weighted_hp(p2_active_hp, p2_boosts)
    return w_hp1 - w_hp2


# 2. Matrice Decisionale: Analisi Azione-Reazione
def calculate_expected_value(d_base: float, p_hit: float = 1.0, p_crit: float = 0.0416) -> float:
    """
    Calcola il Valore Atteso (Expected Value, EV) del danno di una mossa.
    
    Spiegazione Matematica:
    L'albero delle decisioni modella il danno atteso E[D] pesando probabilità di hit e crit.
    E[D] = P_hit * ((1 - P_crit) * D_base + P_crit * 1.5 * D_base)
    
    Esempio:
    Mossa con 100 danni base (D_base=100), 80% precisione (P_hit=0.8) e 4.16% crit base.
    E[D] = 0.8 * ((1 - 0.0416)*100 + 0.0416 * 150) = 0.8 * (95.84 + 6.24) = 81.66 danni attesi.
    """
    return p_hit * ((1 - p_crit) * d_base + p_crit * 1.5 * d_base)

def calculate_payoff_matrix(ev_action_p1: float, ev_action_p2: float) -> float:
    """
    Calcola il Payoff (Π_P1) per il giocatore 1 in un gioco a somma zero, 
    usando la differenza dei Valori Attesi.
    """
    return ev_action_p1 - ev_action_p2


# 3. Indice di Vantaggio (Momentum)
def calculate_momentum_index(delta_hp_norm: float, speed_advantage: float, 
                             hazard_control: float, type_matchup: float,
                             weights: tuple = (1.0, 0.5, 0.2, 0.5)) -> float:
    """
    Calcola l'Indice di Vantaggio (Momentum, Iv(t)) come funzione composita euristica.
    
    Spiegazione Matematica:
    Assegna uno scalare al giocatore 1. Definiamo un vettore di pesi w.
    I_v(t) = w1*DeltaHP_norm(t) + w2*S(t) + w3*H(t) + w4*T(t)
    - S(t): 1 se P1 è più veloce, -1 altrimenti.
    - H(t): HP_P2 - HP_P1 (danno atteso dalle hazard sul lato).
    - T(t): Moltiplicatore efficacia mossa STAB.
    
    Esempio:
    Un giocatore in vantaggio di +20% HP (delta_hp=0.2), con vantaggio di speed (S=1),
    senza hazard (H=0) e type neutro (T=1) avrà un momentum alto e positivo, dominando 
    la "scacchiera".
    """
    w1, w2, w3, w4 = weights
    iv = (w1 * delta_hp_norm) + (w2 * speed_advantage) + (w3 * hazard_control) + (w4 * type_matchup)
    
    return max(-10.0, min(10.0, iv))


# 4. Modello Matematico di Efficacia dello Sweeper
def calculate_sweeper_effectiveness(k: int, t_a: int, d_t: float, hp_opp_avg: float) -> float:
    """
    Valutazione aggregata della reale utilità di uno sweeper nel team.
    
    Spiegazione Matematica:
    SE = (K / T_a) * (D_T / HP_opp_avg)
    Dove:
    - K: K.O. totali ottenuti
    - T_a: Turni attivi in campo
    - D_T: Danno inflitto totale
    - HP_opp_avg: Media degli HP massimi dei nemici affrontati
    
    Esempio:
    Un Flutter Mane ottiene 3 KO (K=3) in 4 turni (T_a=4) infliggendo 400 danni totali (D_T=400)
    contro nemici con media 150 HP max (HP_opp_avg=150).
    SE = (3/4) * (400/150) = 0.75 * 2.66 = 2.0. Un SE > 1.5 indica una pulizia estremamente rapida
    ed efficiente senza spreco di turni di setup.
    """
    if t_a == 0 or hp_opp_avg == 0:
        return 0.0
    return (k / t_a) * (d_t / hp_opp_avg)


# 5. Indice di Pressione del Campo (FPI)
def calculate_field_pressure_index(turn_hazard_advantage: List[float], turn_weather_advantage: List[float]) -> float:
    """
    Indica la gestione degli effetti sul campo nel tempo.
    
    Spiegazione Matematica:
    FPI = Sum(H_t + W_t) / T
    Dove H_t è il vantaggio Hazard e W_t il vantaggio meteo al turno t.
    
    Esempio:
    Su 10 turni, se per 8 turni abbiamo piazzato le Stealth Rock (vantaggio +1 ogni turno), 
    FPI = 8/10 = 0.8. Significa che l'80% del tempo l'avversario ha subito pressione ambientale.
    """
    t_total = len(turn_hazard_advantage)
    if t_total == 0:
        return 0.0
    
    total_pressure = sum(h + w for h, w in zip(turn_hazard_advantage, turn_weather_advantage))
    return total_pressure / t_total

