"""
migrate_v1_to_v2.py
===================
Script di migrazione dati dallo schema V1 (models.py) allo schema V2 (models_v2.py).

Pipeline:
  A. Crea tabelle V2
  B. Seed tag
  C. Migra PokemonSpecies (JSON -> colonne scalari)
  D. Migra Ability, Item, Move (V1 -> V2)
  E. Migra PokemonSet -> PokemonBuild (MD5 -> SHA-256, CSV mosse -> junction)
  F. Migra TeamVariant -> TeamVariantV2 (JSON -> junction)
  G. Migra Trainer -> TrainerV2
  H. Migra Match -> MatchV2 + MatchTeamV2
  I. Migra Turn -> TurnV2 + TurnBoardState + TurnFieldCondition
  J. Migra TurnAction -> TurnActionV2 + ActionEffectV2 + ActionEffectStatChange
  K. Migra MatchSummary -> MatchSummaryV2 + MatchBrought + MatchArchetype

Uso:
    python -m database.migrate_v1_to_v2 [--dry-run]
"""

import sys
import json
import re
import argparse
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from database.connection import SessionLocal, Base, engine
from database.hash_utils import compute_build_hash, compute_team_hash, to_id
from database.seed_tags import run_full_seed, seed_tags as _seed_tags
from database.tag_definitions import TAGS

# V1 models (vecchi)
from database.models import (
    PokemonSpecies as V1Species,
    Ability as V1Ability,
    Item as V1Item,
    Move as V1Move,
    PokemonSet as V1PokemonSet,
    TeamVariant as V1TeamVariant,
    Trainer as V1Trainer,
    Match as V1Match,
    MatchTeam as V1MatchTeam,
    Turn as V1Turn,
    TurnAction as V1TurnAction,
    ActionEffect as V1ActionEffect,
    MatchSummary as V1MatchSummary,
)

# V2 models (nuovi)
from database.models_v2 import (
    PokemonSpeciesV2, AbilityV2, ItemV2, MoveV2,
    PokemonBuild, PokemonBuildMove, PokemonBuildStats,
    TeamVariantV2, TeamVariantBuild,
    TrainerV2, MatchV2, MatchTeamV2,
    TurnV2, TurnBoardState, TurnFieldCondition,
    TurnActionV2, ActionEffectV2, ActionEffectStatChange,
    MatchSummaryV2, MatchBrought, MatchArchetype,
    Tag,
)

# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

FIELD_CONDITION_TAG_NAMES = {
    # field (entrambi i lati)
    "trick_room":    "trickroom",
    "gravity":       "gravity",
    # p1/p2
    "p1_tailwind":   "tailwind",
    "p2_tailwind":   "tailwind",
    "p1_reflect":    "reflect",
    "p2_reflect":    "reflect",
    "p1_lightscreen":"lightscreen",
    "p2_lightscreen":"lightscreen",
    "p1_aurora_veil":"auroraveil",
    "p2_aurora_veil":"auroraveil",
}


def get_side_from_key(key: str) -> str:
    """Ricava il lato ('field', 'p1', 'p2') dalla chiave del field condition."""
    if key.startswith("p1_"):
        return "p1"
    if key.startswith("p2_"):
        return "p2"
    return "field"


def safe_json_loads(val) -> dict:
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return {}
    return {}


# ──────────────────────────────────────────────────────────────────────────────
# FASE C -- Migrazione PokemonSpecies
# ──────────────────────────────────────────────────────────────────────────────

