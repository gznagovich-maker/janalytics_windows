"""
pg_extensions.py
================
Attivazione delle estensioni PostgreSQL necessarie per JAnalytics.

Esegui questo script UNA SOLA VOLTA dopo aver creato il database PG:
  python database/pg_extensions.py

Estensioni attivate:
  - pg_trgm:   Indici trigram per ricerca full-text fuzzy (nomi Pokémon, trainer)
  - btree_gin: Indici GIN su colonne B-Tree (ottimizza query su JSONB con filtri scalar)

Nota: richiede privilegi superuser o pg_extension_owner.
"""

import sys
from pathlib import Path

# Forza UTF-8 su stdout (Windows cp1252 non supporta ✓ ⚠)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = str(Path(__file__).parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import text
from database.connection import engine, test_connection


EXTENSIONS = [
    ("pg_trgm",   "Ricerca fuzzy trigram su nomi e ID"),
    ("btree_gin", "Indici GIN su colonne scalari + JSONB"),
    ("unaccent",  "Ricerca case-insensitive con accenti (facoltativa)"),
]

GIN_INDEXES = [
    # Indice GIN su raw_tags JSONB per query come raw_tags @> '{"key": "value"}'
    """
    CREATE INDEX IF NOT EXISTS idx_turn_action_raw_tags_gin
        ON turn_action_v2 USING GIN (raw_tags)
        WHERE raw_tags IS NOT NULL
    """,
    # Indice GIN su abilities_json JSONB per ricerche per abilità
    """
    CREATE INDEX IF NOT EXISTS idx_species_abilities_gin
        ON pokemon_species_v2 USING GIN (abilities_json)
        WHERE abilities_json IS NOT NULL
    """,
    # Indice trigram su trainer_v2.id per ricerca parziale
    """
    CREATE INDEX IF NOT EXISTS idx_trainer_id_trgm
        ON trainer_v2 USING GIN (id gin_trgm_ops)
    """,
    # Indice trigram su match_v2.id per ricerca parziale
    """
    CREATE INDEX IF NOT EXISTS idx_match_id_trgm
        ON match_v2 USING GIN (id gin_trgm_ops)
    """,
]


def setup_extensions() -> None:
    print("Attivazione estensioni PostgreSQL...")
    with engine.begin() as conn:
        for ext_name, description in EXTENSIONS:
            try:
                conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext_name}"))
                print(f"  ✓ {ext_name}: {description}")
            except Exception as e:
                print(f"  ⚠ {ext_name}: {e} (potrebbe richiedere privilegi superuser)")

    print("\nCreazione indici GIN avanzati...")
    with engine.begin() as conn:
        for idx_sql in GIN_INDEXES:
            try:
                conn.execute(text(idx_sql.strip()))
                print(f"  ✓ indice creato")
            except Exception as e:
                print(f"  ⚠ Indice saltato: {e}")

    print("\n✅ Setup estensioni completato.")


if __name__ == "__main__":
    if not test_connection():
        print("[ERRORE] Impossibile connettersi al database.")
        sys.exit(1)
    setup_extensions()
