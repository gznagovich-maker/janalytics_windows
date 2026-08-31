"""
repository_v2.py
================
Repository layer riscritto per lo schema V2 di JAnalytics.

Tutte le query usano i nuovi modelli (models_v2.py) con:
  - Tabelle di giunzione per mosse e team (no JSON/CSV)
  - Tag system per field conditions e archetipi
  - Hash SHA-256 per build e team
  - Ricerche per specie/mossa/abilità con JOIN su junction table (indicizzabili)
"""

import json
import re
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import or_, func, select, and_
from sqlalchemy.orm import Session, joinedload, selectinload

from database.connection import SessionLocal
from database.models_v2 import (
    MatchV2, MatchTeamV2, PokemonBuild, PokemonBuildMove, PokemonBuildStats, MoveV2,
    TeamVariantV2, TeamVariantBuild, TrainerV2, TurnV2, TurnActionV2,
    ActionEffectV2, ActionEffectStatChange, TurnBoardState, TurnFieldCondition,
    PokemonSpeciesV2, AbilityV2, ItemV2, Tag, MatchSummaryV2,
    MatchBrought, MatchArchetype
)
from database.hash_utils import compute_build_hash, compute_team_hash, to_id
from src.domain.models import Pokemon


# ──────────────────────────────────────────────────────────────────────────────
# SAVE / UPSERT
# ──────────────────────────────────────────────────────────────────────────────

def _upsert_build(session: Session, poke: Pokemon,
                  ev_hp=0, ev_atk=0, ev_def=0, ev_spa=0, ev_spd=0, ev_spe=0,
                  iv_hp=31, iv_atk=31, iv_def=31, iv_spa=31, iv_spd=31, iv_spe=31) -> str:
    """
    Crea (o riusa) una PokemonBuild fuzzy per il Pokémon dato.
    L'hash NON include EV/IV — ogni spread viene salvato in PokemonBuildStats (upsert).
    Restituisce il build_id SHA-256.
    """
    moves_list = [to_id(m) for m in (poke.moves or []) if m]

    build_id = compute_build_hash(
        species=poke.species or "",
        ability=poke.ability or "",
        item=poke.item or "",
        tera_type=poke.tera_type,
        nature=poke.nature or "hardy",
        moves=moves_list,
        # EV/IV esclusi dal hash
    )

    existing_build = session.query(PokemonBuild).filter_by(id=build_id).first()
    if not existing_build:
        new_build = PokemonBuild(
            id=build_id,
            species_id=to_id(poke.species) if poke.species else None,
            ability_id=to_id(poke.ability) if poke.ability else None,
            item_id=to_id(poke.item) if poke.item and to_id(poke.item) != 'item' else None,
            tera_type=poke.tera_type,
            nature=poke.nature or "Hardy",
        )
        session.add(new_build)
        session.flush()
        for slot_idx, move_id in enumerate(sorted(moves_list), start=1):
            if not move_id:
                continue
            if not session.query(MoveV2).filter_by(id=move_id).first():
                session.add(MoveV2(
                    id=move_id, name=move_id.capitalize(),
                    type="Normal", category="Status", base_power=0, accuracy=100, priority=0
                ))
                session.flush()
            session.add(PokemonBuildMove(build_id=build_id, move_id=move_id, slot=slot_idx))

    else:
        # Patch any incorrectly saved None values if we now have the data
        dirty = False
        if not existing_build.ability_id and poke.ability:
            existing_build.ability_id = to_id(poke.ability)
            dirty = True
        if not existing_build.item_id and poke.item and to_id(poke.item) != 'item':
            existing_build.item_id = to_id(poke.item)
            dirty = True
        if dirty:
            session.flush()

    # Upsert spread EV/IV in PokemonBuildStats
    existing_stats = session.query(PokemonBuildStats).filter_by(
        build_id=build_id,
        ev_hp=ev_hp, ev_atk=ev_atk, ev_def=ev_def,
        ev_spa=ev_spa, ev_spd=ev_spd, ev_spe=ev_spe,
        iv_hp=iv_hp, iv_atk=iv_atk, iv_def=iv_def,
        iv_spa=iv_spa, iv_spd=iv_spd, iv_spe=iv_spe,
    ).first()
    if existing_stats:
        existing_stats.observed_count += 1
    else:
        session.add(PokemonBuildStats(
            build_id=build_id,
            ev_hp=ev_hp, ev_atk=ev_atk, ev_def=ev_def,
            ev_spa=ev_spa, ev_spd=ev_spd, ev_spe=ev_spe,
            iv_hp=iv_hp, iv_atk=iv_atk, iv_def=iv_def,
            iv_spa=iv_spa, iv_spd=iv_spd, iv_spe=iv_spe,
            observed_count=1,
        ))
        session.flush()

    return build_id