def migrate_species(session: Session) -> int:
    print("[MIG] Fase C: Migrazione PokemonSpecies...")
    v1_species = session.query(V1Species).all()
    count = 0

    for s in v1_species:
        if session.query(PokemonSpeciesV2).filter_by(id=s.id).first():
            continue

        # Parsare types da JSON list ['Fire', 'Water']
        types = []
        if s.types:
            if isinstance(s.types, list):
                types = s.types
            elif isinstance(s.types, str):
                try:
                    types = json.loads(s.types)
                except Exception:
                    types = [s.types]

        type1 = types[0] if len(types) > 0 else None
        type2 = types[1] if len(types) > 1 else None

        # Parsare base_stats da JSON dict
        stats = {}
        if s.base_stats:
            if isinstance(s.base_stats, dict):
                stats = s.base_stats
            elif isinstance(s.base_stats, str):
                try:
                    stats = json.loads(s.base_stats)
                except Exception:
                    stats = {}

        new_species = PokemonSpeciesV2(
            id=s.id,
            num=s.num or 0,
            name=s.name or s.id,
            base_species_id=None,  # set dopo per self-ref
            forme=s.forme,
            type1=type1,
            type2=type2,
            bst_hp=stats.get("hp", 0),
            bst_atk=stats.get("atk", 0),
            bst_def=stats.get("def", 0),
            bst_spa=stats.get("spa", 0),
            bst_spd=stats.get("spd", 0),
            bst_spe=stats.get("spe", 0),
            sprite_url=s.sprite_url,
            artwork_url=s.artwork_url,
        )
        session.add(new_species)
        count += 1

    session.flush()

    # Seconda passata: aggiorna base_species_id (self-ref)
    for s in v1_species:
        if s.base_species and s.base_species != s.id:
            v2 = session.query(PokemonSpeciesV2).filter_by(id=s.id).first()
            if v2:
                v2.base_species_id = s.base_species if session.query(
                    PokemonSpeciesV2).filter_by(id=s.base_species).first() else None

    session.commit()
    print(f"[MIG] {count} specie migrate.")
    return count


# ──────────────────────────────────────────────────────────────────────────────
# FASE D -- Migrazione Ability, Item, Move
# ──────────────────────────────────────────────────────────────────────────────

def migrate_abilities(session: Session) -> int:
    print("[MIG] Fase D.1: Migrazione Abilità...")
    v1_abilities = session.query(V1Ability).all()
    count = 0
    for a in v1_abilities:
        if session.query(AbilityV2).filter_by(id=a.id).first():
            continue
        session.add(AbilityV2(id=a.id, name=a.name, short_desc=a.short_desc))
        count += 1
    session.commit()
    print(f"[MIG] {count} abilità migrate.")
    return count


def migrate_items(session: Session) -> int:
    print("[MIG] Fase D.2: Migrazione Strumenti...")
    v1_items = session.query(V1Item).all()
    count = 0
    for i in v1_items:
        if session.query(ItemV2).filter_by(id=i.id).first():
            continue
        session.add(ItemV2(
            id=i.id, name=i.name,
            short_desc=i.short_desc or i.effect,
            sprite_url=i.sprite_url
        ))
        count += 1
    session.commit()
    print(f"[MIG] {count} strumenti migrati.")
    return count


def migrate_moves(session: Session) -> int:
    print("[MIG] Fase D.3: Migrazione Mosse...")
    v1_moves = session.query(V1Move).all()
    count = 0
    for m in v1_moves:
        if session.query(MoveV2).filter_by(id=m.id).first():
            continue
        session.add(MoveV2(
            id=m.id, name=m.name, type=m.type,
            category=m.category, base_power=m.base_power,
            accuracy=m.accuracy, priority=m.priority,
            short_desc=m.short_desc,
        ))
        count += 1
    session.commit()
    print(f"[MIG] {count} mosse migrate.")
    return count


# ──────────────────────────────────────────────────────────────────────────────
# FASE E -- Migrazione PokemonSet -> PokemonBuild
# ──────────────────────────────────────────────────────────────────────────────

