# test_db.py
import uuid
from src.parser.showdown import ShowdownParser, parse_showdown_log
from database.connection import init_db, SessionLocal
from database.repository import save_parsed_match_to_db
from database.models import Match, PokemonBuild, TurnAction

# 1. Inizializza il database (crea il file vgc_replays.db e le tabelle)
init_db()

# 2. Il tuo log di test
SAMPLE_LOG = """
|j|☆7upikid
|j|☆jirkunow
|t:|1781093457
|gametype|doubles
|player|p1|7upikid|lucas-gen4pt|1069
|player|p2|jirkunow|dancer|1080
|gen|9
|tier|[Gen 9 Champions] VGC 2026 Reg M-A (Bo3)
|poke|p1|Chandelure, L50, M|
|poke|p1|Kangaskhan, L50, F|
|poke|p1|Sneasler, L50, M|
|poke|p1|Torkoal, L50, M|
|poke|p1|Starmie, L50|
|poke|p1|Forretress, L50, F|
|poke|p2|Floette-Eternal, L50, F|
|poke|p2|Sinistcha, L50|
|poke|p2|Maushold-Four, L50|
|poke|p2|Primarina, L50, M|
|poke|p2|Incineroar, L50, M|
|poke|p2|Corviknight, L50, F|
|start
|switch|p1a: Kangaskhan|Kangaskhan, L50, F|100/100
|switch|p1b: Starmie|Starmie, L50|100/100
|switch|p2a: Floette|Floette-Eternal, L50, F|100/100
|switch|p2b: Incineroar|Incineroar, L50, M|100/100
|turn|1
|move|p1a: Kangaskhan|Fake Out|p2a: Floette
|-damage|p2a: Floette|81/100
"""


def run_test():
    print("Avvio il parsing...")
    parser = ShowdownParser()
    parsed_data = parse_showdown_log(SAMPLE_LOG)

    # --- NUOVO: VERIFICA DEL PARSER ---
    print("\n--- RISULTATO DEL PARSER ---")
    print(f"Giocatori trovati: {list(parsed_data.players.keys())}")
    for p_id, p_data in parsed_data.players.items():
        print(f"[{p_id}] {p_data.name} ha {len(p_data.team)} Pokemon")
    print(f"Turni estratti: {len(parsed_data.turns)}")
    print("----------------------------\n")

    match_id = f"test-match-{uuid.uuid4().hex[:8]}"
    print(f"Salvataggio nel database con ID: {match_id}...")
    try:
        # FASE 1: Salvataggio (il repository apre e chiude la sua sessione)
        save_parsed_match_to_db(parsed_data, match_id)
        print("Salvataggio completato con successo!\n")
    except Exception as e:
        print(f"ERRORE DURANTE IL SALVATAGGIO: {e}")
        return  # Se fallisce qui, fermiamo lo script per non causare altri errori

    # FASE 2: Verifica della lettura
    session = SessionLocal()
    try:
        saved_match = session.query(Match).filter_by(id=match_id).first()
        print(f"Match Trovato: {saved_match.id}")

        builds = session.query(PokemonBuild).filter(PokemonBuild.team.has(match_id=match_id)).all()
        print(f"Pokemon salvati per questo match: {len(builds)}")
        for b in builds[:4]:
            print(f" - {b.species_id} (Team ID: {b.team_id})")

        actions = session.query(TurnAction).filter(TurnAction.turn.has(match_id=match_id)).all()
        print(f"\nAzioni di turno salvate: {len(actions)}")
        for a in actions:
            print(f" - Turno {a.turn.turn_number}, Azione: {a.action_type}")

    except Exception as e:
        print(f"ERRORE DURANTE LA LETTURA: {e}")
    finally:
        # Ora è sicuro chiamare close() perché session è stata definita fuori dal try
        session.close()

# ... (tutto il resto del file, inclusa la def run_test(): ) ...

if __name__ == "__main__":
    run_test()