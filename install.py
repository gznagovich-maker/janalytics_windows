import sys
from database.connection import init_db
from database.metadata_sync import sync_metadata
from database.pokedex_sync import sync_pokedex

def main():
    print("=" * 50)
    print("Inizializzazione Database di VGC Replay Analyzer")
    print("=" * 50)
    print("\n[1/3] Creazione delle tabelle...")
    init_db()
    
    print("\n[2/3] Sincronizzazione di Abilità, Strumenti e Mosse...")
    sync_metadata()
    
    print("\n[3/3] Sincronizzazione del Pokédex...")
    sync_pokedex()
    
    print("\n" + "=" * 50)
    print("Installazione completata con successo!")
    print("Ora puoi avviare l'applicazione principale (main.py).")
    print("=" * 50)

if __name__ == "__main__":
    main()