def migrate_builds(session: Session) -> Dict[str, str]:
    """
    Migra PokemonSet -> PokemonBuild con nuovi hash SHA-256 fuzzy (senza EV/IV).
    Gli spread EV/IV vengono salvati in PokemonBuildStats (1-to-many) con upsert.
    Restituisce il mapping old_md5 -> new_sha256.
    """
    print("[MIG] Fase E: Migrazione PokemonSet -> PokemonBuild (fuzzy)...")
    v1_sets = session.query(V1PokemonSet).all()
    old_to_new: Dict[str, str] = {}
    count = 0
    skipped = 0

    for old in v1_sets:
        moves_list = old.moves.split(',') if old.moves else []
        moves_list = [m.strip() for m in moves_list if m.strip()]

        # Hash SENZA EV/IV (fuzzy identity)
        new_id = compute_build_hash(
            species=old.species_id or "",
            ability=old.ability_id or "",
            item=old.item_id or "",
            tera_type=old.tera_type,
            nature=old.nature or "hardy",
            moves=moves_list,
        )
        old_to_new[old.id] = new_id

        build_exists = session.query(PokemonBuild).filter_by(id=new_id).first()
        if not build_exists:
            new_build = PokemonBuild(
                id=new_id,
                species_id=old.species_id if session.query(
                    PokemonSpeciesV2).filter_by(id=old.species_id).first() else None,
                ability_id=old.ability_id if old.ability_id and session.query(
                    AbilityV2).filter_by(id=old.ability_id).first() else None,
                item_id=old.item_id if old.item_id and session.query(
                    ItemV2).filter_by(id=old.item_id).first() else None,
                tera_type=old.tera_type,
                nature=old.nature or "Hardy",
            )
            session.add(new_build)
            session.flush()

            # Inserisci mosse nella junction table
            for slot_idx, move_id in enumerate(sorted(moves_list), start=1):
                if not move_id:
                    continue
                if not session.query(MoveV2).filter_by(id=move_id).first():
                    session.add(MoveV2(
                        id=move_id, name=move_id.capitalize(),
                        type="Normal", category="Status",
                        base_power=0, accuracy=100, priority=0
                    ))
                    session.flush()
                session.add(PokemonBuildMove(build_id=new_id, move_id=move_id, slot=slot_idx))

            count += 1
        else:
            skipped += 1

        # Upsert dello spread EV/IV in PokemonBuildStats
        existing_stats = session.query(PokemonBuildStats).filter_by(
            build_id=new_id,
            ev_hp=old.ev_hp, ev_atk=old.ev_atk, ev_def=old.ev_def,
            ev_spa=old.ev_spa, ev_spd=old.ev_spd, ev_spe=old.ev_spe,
            iv_hp=old.iv_hp, iv_atk=old.iv_atk, iv_def=old.iv_def,
            iv_spa=old.iv_spa, iv_spd=old.iv_spd, iv_spe=old.iv_spe,
        ).first()

        if existing_stats:
            existing_stats.observed_count += 1
        else:
            session.add(PokemonBuildStats(
                build_id=new_id,
                ev_hp=old.ev_hp, ev_atk=old.ev_atk, ev_def=old.ev_def,
                ev_spa=old.ev_spa, ev_spd=old.ev_spd, ev_spe=old.ev_spe,
                iv_hp=old.iv_hp, iv_atk=old.iv_atk, iv_def=old.iv_def,
                iv_spa=old.iv_spa, iv_spd=old.iv_spd, iv_spe=old.iv_spe,
                observed_count=1,
            ))

        if (count + skipped) % 100 == 0:
            session.flush()
            print(f"[MIG]   ... {count + skipped} build processate ({count} nuove, {skipped} duplicate)")

    session.commit()
    print(f"[MIG] {count} build nuove, {skipped} deduplicate. Mapping: {len(old_to_new)} entries.")
    return old_to_new


# ──────────────────────────────────────────────────────────────────────────────
# FASE F -- Migrazione TeamVariant -> TeamVariantV2
# ──────────────────────────────────────────────────────────────────────────────

