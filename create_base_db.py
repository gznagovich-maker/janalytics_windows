import os
import sqlite3
from pathlib import Path

# Imposta temporaneamente la variabile per forzare SQLite nel file base
os.environ["DATABASE_URL"] = "sqlite:///base_metadata.db"

from database.connection import init_db
from database.seed_v2_metadata import seed_v2_metadata
from database.seed_tags import seed_tags

def create_base():
    base_file = Path("base_metadata.db")
    if base_file.exists():
        base_file.unlink()
        
    print("Creazione del database SQLite base...")
    init_db()
    
    print("Popolamento metadati (Pokemon, Mosse, Abilità, Tag)...")
    seed_v2_metadata()
    try:
        seed_tags()
    except Exception as e:
        print(f"Errore seed tags (opzionale): {e}")
        
    print("FATTO! Il file 'base_metadata.db' è pronto per essere distribuito.")

if __name__ == "__main__":
    create_base()
