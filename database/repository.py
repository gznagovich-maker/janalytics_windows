from typing import Optional, List, Dict, Any
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from database.connection import SessionLocal
from database.models import Match, Team, PokemonBuild, Turn, TurnAction, Trainer, ActionEffect
import json
import re

def to_id(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'[^a-z0-9]', '', text.lower())

def get_all_matches():
    """Recupera tutti i match salvati nel DB."""
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

def search_matches(query_text: str = "", player_filter: str = "", species_filter: str = "") -> List[Dict[str, Any]]:
    """Recupera i match filtrati per ID/Nome, Giocatore o Specie Pokémon."""
    session = SessionLocal()
    try:
        q = session.query(Match)

        if query_text:
            q = q.filter(Match.id.ilike(f"%{query_text}%"))

        if player_filter:
            q = q.filter(Match.teams.any(Team.trainer_id.ilike(f"%{player_filter}%")))

        if species_filter:
            q = q.filter(Match.teams.any(
                Team.pokemon_builds.any(PokemonBuild.species_id.ilike(f"%{species_filter}%"))
            ))

        matches = q.all()
        results = []
        for m in matches:
            p1 = next((t.trainer_id for t in m.teams if t.player_slot == "p1"), "P1 Sconosciuto")
            p2 = next((t.trainer_id for t in m.teams if t.player_slot == "p2"), "P2 Sconosciuto")

            p1_team = [p.species_id for t in m.teams if t.player_slot == "p1" for p in t.pokemon_builds]
            p2_team = [p.species_id for t in m.teams if t.player_slot == "p2" for p in t.pokemon_builds]

            results.append({
                "id": m.id,
                "p1": p1,
                "p2": p2,
                "p1_team": ", ".join(p1_team),
                "p2_team": ", ".join(p2_team),
                "turns_count": len(m.turns)
            })
        return results
    finally:
        session.close()

def get_match_details(match_id: str) -> Optional[Dict[str, Any]]:
    """Recupera la struttura completa di un match: Team, Turni, Stato della Board per ogni azione."""
    session = SessionLocal()
    try:
        match = session.query(Match).filter_by(id=match_id).first()
        if not match:
            return None

        build_id_to_species = {}
        teams_data = {}

        for team in match.teams:
            p_slot = team.player_slot
            poke_list = []
            for pb in team.pokemon_builds:
                build_id_to_species[pb.id] = f"{pb.species_id.capitalize()}"
                poke_list.append({
                    "id": pb.id,
                    "species": pb.species_id.capitalize(),
                    "ability": pb.ability.name if pb.ability else (pb.ability_id or "Non rivelata"),
                    "item": pb.item.name if pb.item else (pb.item_id or "Non rivelato"),
                    "tera_type": pb.tera_type or "Non rivelato",
                    "nature": pb.nature or "Sconosciuta",
                    "moves": pb.moves.split(",") if pb.moves else [],
                    "is_brought": pb.is_brought,
                    "base_stats": pb.species.base_stats if pb.species and pb.species.base_stats else {}
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
                    "actor": build_id_to_species.get(a.actor_build_id, "—"),
                    "target": build_id_to_species.get(a.target_build_id, "—"),
                    "board_state": {
                        "p1a": {"id": a.active_p1a_id, "name": build_id_to_species.get(a.active_p1a_id, "Vuoto")},
                        "p1b": {"id": a.active_p1b_id, "name": build_id_to_species.get(a.active_p1b_id, "Vuoto")},
                        "p2a": {"id": a.active_p2a_id, "name": build_id_to_species.get(a.active_p2a_id, "Vuoto")},
                        "p2b": {"id": a.active_p2b_id, "name": build_id_to_species.get(a.active_p2b_id, "Vuoto")},
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
        db_match = Match(id=match_id_str, format=parsed_match.format)
        session.add(db_match)

        poke_tracking = {}

        print("-> [REPO] Leggo i giocatori dal parser...")
        for player_slot, player_data in parsed_match.players.items():
            print(f"-> [REPO] Trovato giocatore: {player_data.name} nello slot {player_slot}")

            db_trainer = session.query(Trainer).filter_by(id=player_data.name).first()
            if not db_trainer:
                db_trainer = Trainer(id=player_data.name, rating=player_data.rating)
                session.add(db_trainer)
                session.flush()
            else:
                if player_data.rating is not None:
                    db_trainer.rating = player_data.rating

            db_team = Team(match_id=match_id_str, trainer_id=db_trainer.id, player_slot=player_slot)
            session.add(db_team)
            session.flush()

            print(f"-> [REPO] Inserisco i Pokemon per {player_data.name}...")
            for poke in player_data.team:
                db_poke = PokemonBuild(
                    team_id=db_team.id,
                    species_id=to_id(poke.species),
                    ability_id=to_id(poke.ability),
                    item_id=to_id(poke.item),
                    tera_type=poke.tera_type,
                    nature=poke.nature if getattr(poke, 'nature', "") else "Hardy",
                    moves=",".join([to_id(m) for m in poke.moves]) if poke.moves else None
                )
                session.add(db_poke)
                session.flush()
                tracking_key = f"{player_slot}: {poke.species.lower()}"
                poke_tracking[tracking_key] = db_poke.id

        print("-> [REPO] Inserisco i turni e le azioni...")
        def get_build_id(raw_str: str) -> Optional[int]:
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

        for turn_num, actions in parsed_match.turns.items():
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
                move_id_val = None
                if act.action_type == 'move':
                    move_id_val = to_id(act.details)

                db_action = TurnAction(
                    turn_id=db_turn.id,
                    action_order=order_idx,
                    action_type=act.action_type,
                    move_id=move_id_val,
                    actor_build_id=get_build_id(act.actor),
                    target_build_id=get_build_id(act.target),
                    active_p1a_id=get_build_id(f"p1: {act.board_state.p1p1}") if act.board_state.p1p1 else None,
                    active_p1b_id=get_build_id(f"p1: {act.board_state.p1p2}") if act.board_state.p1p2 else None,
                    active_p2a_id=get_build_id(f"p2: {act.board_state.p2p1}") if act.board_state.p2p1 else None,
                    active_p2b_id=get_build_id(f"p2: {act.board_state.p2p2}") if act.board_state.p2p2 else None,
                    ability_activated=getattr(act, 'ability_activated', None),
                    item_consumed=getattr(act, 'item_consumed', None),
                    tags=act.tags,
                    details=act.details
                )
                session.add(db_action)
                session.flush()

                if hasattr(act, 'effects'):
                    for target_raw_id, eff in act.effects.items():
                        target_b_id = get_build_id(target_raw_id)
                        db_effect = ActionEffect(
                            turn_action_id=db_action.id,
                            target_build_id=target_b_id,
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
    """Elimina un match e tutte le sue dipendenze dal database."""
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
        print(f"Errore durante l'eliminazione del match {match_id}: {e}")
        return False
    finally:
        session.close()
