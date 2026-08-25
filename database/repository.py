import json
import re
import hashlib
from typing import Optional, List, Dict, Any
from sqlalchemy import or_, text
from sqlalchemy.orm import joinedload
from database.connection import SessionLocal
from database.models import Match, MatchTeam, PokemonSet, TeamVariant, Turn, TurnAction, Trainer, ActionEffect, MatchSummary
from src.domain.models import Pokemon

def to_id(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'[^a-z0-9]', '', text.lower())

def _hash_pokemon_set(poke: Pokemon) -> str:
    s_moves = ",".join([to_id(m) for m in poke.moves]) if poke.moves else ""
    data = f"{to_id(poke.species)}_{to_id(poke.ability)}_{to_id(poke.item)}_{poke.tera_type}_{poke.nature}_{s_moves}"
    return hashlib.md5(data.encode('utf-8')).hexdigest()

def _hash_team_variant(set_ids: List[str]) -> str:
    return hashlib.md5(",".join(sorted(set_ids)).encode('utf-8')).hexdigest()

def get_all_matches():
    session = SessionLocal()
    try:
        matches = session.query(Match).all()
        result = []
        for m in matches:
            result.append({
                "id": m.id,
                "format": m.format,
                "timestamp": m.timestamp,
                "teams_count": len(m.teams)
            })
        return result
    finally:
        session.close()

def search_matches(query_text: str = "", player_filter: str = "", species_filter: str = "", limit: int = 20, offset: int = 0) -> tuple[List[Dict[str, Any]], int]:
    session = SessionLocal()
    try:
        q = session.query(Match)

        if query_text:
            q = q.filter(Match.id.ilike(f"%{query_text}%"))

        if player_filter:
            q = q.filter(Match.teams.any(MatchTeam.trainer_id.ilike(f"%{player_filter}%")))

        # For species filter, we'll do a basic text search on the JSON if needed, or skip for now if too complex in SQLite.
        # SQLite json_extract or LIKE on JSON string:
        if species_filter:
            # First find sets that match the species
            matching_sets = session.query(PokemonSet.id).filter(PokemonSet.species_id.ilike(f"%{species_filter}%")).all()
            set_ids = [s.id for s in matching_sets]
            # Then find variants that contain these sets
            if set_ids:
                q = q.filter(Match.teams.any(MatchTeam.team_variant_id.in_(
                    session.query(TeamVariant.id).filter(
                        or_(*[TeamVariant.pokemon_set_ids.like(f'%"{sid}"%') for sid in set_ids])
                    )
                )))

        total_count = q.count()
        matches = q.offset(offset).limit(limit).all()
        
        variant_ids = set()
        for m in matches:
            for t in m.teams:
                variant_ids.add(t.team_variant_id)
                
        variants = session.query(TeamVariant).filter(TeamVariant.id.in_(variant_ids)).all()
        set_ids = set()
        for v in variants:
            if v.pokemon_set_ids:
                set_ids.update(v.pokemon_set_ids)
                
        sets = session.query(PokemonSet).filter(PokemonSet.id.in_(set_ids)).all()
        set_species = {s.id: s.species_id for s in sets}
        
        variant_species_str = {}
        for v in variants:
            sp_list = []
            if v.pokemon_set_ids:
                for sid in v.pokemon_set_ids:
                    sp_list.append(set_species.get(sid, "?").capitalize())
            variant_species_str[v.id] = ", ".join(sp_list)
        
        results = []
        for m in matches:
            p1 = next((t.trainer_id for t in m.teams if t.player_slot == "p1"), "P1 Sconosciuto")
            p2 = next((t.trainer_id for t in m.teams if t.player_slot == "p2"), "P2 Sconosciuto")
            
            p1_t = next((t for t in m.teams if t.player_slot == "p1"), None)
            p2_t = next((t for t in m.teams if t.player_slot == "p2"), None)
            
            p1_team_str = variant_species_str.get(p1_t.team_variant_id, "") if p1_t else ""
            p2_team_str = variant_species_str.get(p2_t.team_variant_id, "") if p2_t else ""

            results.append({
                "id": m.id,
                "p1": p1,
                "p2": p2,
                "p1_team": p1_team_str,
                "p2_team": p2_team_str,
                "turns_count": len(m.turns)
            })
        return results, total_count
    finally:
        session.close()