def migrate_teams(session: Session, old_to_new_build: Dict[str, str]) -> Dict[str, str]:
    """
    Migra TeamVariant -> TeamVariantV2 + TeamVariantBuild.
    Restituisce mapping old_md5 -> new_sha256.
    """
    print("[MIG] Fase F: Migrazione TeamVariant -> TeamVariantV2...")
    v1_variants = session.query(V1TeamVariant).all()
    old_to_new_team: Dict[str, str] = {}
    count = 0
    skipped = 0

    for v in v1_variants:
        old_set_ids = v.pokemon_set_ids or []
        if isinstance(old_set_ids, str):
            try:
                old_set_ids = json.loads(old_set_ids)
            except Exception:
                old_set_ids = []

        # Traduci MD5 -> SHA-256
        new_build_ids = [old_to_new_build.get(sid, sid) for sid in old_set_ids]
        new_build_ids = [bid for bid in new_build_ids if bid]

        if not new_build_ids:
            print(f"[MIG]   WARN: TeamVariant {v.id} ha 0 build valide, skip.")
            continue

        new_team_id = compute_team_hash(new_build_ids)
        old_to_new_team[v.id] = new_team_id

        if session.query(TeamVariantV2).filter_by(id=new_team_id).first():
            skipped += 1
            continue

        new_variant = TeamVariantV2(id=new_team_id, size=len(new_build_ids))
        session.add(new_variant)
        session.flush()

        # Junction table: slot = posizione nel team originale (non ordinata)
        for slot_idx, build_id in enumerate(new_build_ids, start=1):
            build_exists = session.query(PokemonBuild).filter_by(id=build_id).first()
            if not build_exists:
                print(f"[MIG]   WARN: Build {build_id} non trovata per team {new_team_id}")
                continue
            session.add(TeamVariantBuild(
                team_variant_id=new_team_id,
                build_id=build_id,
                slot=slot_idx
            ))

        count += 1

    session.commit()
    print(f"[MIG] {count} team migrati, {skipped} già esistenti.")
    return old_to_new_team


# ──────────────────────────────────────────────────────────────────────────────
# FASE G -- Migrazione Trainer
# ──────────────────────────────────────────────────────────────────────────────

def migrate_trainers(session: Session) -> int:
    print("[MIG] Fase G: Migrazione Trainer...")
    v1_trainers = session.query(V1Trainer).all()
    count = 0
    for t in v1_trainers:
        if session.query(TrainerV2).filter_by(id=t.id).first():
            continue
        session.add(TrainerV2(id=t.id, rating=t.rating))
        count += 1
    session.commit()
    print(f"[MIG] {count} trainer migrati.")
    return count


# ──────────────────────────────────────────────────────────────────────────────
# FASE H -- Migrazione Match + MatchTeam
# ──────────────────────────────────────────────────────────────────────────────

def migrate_matches(session: Session, old_to_new_team: Dict[str, str]) -> int:
    print("[MIG] Fase H: Migrazione Match + MatchTeam...")
    v1_matches = session.query(V1Match).all()
    count = 0
    skipped = 0

    for m in v1_matches:
        if session.query(MatchV2).filter_by(id=m.id).first():
            skipped += 1
            continue

        new_match = MatchV2(
            id=m.id,
            format=m.format,
            timestamp=m.timestamp,
            winner_id=m.winner_id if m.winner_id and session.query(
                TrainerV2).filter_by(id=m.winner_id).first() else None,
        )
        session.add(new_match)
        session.flush()

        for mt in m.teams:
            new_team_id = old_to_new_team.get(mt.team_variant_id)
            if not new_team_id:
                print(f"[MIG]   WARN: team_variant {mt.team_variant_id} non trovato nel mapping")
                continue
            trainer_exists = session.query(TrainerV2).filter_by(id=mt.trainer_id).first()
            if not trainer_exists:
                continue

            session.add(MatchTeamV2(
                match_id=m.id,
                trainer_id=mt.trainer_id,
                player_slot=mt.player_slot,
                team_variant_id=new_team_id,
            ))

        count += 1
        if count % 50 == 0:
            session.flush()
            print(f"[MIG]   ... {count} match processati")

    session.commit()
    print(f"[MIG] {count} match migrati, {skipped} già esistenti.")
    return count


