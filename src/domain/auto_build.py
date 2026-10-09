"""
auto_build.py
=============
Logica pura per generare spread EV e nature coerenti con il ruolo rilevato.
Le build generate sono sempre sbloccate e modificabili dall'utente.

La classificazione fisico / speciale / mixed si basa sulle mosse effettive
del Pokémon (categoria Physical/Special dal DB), non solo sulle base stats.
"""

from typing import Dict, Any, Optional, List


def _classify_moves(moves: List[str]) -> str:
    """
    Analizza le mosse del Pokémon dal DB e restituisce:
        'physical' — ha solo mosse fisiche offensive
        'special'  — ha solo mosse speciali offensive
        'mixed'    — ha sia mosse fisiche che speciali offensive
        'unknown'  — nessuna mossa offensiva trovata (fallback su base stats)
    """
    if not moves:
        return "unknown"

    try:
        from database.connection import SessionLocal
        from database.models_v2 import MoveV2

        has_physical = False
        has_special = False

        with SessionLocal() as session:
            for move_name in moves:
                if not move_name:
                    continue
                # Cerca per name (case insensitive) o per id
                move_obj = session.query(MoveV2).filter(
                    (MoveV2.name == move_name) | (MoveV2.id == move_name)
                ).first()
                if not move_obj:
                    continue
                if move_obj.category == "Physical" and (move_obj.base_power or 0) > 0:
                    has_physical = True
                elif move_obj.category == "Special" and (move_obj.base_power or 0) > 0:
                    has_special = True

        if has_physical and has_special:
            return "mixed"
        elif has_physical:
            return "physical"
        elif has_special:
            return "special"
        else:
            return "unknown"
    except Exception:
        return "unknown"


def generate_auto_build(
    role: str,
    base_stats: Optional[dict] = None,
    moves: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Genera una spread di base coerente con il ruolo rilevato.

    La classificazione offensiva segue questa logica:
        1. Analizza le mosse dal DB per determinare Physical / Special / Mixed.
        2. Se non riesce a classificare, fallback sulle base stats (Atk vs SpA).

    Regole (scala Champions 0-32, budget 66 punti):
        Offensive (Physical):
            - 32 Atk, 32 Spe, 2 HP
            - Natura: Jolly (+Spe, -SpA)

        Offensive (Special):
            - 32 SpA, 32 Spe, 2 HP
            - Natura: Timid (+Spe, -Atk)

        Offensive (Mixed):
            - 22 Atk, 22 SpA, 22 Spe
            - Natura: Naive (+Spe, -SpD) o Hasty (+Spe, -Def)

        Defensive / Disruptive:
            - 32 HP, 32 nel miglior stat difensivo (Def o SpD), 2 nell'altro
            - Natura: Impish (se Def > SpD) o Careful (se SpD >= Def)

    Args:
        role: "Offensive", "Defensive", o "Disruptive"
        base_stats: Dict con chiavi 'hp','atk','def','spa','spd','spe'
        moves: Lista dei nomi delle mosse del Pokémon

    Returns:
        Dict con chiavi "evs" (dict stat→champions_points) e "nature" (str)
    """
    if role == "Offensive":
        # Classifica in base alle mosse reali
        move_class = _classify_moves(moves or [])

        if move_class == "mixed":
            # Mixed attacker: distribuisci equamente
            return {
                "evs": {"Atk": 22, "SpA": 22, "Spe": 22},
                "nature": "Naive"   # +Spe -SpD
            }
        elif move_class == "physical":
            return {
                "evs": {"Atk": 32, "Spe": 32, "HP": 2},
                "nature": "Jolly"
            }
        elif move_class == "special":
            return {
                "evs": {"SpA": 32, "Spe": 32, "HP": 2},
                "nature": "Timid"
            }
        else:
            # Fallback: classifica in base alle base stats
            if not base_stats:
                return {
                    "evs": {"Atk": 32, "Spe": 32, "HP": 2},
                    "nature": "Jolly"
                }
            atk = base_stats.get("atk", 0) or 0
            spa = base_stats.get("spa", 0) or 0
            if atk >= spa:
                return {
                    "evs": {"Atk": 32, "Spe": 32, "HP": 2},
                    "nature": "Jolly"
                }
            else:
                return {
                    "evs": {"SpA": 32, "Spe": 32, "HP": 2},
                    "nature": "Timid"
                }
    else:
        # Defensive o Disruptive → build difensiva
        if not base_stats:
            return {
                "evs": {"HP": 32, "Def": 32, "SpD": 2},
                "nature": "Impish"
            }
        def_ = base_stats.get("def", 0) or 0
        spd = base_stats.get("spd", 0) or 0
        if def_ >= spd:
            return {
                "evs": {"HP": 32, "Def": 32, "SpD": 2},
                "nature": "Impish"
            }
        else:
            return {
                "evs": {"HP": 32, "SpD": 32, "Def": 2},
                "nature": "Careful"
            }


def has_custom_spread(member: Dict[str, Any]) -> bool:
    """
    Controlla se un membro del team ha già una spread personalizzata.
    Restituisce True se le EVs sono non-vuote e non tutte a 0.
    """
    opts = member.get("options", {})
    evs = opts.get("evs", {})
    if not evs:
        return False
    return any(v > 0 for v in evs.values())
