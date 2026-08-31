"""
seed_tags.py
============
Script di seeding del sistema Tag per JAnalytics V2.

Popola le tabelle:
  - tag            (da TAGS in tag_definitions.py)
  - move_tag       (da MOVE_TAG_MAP)
  - ability_tag    (da ABILITY_TAG_MAP)
  - item_tag       (da ITEM_TAG_MAP)

Può essere eseguito più volte in modo idempotente (INSERT OR IGNORE).

Uso:
    python -m database.seed_tags
    # oppure importato da migrate_v1_to_v2.py
"""

import json
import os
import re
from typing import Dict, Optional

from database.connection import SessionLocal
from database.models_v2 import Tag, MoveTag, AbilityTag, ItemTag, MoveV2, AbilityV2, ItemV2
from database.tag_definitions import TAGS, MOVE_TAG_MAP, ABILITY_TAG_MAP, ITEM_TAG_MAP


def to_id(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'[^a-z0-9]', '', text.lower())


def seed_tags(session) -> Dict[str, int]:
    """
    Inserisce tutti i tag definiti in TAGS nel database.
    Restituisce un dizionario name → id per lookup rapido.
    """
    print("[SEED] Inserimento Tag...")
    tag_name_to_id: Dict[str, int] = {}

    for category, names in TAGS.items():
        for name in names:
            existing = session.query(Tag).filter_by(name=name).first()
            if not existing:
                tag = Tag(category=category, name=name)
                session.add(tag)
                session.flush()
                tag_name_to_id[name] = tag.id
            else:
                tag_name_to_id[name] = existing.id

    session.commit()
    print(f"[SEED] {len(tag_name_to_id)} tag disponibili.")
    return tag_name_to_id


def seed_move_tags(session, tag_name_to_id: Dict[str, int]):
    """
    Assegna i tag alle mosse presenti in move_v2.
    Legge moves.json per i dati di base (tipo, categoria, priorità)
    e applica MOVE_TAG_MAP per i tag semantici aggiuntivi.
    """
    print("[SEED] Seeding move_tag...")

    # Cerca moves.json nella root del progetto
    moves_json_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "moves.json"
    )
    moves_data: Dict = {}
    if os.path.exists(moves_json_path):
        with open(moves_json_path, "r", encoding="utf-8") as f:
            moves_data = json.load(f)
    else:
        print(f"[SEED] WARN: moves.json non trovato in {moves_json_path}")

    count = 0
    moves_in_db = session.query(MoveV2).all()
    move_ids_in_db = {m.id for m in moves_in_db}

    for move_id in move_ids_in_db:
        tags_to_assign = set()

        # 1. Dall'archivio statico MOVE_TAG_MAP
        for map_key, map_tags in MOVE_TAG_MAP.items():
            if to_id(map_key) == move_id:
                tags_to_assign.update(map_tags)
                break

        # 2. Da moves.json: inferisci tag da proprietà strutturate
        move_json = moves_data.get(move_id, {})
        if move_json:
            priority = move_json.get("priority", 0)
            if priority and int(priority) > 0:
                tags_to_assign.add("priority")

            target = move_json.get("target", "")
            # adjacentFoes = spread (hits both opponents)
            if target in ("allAdjacentFoes", "allAdjacent"):
                tags_to_assign.add("spread")

        # 3. Inserisci le associazioni
        for tag_name in tags_to_assign:
            tag_id = tag_name_to_id.get(tag_name)
            if tag_id is None:
                # Cerca per nome normalizzato
                tag = session.query(Tag).filter_by(name=tag_name).first()
                if tag:
                    tag_id = tag.id
                else:
                    continue

            existing = session.query(MoveTag).filter_by(
                move_id=move_id, tag_id=tag_id
            ).first()
            if not existing:
                session.add(MoveTag(move_id=move_id, tag_id=tag_id))
                count += 1

    session.commit()
    print(f"[SEED] {count} move_tag inseriti.")


def seed_ability_tags(session, tag_name_to_id: Dict[str, int]):
    """Assegna tag alle abilità presenti in ability_v2."""
    print("[SEED] Seeding ability_tag...")
    count = 0

    abilities_in_db = session.query(AbilityV2).all()
    ability_ids_in_db = {a.id for a in abilities_in_db}

    for ability_id in ability_ids_in_db:
        tags_to_assign = set()

        for map_key, map_tags in ABILITY_TAG_MAP.items():
            if to_id(map_key) == ability_id:
                tags_to_assign.update(map_tags)
                break

        for tag_name in tags_to_assign:
            tag_id = tag_name_to_id.get(tag_name)
            if tag_id is None:
                tag = session.query(Tag).filter_by(name=tag_name).first()
                if tag:
                    tag_id = tag.id
                else:
                    continue

            existing = session.query(AbilityTag).filter_by(
                ability_id=ability_id, tag_id=tag_id
            ).first()
            if not existing:
                session.add(AbilityTag(ability_id=ability_id, tag_id=tag_id))
                count += 1

    session.commit()
    print(f"[SEED] {count} ability_tag inseriti.")


def seed_item_tags(session, tag_name_to_id: Dict[str, int]):
    """Assegna tag agli strumenti presenti in item_v2."""
    print("[SEED] Seeding item_tag...")
    count = 0

    items_in_db = session.query(ItemV2).all()
    item_ids_in_db = {i.id for i in items_in_db}

    for item_id in item_ids_in_db:
        tags_to_assign = set()

        for map_key, map_tags in ITEM_TAG_MAP.items():
            if to_id(map_key) == item_id:
                tags_to_assign.update(map_tags)
                break

        for tag_name in tags_to_assign:
            tag_id = tag_name_to_id.get(tag_name)
            if tag_id is None:
                tag = session.query(Tag).filter_by(name=tag_name).first()
                if tag:
                    tag_id = tag.id
                else:
                    continue

            existing = session.query(ItemTag).filter_by(
                item_id=item_id, tag_id=tag_id
            ).first()
            if not existing:
                session.add(ItemTag(item_id=item_id, tag_id=tag_id))
                count += 1

    session.commit()
    print(f"[SEED] {count} item_tag inseriti.")


def run_full_seed():
    """Esegui il seeding completo in sequenza."""
    from database.connection import Base, engine
    from database.models_v2 import (
        Tag, MoveTag, AbilityTag, ItemTag, MoveV2, AbilityV2, ItemV2,
        PokemonSpeciesV2, PokemonBuild, PokemonBuildMove,
        TeamVariantV2, TeamVariantBuild, TrainerV2, MatchV2, MatchTeamV2,
        TurnV2, TurnBoardState, TurnFieldCondition,
        TurnActionV2, ActionEffectV2, ActionEffectStatChange,
        MatchSummaryV2, MatchBrought, MatchArchetype
    )

    print("[SEED] Creazione tabelle V2...")
    Base.metadata.create_all(bind=engine)
    print("[SEED] Tabelle create (o già esistenti).")

    session = SessionLocal()
    try:
        tag_map = seed_tags(session)
        seed_move_tags(session, tag_map)
        seed_ability_tags(session, tag_map)
        seed_item_tags(session, tag_map)
        print("[SEED] ✅ Seeding completato.")
    except Exception as e:
        session.rollback()
        print(f"[SEED] ❌ Errore durante il seeding: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    run_full_seed()
