"""
migrate_sqlite_to_pg.py
=======================
Script one-shot per migrare i dati V2 da SQLite a PostgreSQL.

Migra SOLO le tabelle V2 (esclude le tabelle V1 legacy):
  pokemon_species_v2, tag, move_v2, ability_v2, item_v2,
  trainer_v2, pokemon_build, pokemon_build_move, pokemon_build_stats,
  team_variant_v2, team_variant_build, match_v2, match_team_v2,
  turn_v2, turn_board_state, turn_field_condition, turn_action_v2,
  action_effect_v2, action_effect_stat_change,
  match_summary_v2, match_brought, match_archetype

Uso:
  python database/migrate_sqlite_to_pg.py [percorso_sqlite.db]

Prerequisiti:
  - PostgreSQL in esecuzione e raggiungibile tramite DATABASE_URL nel .env
  - Tabelle PG già create (tramite init_db() o alembic upgrade head)
"""

import sys
import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional

# ──────────────────────────────────────────────────────────────────────────────
# Setup path
# ──────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT = str(Path(__file__).parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.connection import SessionLocal, engine, init_db, test_connection
from database.models_v2 import (
    PokemonSpeciesV2, Tag, MoveV2, AbilityV2, ItemV2, TrainerV2,
    PokemonBuild, PokemonBuildMove, PokemonBuildStats,
    TeamVariantV2, TeamVariantBuild,
    MatchV2, MatchTeamV2,
    TurnV2, TurnBoardState, TurnFieldCondition,
    TurnActionV2, ActionEffectV2, ActionEffectStatChange,
    MatchSummaryV2, MatchBrought, MatchArchetype,
)


def _parse_json_safe(val: Any) -> Optional[dict]:
    """Deserializza JSON stringa → dict. Ritorna None se non è JSON valido."""
    if val is None:
        return None
    if isinstance(val, dict):
        return val
    try:
        result = json.loads(val)
        return result if isinstance(result, (dict, list)) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _parse_timestamp(val: Any) -> Optional[datetime]:
    """Converte timestamp SQLite (stringa o None) in datetime UTC-aware."""
    if not val:
        return None
    try:
        if isinstance(val, datetime):
            return val.replace(tzinfo=timezone.utc) if val.tzinfo is None else val
        dt = datetime.fromisoformat(str(val))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except (ValueError, TypeError):
        return None


