"""
hash_utils.py
=============
Funzioni canoniche per il calcolo deterministico degli hash SHA-256
di PokemonBuild e TeamVariant.

Regole canonicali:
  - Tutti i testi vengono normalizzati in Showdown ID format (solo [a-z0-9])
  - Le mosse vengono ORDINATE ALFABETICAMENTE (l'ordine slot non è identità)
  - I build_id del team vengono ORDINATI ALFABETICAMENTE
  - EV/IV NON fanno parte dell'identità della build (approccio "fuzzy")
    → lo stesso Miraidon Life Orb con spread diversi = stesso build_id
    → gli spread vengono registrati in pokemon_build_stats (1-to-many)
  - JSON serializzato con sort_keys=True e senza spazi
"""

import re
import hashlib
import json
from typing import Optional, List


def to_id(text: str) -> str:
    """Normalizza una stringa in Showdown ID format: solo [a-z0-9]."""
    if not text:
        return ""
    return re.sub(r'[^a-z0-9]', '', text.lower())


def compute_build_hash(
    species: str,
    ability: str,
    item: str,
    tera_type: Optional[str],
    nature: str,
    moves: List[str],
) -> str:
    """
    Calcola l'hash SHA-256 deterministico per una PokemonBuild.

    L'identità della build è data da: specie + abilità + strumento +
    tera type + natura + moveset (ordinato alfabeticamente).

    EV e IV NON sono inclusi: due istanze dello stesso Pokémon con spread
    diversi condividono lo stesso build_id. Il dettaglio dello spread viene
    registrato nella tabella separata PokemonBuildStats (1-to-many).

    Due build con le stesse mosse in ordine diverso generano lo STESSO hash
    perché le mosse vengono ordinate alfabeticamente prima del calcolo.

    Returns:
        str: Hash SHA-256 hex (64 caratteri).
    """
    canonical = {
        "species":   to_id(species),
        "ability":   to_id(ability),
        "item":      to_id(item or ""),
        "tera_type": to_id(tera_type or ""),
        "nature":    to_id(nature or "hardy"),
        # Mosse ordinate: protect+hydropump+icebeam = icebeam+hydropump+protect
        "moves":     sorted([to_id(m) for m in moves if m]),
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def compute_team_hash(build_ids: List[str]) -> str:
    """
    Calcola l'hash SHA-256 deterministico per un TeamVariant.

    Un team è definito dalla sua composizione, NON dall'ordine delle build.
    I build_id (già SHA-256) vengono ordinati alfabeticamente prima del calcolo,
    garantendo che lo stesso insieme di 6 build generi sempre lo stesso team_id.

    Args:
        build_ids: Lista di ID (SHA-256) delle 6 build che compongono il team.

    Returns:
        str: Hash SHA-256 hex (64 caratteri).
    """
    canonical = sorted(build_ids)
    payload = ",".join(canonical)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------
# Backward-compat: le vecchie funzioni MD5 (da NON usare in nuovo codice)
# Mantenute solo per la fase di migrazione.
# ---------------------------------------------------------------------------

def _legacy_hash_pokemon_set_md5(species: str, ability: str, item: str,
                                   tera_type: Optional[str], nature: str,
                                   moves: List[str]) -> str:
    """DEPRECATED — solo per lookup durante la migrazione dati."""
    s_moves = ",".join([to_id(m) for m in moves]) if moves else ""
    data = f"{to_id(species)}_{to_id(ability)}_{to_id(item)}_{tera_type}_{nature}_{s_moves}"
    return hashlib.md5(data.encode('utf-8')).hexdigest()


def _legacy_hash_team_variant_md5(set_ids: List[str]) -> str:
    """DEPRECATED — solo per lookup durante la migrazione dati."""
    return hashlib.md5(",".join(sorted(set_ids)).encode('utf-8')).hexdigest()