# ──────────────────────────────────────────────────────────────────────────────
# FASE I -- Migrazione Turn + TurnBoardState + TurnFieldCondition
# ──────────────────────────────────────────────────────────────────────────────

def migrate_turns(
    session: Session,
    old_to_new_build: Dict[str, str],
    tag_name_to_id: Dict[str, int]
) -> Dict[int, int]:
    """
    Migra Turn -> TurnV2 + TurnBoardState + TurnFieldCondition.
    Restituisce mapping old_turn_id -> new_turn_id.
    """
    print("[MIG] Fase I: Migrazione Turn...")

    # Mappa tag_name -> id per le field conditions
    fc_tag_ids: Dict[str, int] = {}
    for tag_name_key in set(FIELD_CONDITION_TAG_NAMES.values()):
        t = session.query(Tag).filter_by(name=tag_name_key).first()
        if t:
            fc_tag_ids[tag_name_key] = t.id

    v1_matches = session.query(V1Match).all()
    old_to_new_turn: Dict[int, int] = {}
    count = 0

    for m in v1_matches:
        # Verifica che il match V2 esista
        if not session.query(MatchV2).filter_by(id=m.id).first():
            continue

        for t in m.turns:
            if session.query(TurnV2).filter_by(
                match_id=m.id, turn_number=t.turn_number
            ).first():
                # Già migrato: recupera l'ID
                existing = session.query(TurnV2).filter_by(
                    match_id=m.id, turn_number=t.turn_number
                ).first()
                old_to_new_turn[t.id] = existing.id
                continue

            new_turn = TurnV2(match_id=m.id, turn_number=t.turn_number)
            session.add(new_turn)
            session.flush()
            old_to_new_turn[t.id] = new_turn.id

            # ── Board State (da primo TurnAction del turno) ───────────────
            first_action = t.actions[0] if t.actions else None
            if first_action:
                def translate(bid: Optional[str]) -> Optional[str]:
                    if not bid:
                        return None
                    return old_to_new_build.get(bid, bid)

                session.add(TurnBoardState(
                    turn_id=new_turn.id,
                    p1a_build_id=translate(first_action.active_p1a_id),
                    p1b_build_id=translate(first_action.active_p1b_id),
                    p2a_build_id=translate(first_action.active_p2a_id),
                    p2b_build_id=translate(first_action.active_p2b_id),
                ))

            # ── Field Conditions (da colonne booleane) ──────────────────
            fc_data = {
                "trick_room":    (t.trick_room,    "field"),
                "p1_tailwind":   (t.p1_tailwind,   "p1"),
                "p2_tailwind":   (t.p2_tailwind,   "p2"),
                "p1_reflect":    (t.p1_reflect,    "p1"),
                "p2_reflect":    (t.p2_reflect,    "p2"),
                "p1_lightscreen":(t.p1_lightscreen,"p1"),
                "p2_lightscreen":(t.p2_lightscreen,"p2"),
                "p1_aurora_veil":(t.p1_aurora_veil,"p1"),
                "p2_aurora_veil":(t.p2_aurora_veil,"p2"),
            }

            for fc_key, (is_active, side) in fc_data.items():
                if not is_active:
                    continue
                tag_name = FIELD_CONDITION_TAG_NAMES.get(fc_key)
                if not tag_name:
                    continue
                tag_id = fc_tag_ids.get(tag_name)
                if not tag_id:
                    continue
                session.add(TurnFieldCondition(
                    turn_id=new_turn.id,
                    side=side,
                    tag_id=tag_id,
                    is_active=True,
                ))

            count += 1

    session.commit()
    print(f"[MIG] {count} turni migrati.")
    return old_to_new_turn