def migrate(sqlite_path: str) -> None:
    print("=" * 60)
    print("JAnalytics — Migrazione SQLite → PostgreSQL (V2 only)")
    print("=" * 60)

    if not os.path.exists(sqlite_path):
        print(f"[ERRORE] File SQLite non trovato: {sqlite_path}")
        sys.exit(1)

    # Verifica connessione PG
    if not test_connection():
        print("[ERRORE] Impossibile connettersi a PostgreSQL. Verifica il .env e che il server sia in esecuzione.")
        sys.exit(1)

    print(f"[OK] Connessione PostgreSQL attiva")
    print(f"[OK] Sorgente SQLite: {sqlite_path}")

    # Crea le tabelle PG se non esistono
    print("\n[1/11] Creazione schema PostgreSQL...")
    init_db()
    print("       Schema pronto.")

    # Connessione SQLite
    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row
    c = src.cursor()

    pg = SessionLocal()
    BATCH_SIZE = 500

    # ──────────────────────────────────────────────────────────────────────────
    # Helper per batch insert con progress
    # ──────────────────────────────────────────────────────────────────────────
    def batch_commit(objects: list, label: str) -> int:
        for i in range(0, len(objects), BATCH_SIZE):
            batch = objects[i:i + BATCH_SIZE]
            pg.bulk_save_objects(batch)
            pg.flush()
        pg.commit()
        print(f"       ✓ {len(objects)} righe migrate")
        return len(objects)

    total_migrated = 0

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Tabelle master data (nessuna FK esterna)
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[2/11] pokemon_species_v2 ...")
    c.execute("SELECT * FROM pokemon_species_v2")
    rows = c.fetchall()

    # Ordina: prima le specie senza parent (base_species_id vuoto/None),
    # poi quelle con parent — rispetta il vincolo FK self-referenziale
    base_rows = [r for r in rows if not r["base_species_id"]]
    child_rows = [r for r in rows if r["base_species_id"]]

    def _make_species(r) -> PokemonSpeciesV2:
        return PokemonSpeciesV2(
            id=r["id"],
            num=r["num"],
            name=r["name"],
            base_species_id=r["base_species_id"] or None,  # stringa vuota → None
            forme=r["forme"] or None,
            type1=r["type1"],
            type2=r["type2"],
            bst_hp=r["bst_hp"], bst_atk=r["bst_atk"], bst_def=r["bst_def"],
            bst_spa=r["bst_spa"], bst_spd=r["bst_spd"], bst_spe=r["bst_spe"],
            abilities_json=_parse_json_safe(r["abilities_json"]),
            learnset_json=_parse_json_safe(r["learnset_json"]),
            sprite_url=r["sprite_url"],
            artwork_url=r["artwork_url"],
        )

    # Inserisci prima le specie base
    base_objects = [_make_species(r) for r in base_rows if not pg.get(PokemonSpeciesV2, r["id"])]
    if base_objects:
        for i in range(0, len(base_objects), BATCH_SIZE):
            pg.bulk_save_objects(base_objects[i:i + BATCH_SIZE])
            pg.flush()
        pg.commit()
    print(f"       Species base: {len(base_objects)} righe")

    # Poi le forme derivate
    child_objects = [_make_species(r) for r in child_rows if not pg.get(PokemonSpeciesV2, r["id"])]
    if child_objects:
        for i in range(0, len(child_objects), BATCH_SIZE):
            pg.bulk_save_objects(child_objects[i:i + BATCH_SIZE])
            pg.flush()
        pg.commit()
    print(f"       Forme/Varianti: {len(child_objects)} righe")
    total_migrated += len(base_objects) + len(child_objects)


    print("\n[3/11] tag, move_v2, ability_v2, item_v2 ...")
    # Tags
    c.execute("SELECT * FROM tag")
    tags = c.fetchall()
    tag_objects = [
        Tag(id=r["id"], category=r["category"], name=r["name"])
        for r in tags if not pg.get(Tag, r["id"])
    ]
    if tag_objects:
        pg.bulk_save_objects(tag_objects)
        pg.commit()
    print(f"       ✓ tag: {len(tag_objects)} righe")

    # move_v2
    c.execute("SELECT * FROM move_v2")
    move_objects = [
        MoveV2(id=r["id"], name=r["name"], type=r["type"], category=r["category"],
               base_power=r["base_power"], accuracy=r["accuracy"],
               priority=r["priority"], pp=r["pp"],
               target=r["target"], short_desc=r["short_desc"])
        for r in c.fetchall() if not pg.get(MoveV2, r["id"])
    ]
    if move_objects:
        pg.bulk_save_objects(move_objects)
        pg.commit()
    print(f"       ✓ move_v2: {len(move_objects)} righe")

    # ability_v2
    c.execute("SELECT * FROM ability_v2")
    ability_objects = [
        AbilityV2(id=r["id"], name=r["name"], short_desc=r["short_desc"])
        for r in c.fetchall() if not pg.get(AbilityV2, r["id"])
    ]
    if ability_objects:
        pg.bulk_save_objects(ability_objects)
        pg.commit()
    print(f"       ✓ ability_v2: {len(ability_objects)} righe")

    # item_v2
    c.execute("SELECT * FROM item_v2")
    item_objects = [
        ItemV2(id=r["id"], name=r["name"], short_desc=r["short_desc"], sprite_url=r["sprite_url"])
        for r in c.fetchall() if not pg.get(ItemV2, r["id"])
    ]
    if item_objects:
        pg.bulk_save_objects(item_objects)
        pg.commit()
    print(f"       ✓ item_v2: {len(item_objects)} righe")

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Trainer
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[4/11] trainer_v2 ...")
    c.execute("SELECT * FROM trainer_v2")
    objects = [
        TrainerV2(id=r["id"], rating=r["rating"])
        for r in c.fetchall() if not pg.get(TrainerV2, r["id"])
    ]
    total_migrated += batch_commit(objects, "trainer_v2")

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Pokemon Build
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[5/11] pokemon_build + pokemon_build_move + pokemon_build_stats ...")
    c.execute("SELECT * FROM pokemon_build")
    builds = c.fetchall()
    build_objects = [
        PokemonBuild(
            id=r["id"], species_id=r["species_id"], ability_id=r["ability_id"],
            item_id=r["item_id"], tera_type=r["tera_type"], nature=r["nature"],
        )
        for r in builds if not pg.get(PokemonBuild, r["id"])
    ]
    if build_objects:
        pg.bulk_save_objects(build_objects)
        pg.commit()
    print(f"       ✓ pokemon_build: {len(build_objects)} righe")

    # pokemon_build_move
    c.execute("SELECT * FROM pokemon_build_move")
    existing_bm = set(
        (r.build_id, r.move_id) for r in pg.query(PokemonBuildMove.build_id, PokemonBuildMove.move_id).all()
    )
    bm_objects = [
        PokemonBuildMove(build_id=r["build_id"], move_id=r["move_id"], slot=r["slot"])
        for r in c.fetchall()
        if (r["build_id"], r["move_id"]) not in existing_bm
    ]
    if bm_objects:
        pg.bulk_save_objects(bm_objects)
        pg.commit()
    print(f"       ✓ pokemon_build_move: {len(bm_objects)} righe")

    # pokemon_build_stats
    c.execute("SELECT * FROM pokemon_build_stats")
    existing_bs = set(r.id for r in pg.query(PokemonBuildStats.id).all())
    bs_objects = [
        PokemonBuildStats(
            id=r["id"], build_id=r["build_id"],
            ev_hp=r["ev_hp"], ev_atk=r["ev_atk"], ev_def=r["ev_def"],
            ev_spa=r["ev_spa"], ev_spd=r["ev_spd"], ev_spe=r["ev_spe"],
            iv_hp=r["iv_hp"], iv_atk=r["iv_atk"], iv_def=r["iv_def"],
            iv_spa=r["iv_spa"], iv_spd=r["iv_spd"], iv_spe=r["iv_spe"],
            observed_count=r["observed_count"],
        )
        for r in c.fetchall() if r["id"] not in existing_bs
    ]
    if bs_objects:
        pg.bulk_save_objects(bs_objects)
        pg.commit()
    print(f"       ✓ pokemon_build_stats: {len(bs_objects)} righe")

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Team Variant
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[6/11] team_variant_v2 + team_variant_build ...")
    c.execute("SELECT * FROM team_variant_v2")
    tv_objects = [
        TeamVariantV2(id=r["id"], size=r["size"])
        for r in c.fetchall() if not pg.get(TeamVariantV2, r["id"])
    ]
    if tv_objects:
        pg.bulk_save_objects(tv_objects)
        pg.commit()
    print(f"       ✓ team_variant_v2: {len(tv_objects)} righe")

    c.execute("SELECT * FROM team_variant_build")
    existing_tvb = set(
        (r.team_variant_id, r.build_id)
        for r in pg.query(TeamVariantBuild.team_variant_id, TeamVariantBuild.build_id).all()
    )
    tvb_objects = [
        TeamVariantBuild(team_variant_id=r["team_variant_id"], build_id=r["build_id"], slot=r["slot"])
        for r in c.fetchall()
        if (r["team_variant_id"], r["build_id"]) not in existing_tvb
    ]
    if tvb_objects:
        pg.bulk_save_objects(tvb_objects)
        pg.commit()
    print(f"       ✓ team_variant_build: {len(tvb_objects)} righe")

    # ──────────────────────────────────────────────────────────────────────────
    # 5. Match
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[7/11] match_v2 + match_team_v2 ...")
    c.execute("SELECT * FROM match_v2")
    match_objects = [
        MatchV2(
            id=r["id"], format=r["format"],
            timestamp=_parse_timestamp(r["timestamp"]),
            winner_id=r["winner_id"],
        )
        for r in c.fetchall() if not pg.get(MatchV2, r["id"])
    ]
    if match_objects:
        pg.bulk_save_objects(match_objects)
        pg.commit()
    print(f"       ✓ match_v2: {len(match_objects)} righe")

    c.execute("SELECT * FROM match_team_v2")
    existing_mt = set(r.id for r in pg.query(MatchTeamV2.id).all())
    mt_objects = [
        MatchTeamV2(
            id=r["id"], match_id=r["match_id"], trainer_id=r["trainer_id"],
            player_slot=r["player_slot"], team_variant_id=r["team_variant_id"],
        )
        for r in c.fetchall() if r["id"] not in existing_mt
    ]
    if mt_objects:
        pg.bulk_save_objects(mt_objects)
        pg.commit()
    print(f"       ✓ match_team_v2: {len(mt_objects)} righe")

    # ──────────────────────────────────────────────────────────────────────────
    # 6. Turn
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[8/11] turn_v2 + turn_board_state + turn_field_condition ...")
    c.execute("SELECT * FROM turn_v2")
    existing_turns = set(r.id for r in pg.query(TurnV2.id).all())
    turn_objects = [
        TurnV2(id=r["id"], match_id=r["match_id"], turn_number=r["turn_number"])
        for r in c.fetchall() if r["id"] not in existing_turns
    ]
    if turn_objects:
        pg.bulk_save_objects(turn_objects)
        pg.commit()
    print(f"       ✓ turn_v2: {len(turn_objects)} righe")

    c.execute("SELECT * FROM turn_board_state")
    existing_bs_ids = set(r.id for r in pg.query(TurnBoardState.id).all())
    bs_rows = [
        TurnBoardState(
            id=r["id"], turn_id=r["turn_id"],
            p1a_build_id=r["p1a_build_id"], p1b_build_id=r["p1b_build_id"],
            p2a_build_id=r["p2a_build_id"], p2b_build_id=r["p2b_build_id"],
        )
        for r in c.fetchall() if r["id"] not in existing_bs_ids
    ]
    if bs_rows:
        pg.bulk_save_objects(bs_rows)
        pg.commit()
    print(f"       ✓ turn_board_state: {len(bs_rows)} righe")

    c.execute("SELECT * FROM turn_field_condition")
    existing_tfc = set(r.id for r in pg.query(TurnFieldCondition.id).all())
    tfc_rows = [
        TurnFieldCondition(
            id=r["id"], turn_id=r["turn_id"], side=r["side"],
            tag_id=r["tag_id"], is_active=bool(r["is_active"]),
        )
        for r in c.fetchall() if r["id"] not in existing_tfc
    ]
    if tfc_rows:
        pg.bulk_save_objects(tfc_rows)
        pg.commit()
    print(f"       ✓ turn_field_condition: {len(tfc_rows)} righe")

    # ──────────────────────────────────────────────────────────────────────────
    # 7. Turn Actions
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[9/11] turn_action_v2 ...")
    c.execute("SELECT * FROM turn_action_v2")
    existing_ta = set(r.id for r in pg.query(TurnActionV2.id).all())
    ta_objects = []
    for r in c.fetchall():
        if r["id"] in existing_ta:
            continue
        # raw_tags: SQLite ha stringa JSON, PG vuole dict/None
        raw_tags_val = _parse_json_safe(r["raw_tags"])
        ta_objects.append(TurnActionV2(
            id=r["id"], turn_id=r["turn_id"],
            action_order=r["action_order"], action_type=r["action_type"],
            actor_build_id=r["actor_build_id"], target_build_id=r["target_build_id"],
            move_id=r["move_id"], details=r["details"],
            raw_tags=raw_tags_val,
        ))
    total_migrated += batch_commit(ta_objects, "turn_action_v2")

    # ──────────────────────────────────────────────────────────────────────────
    # 8. Action Effects
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[10/11] action_effect_v2 + action_effect_stat_change ...")
    c.execute("SELECT * FROM action_effect_v2")
    existing_ae = set(r.id for r in pg.query(ActionEffectV2.id).all())
    ae_objects = [
        ActionEffectV2(
            id=r["id"], turn_action_id=r["turn_action_id"],
            target_build_id=r["target_build_id"],
            damage_percent=float(r["damage_percent"] or 0.0),
            status_inflicted=r["status_inflicted"],
            is_crit=bool(r["is_crit"]),
            effectiveness=r["effectiveness"],
            ability_activated=r["ability_activated"],
            item_consumed=r["item_consumed"],
            is_protected=bool(r["is_protected"]),
        )
        for r in c.fetchall() if r["id"] not in existing_ae
    ]
    if ae_objects:
        for i in range(0, len(ae_objects), BATCH_SIZE):
            pg.bulk_save_objects(ae_objects[i:i+BATCH_SIZE])
            pg.flush()
        pg.commit()
    print(f"       ✓ action_effect_v2: {len(ae_objects)} righe")

    c.execute("SELECT * FROM action_effect_stat_change")
    existing_sc = set(r.id for r in pg.query(ActionEffectStatChange.id).all())
    sc_objects = [
        ActionEffectStatChange(id=r["id"], effect_id=r["effect_id"], stat=r["stat"], stages=r["stages"])
        for r in c.fetchall() if r["id"] not in existing_sc
    ]
    if sc_objects:
        pg.bulk_save_objects(sc_objects)
        pg.commit()
    print(f"       ✓ action_effect_stat_change: {len(sc_objects)} righe")

    # ──────────────────────────────────────────────────────────────────────────
    # 9. Match Summary
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[11/11] match_summary_v2 + match_brought + match_archetype ...")
    c.execute("SELECT * FROM match_summary_v2")
    existing_ms = set(r.id for r in pg.query(MatchSummaryV2.id).all())
    ms_objects = [
        MatchSummaryV2(id=r["id"], match_id=r["match_id"], total_turns=r["total_turns"])
        for r in c.fetchall() if r["id"] not in existing_ms
    ]
    if ms_objects:
        pg.bulk_save_objects(ms_objects)
        pg.commit()
    print(f"       ✓ match_summary_v2: {len(ms_objects)} righe")

    c.execute("SELECT * FROM match_brought")
    existing_mb = set(r.id for r in pg.query(MatchBrought.id).all())
    mb_objects = [
        MatchBrought(id=r["id"], summary_id=r["summary_id"], player_slot=r["player_slot"], build_id=r["build_id"])
        for r in c.fetchall() if r["id"] not in existing_mb
    ]
    if mb_objects:
        pg.bulk_save_objects(mb_objects)
        pg.commit()
    print(f"       ✓ match_brought: {len(mb_objects)} righe")

    c.execute("SELECT * FROM match_archetype")
    existing_ma = set(r.id for r in pg.query(MatchArchetype.id).all())
    ma_objects = [
        MatchArchetype(
            id=r["id"], summary_id=r["summary_id"], player_slot=r["player_slot"],
            tag_id=r["tag_id"], weight=float(r["weight"] or 1.0),
        )
        for r in c.fetchall() if r["id"] not in existing_ma
    ]
    if ma_objects:
        pg.bulk_save_objects(ma_objects)
        pg.commit()
    print(f"       ✓ match_archetype: {len(ma_objects)} righe")

    src.close()
    pg.close()

    print("\n" + "=" * 60)
    print("✅ Migrazione completata con successo!")
    print("=" * 60)
    print("\nProssimi passi consigliati:")
    print("  1. ANALYZE nel DB PG: SELECT schemaname, tablename FROM pg_stat_user_tables;")
    print("  2. Esegui: VACUUM ANALYZE;")
    print("  3. Testa le query con EXPLAIN ANALYZE")
    print("  4. Refresh materialized views: python database/materialized_views.py --refresh")


if __name__ == "__main__":
    sqlite_path = sys.argv[1] if len(sys.argv) > 1 else "vgc_replays.db"
    migrate(sqlite_path)