def save_parsed_match_to_db_v2(parsed_match, match_id_str: str):
    """
    Salva un match parsato nel database V2.
    Equivalente funzionale di repository.save_parsed_match_to_db()
    con lo schema normalizzato.
    """
    session = SessionLocal()
    try:
        print(f"-> [REPO-V2] Avvio salvataggio match {match_id_str}...")

        # Match — winner_id viene impostato DOPO i trainer (vincolo FK)
        db_match = session.query(MatchV2).filter_by(id=match_id_str).first()
        if not db_match:
            db_match = MatchV2(id=match_id_str, format=parsed_match.format)
            session.add(db_match)
            session.flush()

        poke_tracking: Dict[str, str] = {}  # "p1: pikachu" → build_id
        brought_p1: set = set()
        brought_p2: set = set()

        for player_slot, player_data in parsed_match.players.items():
            # Trainer — deve esistere PRIMA che match_v2.winner_id vi punti
            db_trainer = session.query(TrainerV2).filter_by(id=player_data.name).first()
            if not db_trainer:
                db_trainer = TrainerV2(id=player_data.name, rating=player_data.rating)
                session.add(db_trainer)
                session.flush()
            elif player_data.rating is not None:
                db_trainer.rating = player_data.rating

            # Builds
            build_ids = []
            for poke in player_data.team:
                build_id = _upsert_build(session, poke)
                build_ids.append(build_id)
                tracking_key = f"{player_slot}: {poke.species.lower()}"
                poke_tracking[tracking_key] = build_id

            # Team variant
            team_id = compute_team_hash(build_ids)
            if not session.query(TeamVariantV2).filter_by(id=team_id).first():
                new_variant = TeamVariantV2(id=team_id, size=len(build_ids))
                session.add(new_variant)
                session.flush()
                for slot_idx, bid in enumerate(build_ids, start=1):
                    session.add(TeamVariantBuild(
                        team_variant_id=team_id, build_id=bid, slot=slot_idx
                    ))

            session.add(MatchTeamV2(
                match_id=match_id_str,
                trainer_id=player_data.name,
                player_slot=player_slot,
                team_variant_id=team_id,
            ))
            session.flush()

        # Imposta winner_id ORA che tutti i trainer sono in DB
        if not db_match.winner_id:
            winner = getattr(parsed_match, "winner_name", None)
            if winner and winner != 'tie':
                # Verifica che il winner esista effettivamente come trainer
                if session.query(TrainerV2).filter_by(id=winner).first():
                    db_match.winner_id = winner
        session.flush()

        def get_build_id(raw_str: str) -> Optional[str]:
            if not raw_str:
                return None
            if ":" in raw_str:
                parts = raw_str.split(":")
                p_slot = parts[0][:2]
                species = parts[1].split(',')[0].strip().lower()
                res = poke_tracking.get(f"{p_slot}: {species}")
                if res:
                    return res
                for k, v in poke_tracking.items():
                    if k.startswith(f"{p_slot}:"):
                        base_sp = k.split(': ')[1]
                        sid = to_id(species)
                        bid = to_id(base_sp)
                        if sid and bid and (sid in bid or bid in sid):
                            return v
                return None
            species = raw_str.split(',')[0].strip().lower()
            for k, v in poke_tracking.items():
                if k.endswith(f": {species}"):
                    return v
            return None

        # Field conditions tag lookup
        fc_tags: Dict[str, Optional[int]] = {}
        for tag_name in ["trickroom", "tailwind", "reflect", "lightscreen", "auroraveil"]:
            t = session.query(Tag).filter_by(name=tag_name).first()
            fc_tags[tag_name] = t.id if t else None

        total_turns = 0
        for turn_num, actions in parsed_match.turns.items():
            total_turns += 1
            db_turn = TurnV2(match_id=match_id_str, turn_number=turn_num)
            session.add(db_turn)
            session.flush()

            # Board state da primo action
            first_act = actions[0] if actions else None
            if first_act:
                session.add(TurnBoardState(
                    turn_id=db_turn.id,
                    p1a_build_id=get_build_id(f"p1: {first_act.board_state.p1p1}") if getattr(first_act.board_state, 'p1p1', None) else None,
                    p1b_build_id=get_build_id(f"p1: {first_act.board_state.p1p2}") if getattr(first_act.board_state, 'p1p2', None) else None,
                    p2a_build_id=get_build_id(f"p2: {first_act.board_state.p2p1}") if getattr(first_act.board_state, 'p2p1', None) else None,
                    p2b_build_id=get_build_id(f"p2: {first_act.board_state.p2p2}") if getattr(first_act.board_state, 'p2p2', None) else None,
                ))

            # Field conditions da global_state
            gs = parsed_match.global_state
            if getattr(gs, 'trick_room', False) and fc_tags.get('trickroom'):
                session.add(TurnFieldCondition(turn_id=db_turn.id, side='field', tag_id=fc_tags['trickroom']))
            for side, attr in [('p1', 'tailwind_p1'), ('p2', 'tailwind_p2')]:
                if getattr(gs, attr, False) and fc_tags.get('tailwind'):
                    session.add(TurnFieldCondition(turn_id=db_turn.id, side=side, tag_id=fc_tags['tailwind']))

            for order_idx, act in enumerate(actions):
                if act.action_type in ("switch", "drag"):
                    if act.actor and act.actor.startswith("p1"):
                        brought_p1.add(get_build_id(act.actor))
                    if act.actor and act.actor.startswith("p2"):
                        brought_p2.add(get_build_id(act.actor))

                move_id_val = None
                if act.action_type == 'move':
                    move_id_val = to_id(act.details)
                    if move_id_val and not session.query(MoveV2).filter_by(id=move_id_val).first():
                        session.add(MoveV2(id=move_id_val, name=move_id_val.capitalize(),
                                          type="Normal", category="Status", base_power=0, accuracy=100, priority=0))
                        session.flush()

                # raw_tags: PG vuole dict (JSONB), non stringa JSON
                raw_tags_val = None
                if hasattr(act, 'tags') and act.tags:
                    try:
                        raw_tags_val = act.tags if isinstance(act.tags, dict) else json.loads(json.dumps(act.tags))
                    except Exception:
                        pass

                db_action = TurnActionV2(
                    turn_id=db_turn.id,
                    action_order=order_idx,
                    action_type=act.action_type,
                    actor_build_id=get_build_id(act.actor),
                    target_build_id=get_build_id(act.target),
                    move_id=move_id_val,
                    details=act.details,
                    raw_tags=raw_tags_val,
                )
                session.add(db_action)
                session.flush()

                if hasattr(act, 'effects'):
                    for target_raw_id, eff in act.effects.items():
                        db_effect = ActionEffectV2(
                            turn_action_id=db_action.id,
                            target_build_id=get_build_id(target_raw_id),
                            damage_percent=eff.damage_percent,
                            status_inflicted=eff.status_inflicted,
                            is_crit=eff.is_crit,
                            effectiveness=eff.effectiveness,
                            ability_activated=eff.ability_activated,
                            item_consumed=eff.item_consumed,
                            is_protected=eff.is_protected,
                        )
                        session.add(db_effect)
                        session.flush()

                        if isinstance(eff.stat_changes, dict):
                            for stat_name, stages in eff.stat_changes.items():
                                try:
                                    session.add(ActionEffectStatChange(
                                        effect_id=db_effect.id,
                                        stat=str(stat_name)[:8],
                                        stages=int(stages)
                                    ))
                                except (ValueError, TypeError):
                                    pass

        # Summary
        summary = MatchSummaryV2(match_id=match_id_str, total_turns=total_turns)
        session.add(summary)
        session.flush()

        for bid in brought_p1:
            if bid:
                session.add(MatchBrought(summary_id=summary.id, player_slot="p1", build_id=bid))
        for bid in brought_p2:
            if bid:
                session.add(MatchBrought(summary_id=summary.id, player_slot="p2", build_id=bid))

        session.commit()
        print(f"-> [REPO-V2] COMMIT completato.")
    except Exception as e:
        session.rollback()
        print(f"-> [REPO-V2] ERRORE: {type(e).__name__}: {e}")
        raise
    finally:
        session.close()