def get_match_details(match_id: str) -> Optional[Dict[str, Any]]:
    session = SessionLocal()
    try:
        match = session.query(Match).filter_by(id=match_id).first()
        if not match:
            return None

        teams_data = {}
        set_id_to_species = {}

        for team in match.teams:
            p_slot = team.player_slot
            poke_list = []
            
            variant = session.query(TeamVariant).filter_by(id=team.team_variant_id).first()
            if variant:
                for sid in variant.pokemon_set_ids:
                    p_set = session.query(PokemonSet).filter_by(id=sid).first()
                    if p_set:
                        set_id_to_species[sid] = f"{p_set.species_id.capitalize()}"
                        poke_list.append({
                            "id": p_set.id,
                            "species": p_set.species_id.capitalize(),
                            "ability": p_set.ability_id or "Non rivelata",
                            "item": p_set.item_id or "Non rivelato",
                            "tera_type": p_set.tera_type or "Non rivelato",
                            "nature": p_set.nature or "Sconosciuta",
                            "moves": p_set.moves.split(",") if p_set.moves else [],
                            "is_brought": False, # Would come from summary
                            "base_stats": {} 
                        })
            
            trainer_obj = session.query(Trainer).filter_by(id=team.trainer_id).first()
            rating = trainer_obj.rating if trainer_obj and trainer_obj.rating else "N/A"
            
            teams_data[p_slot] = {
                "trainer": team.trainer_id,
                "rating": rating,
                "pokemon": poke_list
            }

        turns_data = []
        for t in match.turns:
            actions = []
            for a in t.actions:
                actions.append({
                    "order": a.action_order,
                    "type": a.action_type,
                    "actor": set_id_to_species.get(a.actor_set_id, "—"),
                    "target": set_id_to_species.get(a.target_set_id, "—"),
                    "board_state": {
                        "p1a": {"id": a.active_p1a_id, "name": set_id_to_species.get(a.active_p1a_id, "Vuoto")},
                        "p1b": {"id": a.active_p1b_id, "name": set_id_to_species.get(a.active_p1b_id, "Vuoto")},
                        "p2a": {"id": a.active_p2a_id, "name": set_id_to_species.get(a.active_p2a_id, "Vuoto")},
                        "p2b": {"id": a.active_p2b_id, "name": set_id_to_species.get(a.active_p2b_id, "Vuoto")},
                    },
                    "details": a.details or "",
                    "tags": a.tags or {}
                })

            turns_data.append({
                "turn_number": t.turn_number,
                "weather": t.weather,
                "terrain": t.terrain,
                "trick_room": t.trick_room,
                "p1_tailwind": t.p1_tailwind,
                "p2_tailwind": t.p2_tailwind,
                "actions": actions
            })

        return {
            "match_id": match.id,
            "format": match.format,
            "teams": teams_data,
            "turns": turns_data
        }
    finally:
        session.close()

