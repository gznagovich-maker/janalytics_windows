"""
role_detector.py
================
Modulo di logica pura per classificare il ruolo di un Pokémon nel VGC.
Analizza mosse e base stats per determinare Offensive / Defensive / Disruptive.
"""

from typing import List, Optional

# Mosse che indicano un ruolo di supporto/disruption
DISRUPTIVE_MOVES = {
    "Tailwind", "Trick Room", "Follow Me", "Rage Powder", "Helping Hand",
    "Fake Out", "Icy Wind", "Spore", "Thunder Wave", "Will-O-Wisp",
    "Yawn", "Encore", "Taunt", "Ally Switch", "Wide Guard", "Quick Guard",
    "Heal Pulse", "Pollen Puff", "Life Dew", "Coaching", "Decorate",
    "Parting Shot", "U-turn", "Volt Switch", "Haze", "Clear Smog",
    "Electroweb", "Snarl", "Charm", "Feather Dance", "Scary Face",
    "After You", "Instruct", "Safeguard", "Mist", "Imprison",
    "Disable", "Torment", "Confuse Ray", "Flatter", "Swagger",
    "Light Screen", "Reflect", "Aurora Veil",
}

# Mosse che non contano come offensive per il ruolo (status/supporto puro)
STATUS_MOVES_CATEGORY = "Status"


def detect_role(
    species_name: str,
    moves: List[str],
    base_stats: Optional[dict] = None
) -> str:
    """
    Classifica un Pokémon come 'Offensive', 'Defensive', o 'Disruptive'.

    Logica prioritaria:
    1. Se ≥2 mosse sono nella lista DISRUPTIVE_MOVES → Disruptive
    2. Se non ci sono base stats, fallback su analisi mosse:
       - Se tutte le mosse sono Status → Disruptive
       - Altrimenti → Offensive (default)
    3. Con base stats:
       - offensive_power = max(atk, spa)
       - defensive_power = (hp + def + spd) / 3
       - Se offensive_power > defensive_power + 10 → Offensive
       - Altrimenti → Defensive

    Args:
        species_name: Nome della specie (non usato direttamente, per logging)
        moves: Lista nomi mosse (1-4 stringhe)
        base_stats: Dict opzionale con chiavi 'hp','atk','def','spa','spd','spe'

    Returns:
        "Offensive" | "Defensive" | "Disruptive"
    """
    # Conta mosse disruptive
    disruptive_count = sum(1 for m in moves if m in DISRUPTIVE_MOVES)

    if disruptive_count >= 2:
        return "Disruptive"

    # Se non abbiamo base stats, usiamo un'euristica sulle mosse
    if not base_stats:
        if disruptive_count >= 1 and len(moves) <= 2:
            return "Disruptive"
        return "Offensive"

    # Analisi base stats
    atk = base_stats.get("atk", 0) or 0
    spa = base_stats.get("spa", 0) or 0
    hp = base_stats.get("hp", 0) or 0
    def_ = base_stats.get("def", 0) or 0
    spd = base_stats.get("spd", 0) or 0
    spe = base_stats.get("spe", 0) or 0

    offensive_power = max(atk, spa)
    defensive_power = (hp + def_ + spd) / 3.0

    # Pokémon con alta velocità e alto attacco tendono ad essere offensivi
    if offensive_power > defensive_power + 10:
        return "Offensive"

    # Se le stats sono bilanciate ma ha mosse disruptive → Disruptive
    if disruptive_count >= 1:
        return "Disruptive"

    return "Defensive"


def get_role_icon(role: str) -> str:
    """Restituisce l'icona unicode per il ruolo."""
    return {
        "Offensive": "⚔",
        "Defensive": "🛡",
        "Disruptive": "⚡",
    }.get(role, "?")


def get_role_color(role: str) -> str:
    """Restituisce il colore hex per il badge del ruolo."""
    return {
        "Offensive": "#B04545",   # Rosso caldo
        "Defensive": "#3D6B50",   # Verde scuro
        "Disruptive": "#C49A3C",  # Bronzo/oro
    }.get(role, "#5E6575")


ROLES = ["Offensive", "Defensive", "Disruptive"]


def cycle_role(current_role: str) -> str:
    """Cicla al prossimo ruolo nella sequenza."""
    try:
        idx = ROLES.index(current_role)
        return ROLES[(idx + 1) % len(ROLES)]
    except ValueError:
        return ROLES[0]