# ──────────────────────────────────────────────────────────────────────────────
# FASE J -- Migrazione TurnAction + ActionEffect + ActionEffectStatChange
# ──────────────────────────────────────────────────────────────────────────────

def migrate_actions(
    session: Session,
    old_to_new_build: Dict[str, str],
    old_to_new_turn: Dict[int, int]
) -> int:
    print("[MIG] Fase J: Migrazione TurnAction + ActionEffect...")
    count = 0

    v1_matches = session.query(V1Match).all()
    for m in v1_matches:
        for t in m.turns:
            new_turn_id = old_to_new_turn.get(t.id)
            if not new_turn_id:
                continue

            for a in t.actions:
                def translate(bid: Optional[str]) -> Optional[str]:
                    if not bid:
                        return None
                    return old_to_new_build.get(bid, bid)

                move_id_val = None
                if a.move_id:
                    move_exists = session.query(MoveV2).filter_by(id=a.move_id).first()
                    move_id_val = a.move_id if move_exists else None

                # Serializza raw_tags come JSON string
                raw_tags_str = None
                if a.tags:
                    try:
                        raw_tags_str = json.dumps(a.tags) if isinstance(a.tags, dict) else str(a.tags)
                    except Exception:
                        pass

                new_action = TurnActionV2(
                    turn_id=new_turn_id,
                    action_order=a.action_order,
                    action_type=a.action_type,
                    actor_build_id=translate(a.actor_set_id),
                    target_build_id=translate(a.target_set_id),
                    move_id=move_id_val,
                    details=a.details,
                    raw_tags=raw_tags_str,
                )
                session.add(new_action)
                session.flush()

                # Migra effetti
                for eff in a.effects:
                    new_effect = ActionEffectV2(
                        turn_action_id=new_action.id,
                        target_build_id=translate(eff.target_set_id),
                        damage_percent=eff.damage_percent or 0.0,
                        status_inflicted=eff.status_inflicted,
                        is_crit=eff.is_crit or False,
                        effectiveness=eff.effectiveness,
                        ability_activated=eff.ability_activated,
                        item_consumed=eff.item_consumed,
                        is_protected=eff.is_protected or False,
                    )
                    session.add(new_effect)
                    session.flush()

                    # Migra stat_changes da JSON dict
                    stat_changes = safe_json_loads(eff.stat_changes)
                    for stat_name, stages in stat_changes.items():
                        try:
                            session.add(ActionEffectStatChange(
                                effect_id=new_effect.id,
                                stat=str(stat_name)[:8],
                                stages=int(stages),
                            ))
                        except (ValueError, TypeError):
                            pass

                count += 1

        if count % 500 == 0 and count > 0:
            session.flush()
            print(f"[MIG]   ... {count} azioni processate")

    session.commit()
    print(f"[MIG] {count} azioni migrate.")
    return count


def safe_json_loads(val) -> dict:
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return {}
    return {}


# ──────────────────────────────────────────────────────────────────────────────
# FASE K -- Migrazione MatchSummary
# ──────────────────────────────────────────────────────────────────────────────