def save_parsed_match_to_db(parsed_match, match_id_str: str):
    session = SessionLocal()
    try:
        print("-> [REPO] Avvio salvataggio match nel DB...")
        
        # Gestione del Match
        db_match = session.query(Match).filter_by(id=match_id_str).first()
        if not db_match:
            db_match = Match(id=match_id_str, format=parsed_match.format)
            if getattr(parsed_match, "winner_name", None) and parsed_match.winner_name != 'tie':
                db_match.winner_id = parsed_match.winner_name
            session.add(db_match)
            session.flush()

        poke_tracking = {}
        brought_p1 = set()
        brought_p2 = set()

        print("-> [REPO] Leggo i giocatori e i set...")
        for player_slot, player_data in parsed_match.players.items():
            db_trainer = session.query(Trainer).filter_by(id=player_data.name).first()
            if not db_trainer:
                db_trainer = Trainer(id=player_data.name, rating=player_data.rating)
                session.add(db_trainer)
                session.flush()
            else:
                if player_data.rating is not None:
                    db_trainer.rating = player_data.rating

            set_ids = []
            for poke in player_data.team:
                set_id = _hash_pokemon_set(poke)
                set_ids.append(set_id)
                
                db_set = session.query(PokemonSet).filter_by(id=set_id).first()
                if not db_set:
                    db_set = PokemonSet(
                        id=set_id,
                        species_id=to_id(poke.species),
                        ability_id=to_id(poke.ability),
                        item_id=to_id(poke.item),
                        tera_type=poke.tera_type,
                        nature=poke.nature if getattr(poke, 'nature', "") else "Hardy",
                        moves=",".join([to_id(m) for m in poke.moves]) if poke.moves else None
                    )
                    session.add(db_set)
                    session.flush()

                tracking_key = f"{player_slot}: {poke.species.lower()}"
                poke_tracking[tracking_key] = db_set.id

            variant_id = _hash_team_variant(set_ids)
            db_variant = session.query(TeamVariant).filter_by(id=variant_id).first()
            if not db_variant:
                db_variant = TeamVariant(id=variant_id, pokemon_set_ids=set_ids)
                session.add(db_variant)
                session.flush()

            db_team = MatchTeam(match_id=match_id_str, trainer_id=db_trainer.id, player_slot=player_slot, team_variant_id=variant_id)
            session.add(db_team)
            session.flush()

        def get_set_id(raw_str: str) -> Optional[str]:
            if not raw_str: return None
            if ":" in raw_str:
                parts = raw_str.split(":")
                p_slot = parts[0][:2]
                species = parts[1].split(',')[0].strip().lower()
                res = poke_tracking.get(f"{p_slot}: {species}")
                if res: return res
                for k, v in poke_tracking.items():
                    if k.startswith(f"{p_slot}:"):
                        base_species = k.split(': ')[1]
                        sid = to_id(species)
                        bid = to_id(base_species)
                        if sid and bid and (sid in bid or bid in sid):
                            return v
                return None
            
            species = raw_str.split(',')[0].strip().lower()
            for k, v in poke_tracking.items():
                if k.endswith(f": {species}"): return v
            return None

        total_turns = 0
        for turn_num, actions in parsed_match.turns.items():
            total_turns += 1
            db_turn = Turn(
                match_id=match_id_str,
                turn_number=turn_num,
                trick_room=parsed_match.global_state.trick_room,
                p1_tailwind=parsed_match.global_state.tailwind_p1,
                p2_tailwind=parsed_match.global_state.tailwind_p2
            )
            session.add(db_turn)
            session.flush()

            for order_idx, act in enumerate(actions):
                if act.action_type in ("switch", "drag"):
                    if act.actor and act.actor.startswith("p1"): brought_p1.add(get_set_id(act.actor))
                    if act.actor and act.actor.startswith("p2"): brought_p2.add(get_set_id(act.actor))

                move_id_val = None
                if act.action_type == 'move':
                    move_id_val = to_id(act.details)

                db_action = TurnAction(
                    turn_id=db_turn.id,
                    action_order=order_idx,
                    action_type=act.action_type,
                    move_id=move_id_val,
                    actor_set_id=get_set_id(act.actor),
                    target_set_id=get_set_id(act.target),
                    active_p1a_id=get_set_id(f"p1: {act.board_state.p1p1}") if act.board_state.p1p1 else None,
                    active_p1b_id=get_set_id(f"p1: {act.board_state.p1p2}") if act.board_state.p1p2 else None,
                    active_p2a_id=get_set_id(f"p2: {act.board_state.p2p1}") if act.board_state.p2p1 else None,
                    active_p2b_id=get_set_id(f"p2: {act.board_state.p2p2}") if act.board_state.p2p2 else None,
                    ability_activated=getattr(act, 'ability_activated', None),
                    item_consumed=getattr(act, 'item_consumed', None),
                    tags=act.tags,
                    details=act.details
                )
                session.add(db_action)
                session.flush()

                if hasattr(act, 'effects'):
                    for target_raw_id, eff in act.effects.items():
                        target_s_id = get_set_id(target_raw_id)
                        db_effect = ActionEffect(
                            turn_action_id=db_action.id,
                            target_set_id=target_s_id,
                            damage_percent=eff.damage_percent,
                            stat_changes=eff.stat_changes,
                            status_inflicted=eff.status_inflicted,
                            is_crit=eff.is_crit,
                            effectiveness=eff.effectiveness,
                            ability_activated=eff.ability_activated,
                            item_consumed=eff.item_consumed,
                            is_protected=eff.is_protected
                        )
                        session.add(db_effect)
                        
        db_summary = MatchSummary(
            match_id=match_id_str,
            p1_brought_pokemon=list(brought_p1),
            p2_brought_pokemon=list(brought_p2),
            total_turns=total_turns
            # p1_archetypes could be calculated here via static analysis
        )
        session.add(db_summary)

        print("-> [REPO] Sto per eseguire il COMMIT finale...")
        session.commit()
        print("-> [REPO] COMMIT completato con successo!")
    except Exception as e:
        session.rollback()
        print(f"-> [REPO] !!! CRASH NEL REPOSITORY !!! Errore: {type(e).__name__} - {str(e)}")
        raise e
    finally:
        session.close()

def delete_match(match_id: str) -> bool:
    session = SessionLocal()
    try:
        match = session.query(Match).filter_by(id=match_id).first()
        if match:
            session.delete(match)
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        return False
    finally:
        session.close()

def clear_all_matches() -> bool:
    session = SessionLocal()
    try:
        matches = session.query(Match).all()
        for match in matches:
            session.delete(match)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        return False
    finally:
        session.close()
