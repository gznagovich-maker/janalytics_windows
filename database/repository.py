from typing import Optional, List, Dict, Any
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from database.connection import SessionLocal
from database.models import Match, Team, PokemonBuild, Turn, TurnAction, Trainer

def get_all_matches():
    """Recupera tutti i match salvati nel DB."""
    session = SessionLocal()
    try:
        matches = session.query(Match).all()
        # Estraiamo i dati utili prima di chiudere la sessione
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


from typing import Optional, List, Dict, Any
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from database.connection import SessionLocal
from database.models import Match, Team, PokemonBuild, Turn, TurnAction, Trainer


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

            # Raccogliamo le specie presenti nei team
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

        # Mappa per convertire ID del PokemonBuild in stringa leggibile (es: "Incineroar")
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
                    "ability": pb.ability or "Non rivelata",
                    "item": pb.item or "Non rivelato",
                    "tera_type": pb.tera_type or "Non rivelato",
                    "is_brought": pb.is_brought
                })
            teams_data[p_slot] = {
                "trainer": team.trainer_id,
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
                        "p1a": build_id_to_species.get(a.active_p1a_id, "Vuoto"),
                        "p1b": build_id_to_species.get(a.active_p1b_id, "Vuoto"),
                        "p2a": build_id_to_species.get(a.active_p2a_id, "Vuoto"),
                        "p2b": build_id_to_species.get(a.active_p2b_id, "Vuoto"),
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
            "teams": teams_data,
            "turns": turns_data
        }
    finally:
        session.close()

def save_parsed_match_to_db(parsed_match, match_id_str: str):
    session = SessionLocal()
    try:
        print("-> [REPO] Avvio salvataggio match nel DB...")
        db_match = Match(id=match_id_str)
        session.add(db_match)

        poke_tracking = {}

        print("-> [REPO] Leggo i giocatori dal parser...")
        # Se si blocca qui, significa che 'parsed_match' non ha l'attributo 'players'
        for player_slot, player_data in parsed_match.players.items():
            print(f"-> [REPO] Trovato giocatore: {player_data.name} nello slot {player_slot}")

            db_trainer = session.query(Trainer).filter_by(id=player_data.name).first()
            if not db_trainer:
                db_trainer = Trainer(id=player_data.name)
                session.add(db_trainer)
                session.flush()

            db_team = Team(match_id=match_id_str, trainer_id=db_trainer.id, player_slot=player_slot)
            session.add(db_team)
            session.flush()

            print(f"-> [REPO] Inserisco i Pokemon per {player_data.name}...")
            # Se si blocca qui, significa che 'player_data' non ha l'attributo 'team'
            for poke in player_data.team:
                db_poke = PokemonBuild(
                    team_id=db_team.id,
                    species_id=poke.species.lower(),
                    ability=poke.ability,
                    item=poke.item,
                    tera_type=poke.tera_type
                )
                session.add(db_poke)
                session.flush()
                tracking_key = f"{player_slot}: {poke.species}"
                poke_tracking[tracking_key] = db_poke.id

        print("-> [REPO] Inserisco i turni e le azioni...")
        # Se si blocca qui, 'parsed_match' non ha l'attributo 'turns' o 'global_state'
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

            # ... (il resto del ciclo per le azioni rimane uguale) ...

        print("-> [REPO] Sto per eseguire il COMMIT finale...")
        session.commit()
        print("-> [REPO] COMMIT completato con successo!")
    except Exception as e:
        session.rollback()
        print(f"-> [REPO] !!! CRASH NEL REPOSITORY !!! Errore: {type(e).__name__} - {str(e)}")
        raise e
    finally:
        session.close()