def migrate_summaries(session: Session, old_to_new_build: Dict[str, str]) -> int:
    print("[MIG] Fase K: Migrazione MatchSummary...")
    v1_summaries = session.query(V1MatchSummary).all()
    count = 0

    for s in v1_summaries:
        if not session.query(MatchV2).filter_by(id=s.match_id).first():
            continue
        if session.query(MatchSummaryV2).filter_by(match_id=s.match_id).first():
            continue

        new_summary = MatchSummaryV2(
            match_id=s.match_id,
            total_turns=s.total_turns or 0,
        )
        session.add(new_summary)
        session.flush()

        def add_brought(player_slot: str, build_ids_json):
            raw = build_ids_json
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    raw = []
            if not isinstance(raw, list):
                raw = []
            for old_bid in raw:
                if not old_bid:
                    continue
                new_bid = old_to_new_build.get(old_bid, old_bid)
                build_exists = session.query(PokemonBuild).filter_by(id=new_bid).first()
                if build_exists:
                    session.add(MatchBrought(
                        summary_id=new_summary.id,
                        player_slot=player_slot,
                        build_id=new_bid,
                    ))

        add_brought("p1", s.p1_brought_pokemon)
        add_brought("p2", s.p2_brought_pokemon)

        count += 1

    session.commit()
    print(f"[MIG] {count} summary migrate.")
    return count


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def run_migration(dry_run: bool = False):
    print("=" * 60)
    print("JAnalytics -- Migrazione Schema V1 -> V2")
    print("=" * 60)

    if dry_run:
        print("[DRY RUN] Nessuna modifica verrà salvata.")

    # 1. Crea tabelle V2 e seed tag
    from database.models_v2 import (
        PokemonSpeciesV2, AbilityV2, ItemV2, MoveV2, Tag, MoveTag, AbilityTag, ItemTag,
        PokemonBuild, PokemonBuildMove, PokemonBuildStats,
        TeamVariantV2, TeamVariantBuild,
        TrainerV2, MatchV2, MatchTeamV2, TurnV2, TurnBoardState, TurnFieldCondition,
        TurnActionV2, ActionEffectV2, ActionEffectStatChange,
        MatchSummaryV2, MatchBrought, MatchArchetype
    )
    print("[MIG] Creazione tabelle V2...")
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        # Seed tag (idempotente)
        tag_map = _seed_tags(session)

        # Pipeline di migrazione
        migrate_species(session)
        migrate_abilities(session)
        migrate_items(session)
        migrate_moves(session)

        old_to_new_build = migrate_builds(session)
        old_to_new_team  = migrate_teams(session, old_to_new_build)
        migrate_trainers(session)
        migrate_matches(session, old_to_new_team)
        old_to_new_turn  = migrate_turns(session, old_to_new_build, tag_map)
        migrate_actions(session, old_to_new_build, old_to_new_turn)
        migrate_summaries(session, old_to_new_build)

        if dry_run:
            session.rollback()
            print("[DRY RUN] Rollback eseguito. Nessuna modifica salvata.")
        else:
            session.commit()
            print("\n[OK] Migrazione completata con successo!")

    except Exception as e:
        session.rollback()
        print(f"\n[ERRORE] Errore durante la migrazione: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        session.close()

    # ── Verifica post-migrazione ────────────────────────────────────────────
    if not dry_run:
        print("\n[VERIFY] Verifica integrità post-migrazione...")
        verify_session = SessionLocal()
        try:
            n_builds  = verify_session.query(PokemonBuild).count()
            n_teams   = verify_session.query(TeamVariantV2).count()
            n_matches = verify_session.query(MatchV2).count()
            n_turns   = verify_session.query(TurnV2).count()
            n_actions = verify_session.query(TurnActionV2).count()
            n_effects = verify_session.query(ActionEffectV2).count()

            # Build senza mosse (può essere legittimo se la build ha 0 mosse parsed)
            builds_no_moves = verify_session.query(PokemonBuild).filter(
                ~PokemonBuild.id.in_(
                    verify_session.query(PokemonBuildMove.build_id)
                )
            ).count()

            print(f"  PokemonBuild:      {n_builds}")
            print(f"  TeamVariantV2:     {n_teams}")
            print(f"  MatchV2:           {n_matches}")
            print(f"  TurnV2:            {n_turns}")
            print(f"  TurnActionV2:      {n_actions}")
            print(f"  ActionEffectV2:    {n_effects}")
            print(f"  Build senza mosse: {builds_no_moves} (warning se > 0)")

        finally:
            verify_session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migra il database JAnalytics da schema V1 a V2."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Esegui la migrazione senza salvare (rollback finale)"
    )
    args = parser.parse_args()
    run_migration(dry_run=args.dry_run)