# ──────────────────────────────────────────────────────────────────────────────
# READ: Match List / Search
# ──────────────────────────────────────────────────────────────────────────────

def search_matches_v2(
    query_text: str = "",
    player_filter: str = "",
    species_filter: str = "",
    move_filter: str = "",
    limit: int = 20,
    offset: int = 0
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Cerca match con filtri opzionali.
    Tutte le ricerche per specie/mossa usano JOIN indicizzabili (no LIKE su JSON).
    """
    session = SessionLocal()
    try:
        q = session.query(MatchV2)

        if query_text:
            q = q.filter(MatchV2.id.ilike(f"%{query_text}%"))

        if player_filter:
            q = q.filter(
                MatchV2.teams.any(
                    MatchTeamV2.trainer_id.ilike(f"%{player_filter}%")
                )
            )

        if species_filter:
            species_id = to_id(species_filter)
            # JOIN indicizzato: match -> match_team -> team_variant -> team_variant_build -> pokemon_build
            matching_builds = (
                session.query(PokemonBuild.id)
                .filter(PokemonBuild.species_id == species_id)
                .subquery()
            )
            matching_variants = (
                session.query(TeamVariantBuild.team_variant_id)
                .filter(TeamVariantBuild.build_id.in_(matching_builds))
                .subquery()
            )
            q = q.filter(
                MatchV2.teams.any(
                    MatchTeamV2.team_variant_id.in_(matching_variants)
                )
            )

        if move_filter:
            move_id = to_id(move_filter)
            # JOIN indicizzato: match -> ... -> pokemon_build_move
            builds_with_move = (
                session.query(PokemonBuildMove.build_id)
                .filter(PokemonBuildMove.move_id == move_id)
                .subquery()
            )
            variants_with_move = (
                session.query(TeamVariantBuild.team_variant_id)
                .filter(TeamVariantBuild.build_id.in_(builds_with_move))
                .subquery()
            )
            q = q.filter(
                MatchV2.teams.any(
                    MatchTeamV2.team_variant_id.in_(variants_with_move)
                )
            )

        total_count = q.count()
        matches = (
            q.options(
                selectinload(MatchV2.teams)
                .selectinload(MatchTeamV2.variant)
                .selectinload(TeamVariantV2.builds)
                .selectinload(TeamVariantBuild.build)
                .selectinload(PokemonBuild.species)
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

        results = []
        for m in matches:
            p1_team = next((t for t in m.teams if t.player_slot == "p1"), None)
            p2_team = next((t for t in m.teams if t.player_slot == "p2"), None)

            def format_team(match_team: Optional[MatchTeamV2]) -> str:
                if not match_team or not match_team.variant:
                    return ""
                species_names = []
                for tvb in sorted(match_team.variant.builds, key=lambda x: x.slot):
                    if tvb.build and tvb.build.species:
                        species_names.append(tvb.build.species.name)
                    elif tvb.build and tvb.build.species_id:
                        species_names.append(tvb.build.species_id.capitalize())
                return ", ".join(species_names)

            results.append({
                "id": m.id,
                "p1": p1_team.trainer_id if p1_team else "P1 Sconosciuto",
                "p2": p2_team.trainer_id if p2_team else "P2 Sconosciuto",
                "p1_team": format_team(p1_team),
                "p2_team": format_team(p2_team),
                "format": m.format,
                "timestamp": m.timestamp,
            })
        return results, total_count

    finally:
        session.close()


# ──────────────────────────────────────────────────────────────────────────────
# READ: Match Details
# ──────────────────────────────────────────────────────────────────────────────

def get_match_details_v2(match_id: str) -> Optional[Dict[str, Any]]:
    """Restituisce i dettagli completi di un match in formato dizionario."""
    session = SessionLocal()
    try:
        match = (
            session.query(MatchV2)
            .options(
                selectinload(MatchV2.teams)
                    .selectinload(MatchTeamV2.variant)
                    .selectinload(TeamVariantV2.builds)
                    .selectinload(TeamVariantBuild.build)
                    .selectinload(PokemonBuild.species),
                selectinload(MatchV2.teams)
                    .selectinload(MatchTeamV2.variant)
                    .selectinload(TeamVariantV2.builds)
                    .selectinload(TeamVariantBuild.build)
                    .selectinload(PokemonBuild.item),
                selectinload(MatchV2.teams)
                    .selectinload(MatchTeamV2.variant)
                    .selectinload(TeamVariantV2.builds)
                    .selectinload(TeamVariantBuild.build)
                    .selectinload(PokemonBuild.ability),
                selectinload(MatchV2.teams)
                    .selectinload(MatchTeamV2.variant)
                    .selectinload(TeamVariantV2.builds)
                    .selectinload(TeamVariantBuild.build)
                    .selectinload(PokemonBuild.move_slots)
                    .selectinload(PokemonBuildMove.move),
                selectinload(MatchV2.turns)
                    .selectinload(TurnV2.actions)
                    .selectinload(TurnActionV2.effects),
                selectinload(MatchV2.turns)
                    .selectinload(TurnV2.board_state),
                selectinload(MatchV2.turns)
                    .selectinload(TurnV2.field_conditions)
                    .selectinload(TurnFieldCondition.tag),
            )
            .filter_by(id=match_id)
            .first()
        )
        if not match:
            return None

        # build_id → species name (per il board state display)
        build_species: Dict[str, str] = {}

        teams_data: Dict[str, Any] = {}
        for mt in match.teams:
            p_slot = mt.player_slot
            poke_list = []
            if mt.variant:
                for tvb in sorted(mt.variant.builds, key=lambda x: x.slot):
                    b = tvb.build
                    if not b:
                        continue
                    sp_name = (b.species.name if b.species else (b.species_id or "?")).capitalize()
                    build_species[b.id] = sp_name

                    moves = [ms.move.name if ms.move else ms.move_id
                             for ms in sorted(b.move_slots, key=lambda x: x.slot)]
                    poke_list.append({
                        "id": b.id,
                        "species": sp_name,
                        "ability": b.ability.name if b.ability else (b.ability_id.capitalize() if b.ability_id else "Non rivelata"),
                        "item": b.item.name if b.item else (b.item_id.capitalize() if b.item_id else "Non rivelato"),
                        "tera_type": b.tera_type or "Non rivelato",
                        "nature": b.nature or "Sconosciuta",
                        "moves": moves,
                        "evs": {
                            "hp": 0, "atk": 0, "def": 0,
                            "spa": 0, "spd": 0, "spe": 0,
                        },
                        "ivs": {
                            "hp": 31, "atk": 31, "def": 31,
                            "spa": 31, "spd": 31, "spe": 31,
                        },
                        "base_stats": {
                            "hp": getattr(b.species, "bst_hp", 0) if b.species else 0,
                            "atk": getattr(b.species, "bst_atk", 0) if b.species else 0,
                            "def": getattr(b.species, "bst_def", 0) if b.species else 0,
                            "spa": getattr(b.species, "bst_spa", 0) if b.species else 0,
                            "spd": getattr(b.species, "bst_spd", 0) if b.species else 0,
                            "spe": getattr(b.species, "bst_spe", 0) if b.species else 0,
                        }
                    })

            trainer = session.query(TrainerV2).filter_by(id=mt.trainer_id).first()
            teams_data[p_slot] = {
                "trainer": mt.trainer_id,
                "rating": trainer.rating if trainer else "N/A",
                "pokemon": poke_list,
            }

        turns_data = []
        for t in sorted(match.turns, key=lambda x: x.turn_number):
            # Board state
            bs = t.board_state
            board = {
                "p1a": {"id": bs.p1a_build_id, "species": build_species.get(bs.p1a_build_id, "Vuoto")} if bs and bs.p1a_build_id else {},
                "p1b": {"id": bs.p1b_build_id, "species": build_species.get(bs.p1b_build_id, "Vuoto")} if bs and bs.p1b_build_id else {},
                "p2a": {"id": bs.p2a_build_id, "species": build_species.get(bs.p2a_build_id, "Vuoto")} if bs and bs.p2a_build_id else {},
                "p2b": {"id": bs.p2b_build_id, "species": build_species.get(bs.p2b_build_id, "Vuoto")} if bs and bs.p2b_build_id else {},
            }

            # Field conditions
            fc = {fc.tag.name: fc.is_active for fc in t.field_conditions if fc.tag}

            actions = []
            for a in sorted(t.actions, key=lambda x: x.action_order):
                try:
                    parsed_tags = json.loads(a.raw_tags) if isinstance(a.raw_tags, str) and a.raw_tags else {}
                except Exception:
                    parsed_tags = {}
                if isinstance(a.raw_tags, dict):
                    parsed_tags = a.raw_tags

                actions.append({
                    "order": a.action_order,
                    "type": a.action_type,
                    "actor": build_species.get(a.actor_build_id, "—"),
                    "target": build_species.get(a.target_build_id, "—"),
                    "move": a.move_id,
                    "details": a.details or "",
                    "raw_tags": parsed_tags,
                    "board_state": board,
                    "effects": [
                        {
                            "target": build_species.get(eff.target_build_id, "?"),
                            "damage_pct": eff.damage_percent,
                            "status": eff.status_inflicted,
                            "is_crit": eff.is_crit,
                            "effectiveness": eff.effectiveness,
                            "is_protected": eff.is_protected,
                        }
                        for eff in a.effects
                    ],
                })

            turns_data.append({
                "turn_number": t.turn_number,
                "board_state": board,
                "field_conditions": fc,
                "actions": actions,
            })

        return {
            "match_id": match.id,
            "format": match.format,
            "winner": match.winner_id,
            "teams": teams_data,
            "turns": turns_data,
        }
    finally:
        session.close()


# ──────────────────────────────────────────────────────────────────────────────
# ANALYTICS: Usage Stats
# ──────────────────────────────────────────────────────────────────────────────

def get_species_usage_v2(format_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Calcola la usage rate per specie nel formato specificato.
    Usa la Materialized View mv_species_usage se disponibile (PG),
    altrimenti fa la query live con JOIN singolo (nessun N+1).
    """
    session = SessionLocal()
    try:
        # Fast path: Materialized View (PostgreSQL)
        try:
            from sqlalchemy import text
            total_teams = (
                session.query(func.count(MatchTeamV2.id))
                .join(MatchV2, MatchTeamV2.match_id == MatchV2.id)
                .filter(MatchV2.format == format_id)
                .scalar()
            ) or 1

            rows = session.execute(
                text("""
                    SELECT species_id, species_name, type1, type2, sprite_url, occurrences
                    FROM mv_species_usage
                    WHERE format = :fmt
                    ORDER BY occurrences DESC
                    LIMIT :lim
                """),
                {"fmt": format_id, "lim": limit}
            ).fetchall()
            return [
                {
                    "species_id": r.species_id,
                    "name": r.species_name or r.species_id,
                    "type1": r.type1,
                    "type2": r.type2,
                    "sprite_url": r.sprite_url,
                    "occurrences": r.occurrences,
                    "usage_percent": round((r.occurrences / total_teams) * 100, 1),
                }
                for r in rows
            ]
        except Exception:
            pass  # MV non disponibile, usa query live

        # Fallback: query live con JOIN singolo (no N+1)
        total_teams = (
            session.query(func.count(MatchTeamV2.id))
            .join(MatchV2, MatchTeamV2.match_id == MatchV2.id)
            .filter(MatchV2.format == format_id)
            .scalar()
        )
        if not total_teams:
            return []

        species_counts = (
            session.query(
                PokemonBuild.species_id,
                PokemonSpeciesV2.name,
                PokemonSpeciesV2.type1,
                PokemonSpeciesV2.type2,
                PokemonSpeciesV2.sprite_url,
                func.count(TeamVariantBuild.build_id).label("cnt")
            )
            .join(TeamVariantBuild, TeamVariantBuild.build_id == PokemonBuild.id)
            .join(MatchTeamV2, MatchTeamV2.team_variant_id == TeamVariantBuild.team_variant_id)
            .join(MatchV2, MatchV2.id == MatchTeamV2.match_id)
            .outerjoin(PokemonSpeciesV2, PokemonSpeciesV2.id == PokemonBuild.species_id)
            .filter(MatchV2.format == format_id)
            .group_by(
                PokemonBuild.species_id,
                PokemonSpeciesV2.name,
                PokemonSpeciesV2.type1,
                PokemonSpeciesV2.type2,
                PokemonSpeciesV2.sprite_url,
            )
            .order_by(func.count(TeamVariantBuild.build_id).desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "species_id": species_id,
                "name": name or species_id,
                "type1": type1,
                "type2": type2,
                "sprite_url": sprite_url,
                "occurrences": cnt,
                "usage_percent": round((cnt / total_teams) * 100, 1),
            }
            for species_id, name, type1, type2, sprite_url, cnt in species_counts
        ]
    finally:
        session.close()


def get_move_usage_v2(format_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Calcola la move usage rate per il formato specificato.
    Fast path tramite mv_move_usage (PG), fallback a JOIN live (no N+1).
    """
    session = SessionLocal()
    try:
        total_teams = (
            session.query(func.count(MatchTeamV2.id))
            .join(MatchV2)
            .filter(MatchV2.format == format_id)
            .scalar()
        ) or 1

        # Fast path: Materialized View
        try:
            from sqlalchemy import text
            rows = session.execute(
                text("""
                    SELECT move_id, move_name, move_type, move_category, occurrences
                    FROM mv_move_usage
                    WHERE format = :fmt
                    ORDER BY occurrences DESC
                    LIMIT :lim
                """),
                {"fmt": format_id, "lim": limit}
            ).fetchall()
            return [
                {
                    "move_id": r.move_id,
                    "name": r.move_name or r.move_id,
                    "type": r.move_type,
                    "category": r.move_category,
                    "occurrences": r.occurrences,
                    "usage_percent": round((r.occurrences / total_teams) * 100, 1),
                }
                for r in rows
            ]
        except Exception:
            pass

        # Fallback: JOIN live con MoveV2 (no N+1)
        move_counts = (
            session.query(
                PokemonBuildMove.move_id,
                MoveV2.name,
                MoveV2.type,
                MoveV2.category,
                func.count(PokemonBuildMove.build_id).label("cnt")
            )
            .outerjoin(MoveV2, MoveV2.id == PokemonBuildMove.move_id)
            .join(TeamVariantBuild, TeamVariantBuild.build_id == PokemonBuildMove.build_id)
            .join(MatchTeamV2, MatchTeamV2.team_variant_id == TeamVariantBuild.team_variant_id)
            .join(MatchV2, MatchV2.id == MatchTeamV2.match_id)
            .filter(MatchV2.format == format_id)
            .group_by(PokemonBuildMove.move_id, MoveV2.name, MoveV2.type, MoveV2.category)
            .order_by(func.count(PokemonBuildMove.build_id).desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "move_id": move_id,
                "name": name or move_id,
                "type": move_type,
                "category": category,
                "occurrences": cnt,
                "usage_percent": round((cnt / total_teams) * 100, 1),
            }
            for move_id, name, move_type, category, cnt in move_counts
        ]
    finally:
        session.close()


def get_builds_for_species_v2(
    species_id: str,
    format_id: Optional[str] = None,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Restituisce le build più usate per una specie, con dettaglio mosse.
    """
    session = SessionLocal()
    try:
        q = (
            session.query(
                PokemonBuild,
                func.count(TeamVariantBuild.build_id).label("cnt")
            )
            .filter(PokemonBuild.species_id == to_id(species_id))
            .join(TeamVariantBuild, TeamVariantBuild.build_id == PokemonBuild.id)
            .join(MatchTeamV2, MatchTeamV2.team_variant_id == TeamVariantBuild.team_variant_id)
        )

        if format_id:
            q = q.join(MatchV2, MatchV2.id == MatchTeamV2.match_id).filter(
                MatchV2.format == format_id
            )

        builds_with_counts = (
            q.group_by(PokemonBuild.id)
            .order_by(func.count(TeamVariantBuild.build_id).desc())
            .limit(limit)
            .all()
        )

        total = sum(cnt for _, cnt in builds_with_counts)

        results = []
        for build, cnt in builds_with_counts:
            # Carica mosse (selectin per evitare N+1)
            moves = (
                session.query(PokemonBuildMove)
                .filter_by(build_id=build.id)
                .order_by(PokemonBuildMove.slot)
                .all()
            )
            move_names = [ms.move_id for ms in moves]

            results.append({
                "build_id": build.id,
                "ability": build.ability_id,
                "item": build.item_id,
                "tera_type": build.tera_type,
                "nature": build.nature,
                "moves": move_names,
                "evs": {
                    "hp": build.ev_hp, "atk": build.ev_atk, "def": build.ev_def,
                    "spa": build.ev_spa, "spd": build.ev_spd, "spe": build.ev_spe,
                },
                "occurrences": cnt,
                "usage_percent": round((cnt / total) * 100, 1) if total > 0 else 0,
            })
        return results
    finally:
        session.close()


# ──────────────────────────────────────────────────────────────────────────────
# DELETE
# ──────────────────────────────────────────────────────────────────────────────

def delete_match_v2(match_id: str) -> bool:
    session = SessionLocal()
    try:
        match = session.query(MatchV2).filter_by(id=match_id).first()
        if match:
            session.delete(match)
            session.commit()
            return True
        return False
    except Exception:
        session.rollback()
        return False
    finally:
        session.close()


def clear_all_matches_v2() -> bool:
    session = SessionLocal()
    try:
        session.query(MatchV2).delete()
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False
    finally:
        session.close()


def get_all_matches_v2() -> List[Dict[str, Any]]:
    session = SessionLocal()
    try:
        matches = session.query(MatchV2).all()
        return [
            {"id": m.id, "format": m.format, "timestamp": m.timestamp}
            for m in matches
        ]
    finally:
        session.close()
