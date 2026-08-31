"""
materialized_views.py
=====================
Gestione delle Materialized Views PostgreSQL per JAnalytics.

Le MV pre-calcolano le statistiche più richieste (usage per specie,
usage per mossa) in modo da renderle disponibili in <5ms invece di
dover rieseguire JOIN a cascata su decine di migliaia di righe.

Uso:
  python database/materialized_views.py --create   # Crea le MV
  python database/materialized_views.py --refresh  # Aggiorna i dati
  python database/materialized_views.py --status   # Verifica esistenza e data ultimo refresh
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Forza UTF-8 su stdout (Windows cp1252 non supporta caratteri Unicode)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = str(Path(__file__).parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import text
from database.connection import engine, test_connection


# ──────────────────────────────────────────────────────────────────────────────
# Definizione delle Materialized Views
# ──────────────────────────────────────────────────────────────────────────────

MV_DEFINITIONS = {

    "mv_species_usage": {
        "description": "Usage rate per specie per formato (join pre-calcolato)",
        "create_sql": """
            CREATE MATERIALIZED VIEW IF NOT EXISTS mv_species_usage AS
            SELECT
                mv.format,
                pb.species_id,
                COUNT(tvb.build_id)                         AS occurrences,
                ps.name                                     AS species_name,
                ps.type1,
                ps.type2,
                ps.sprite_url,
                ps.bst_hp, ps.bst_atk, ps.bst_def,
                ps.bst_spa, ps.bst_spd, ps.bst_spe
            FROM match_v2 mv
            JOIN match_team_v2 mt  ON mt.match_id          = mv.id
            JOIN team_variant_build tvb ON tvb.team_variant_id = mt.team_variant_id
            JOIN pokemon_build pb  ON pb.id                = tvb.build_id
            LEFT JOIN pokemon_species_v2 ps ON ps.id       = pb.species_id
            GROUP BY mv.format, pb.species_id,
                     ps.name, ps.type1, ps.type2, ps.sprite_url,
                     ps.bst_hp, ps.bst_atk, ps.bst_def,
                     ps.bst_spa, ps.bst_spd, ps.bst_spe
            WITH DATA
        """,
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_mv_species_format          ON mv_species_usage(format)",
            "CREATE INDEX IF NOT EXISTS idx_mv_species_usage_occ       ON mv_species_usage(format, occurrences DESC)",
            "CREATE INDEX IF NOT EXISTS idx_mv_species_species_id      ON mv_species_usage(species_id)",
        ],
    },

    "mv_move_usage": {
        "description": "Usage rate per mossa per formato",
        "create_sql": """
            CREATE MATERIALIZED VIEW IF NOT EXISTS mv_move_usage AS
            SELECT
                mv.format,
                pbm.move_id,
                COUNT(pbm.build_id)   AS occurrences,
                m.name                AS move_name,
                m.type                AS move_type,
                m.category            AS move_category,
                m.base_power
            FROM match_v2 mv
            JOIN match_team_v2 mt      ON mt.match_id         = mv.id
            JOIN team_variant_build tvb ON tvb.team_variant_id = mt.team_variant_id
            JOIN pokemon_build_move pbm ON pbm.build_id        = tvb.build_id
            LEFT JOIN move_v2 m         ON m.id               = pbm.move_id
            GROUP BY mv.format, pbm.move_id,
                     m.name, m.type, m.category, m.base_power
            WITH DATA
        """,
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_mv_move_format     ON mv_move_usage(format)",
            "CREATE INDEX IF NOT EXISTS idx_mv_move_usage_occ  ON mv_move_usage(format, occurrences DESC)",
            "CREATE INDEX IF NOT EXISTS idx_mv_move_move_id    ON mv_move_usage(move_id)",
        ],
    },

    "mv_build_usage": {
        "description": "Build più usate per specie per formato",
        "create_sql": """
            CREATE MATERIALIZED VIEW IF NOT EXISTS mv_build_usage AS
            SELECT
                mv.format,
                pb.id                           AS build_id,
                pb.species_id,
                pb.ability_id,
                pb.item_id,
                pb.tera_type,
                pb.nature,
                COUNT(tvb.build_id)             AS occurrences
            FROM match_v2 mv
            JOIN match_team_v2 mt       ON mt.match_id         = mv.id
            JOIN team_variant_build tvb  ON tvb.team_variant_id = mt.team_variant_id
            JOIN pokemon_build pb        ON pb.id              = tvb.build_id
            GROUP BY mv.format, pb.id, pb.species_id, pb.ability_id,
                     pb.item_id, pb.tera_type, pb.nature
            WITH DATA
        """,
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_mv_build_format     ON mv_build_usage(format)",
            "CREATE INDEX IF NOT EXISTS idx_mv_build_species    ON mv_build_usage(format, species_id)",
            "CREATE INDEX IF NOT EXISTS idx_mv_build_usage_occ  ON mv_build_usage(format, species_id, occurrences DESC)",
        ],
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# Funzioni
# ──────────────────────────────────────────────────────────────────────────────

def create_all_views() -> None:
    """Crea le materialized views e i loro indici (idempotente)."""
    print("Creazione Materialized Views...")
    with engine.begin() as conn:
        for name, mv in MV_DEFINITIONS.items():
            print(f"  → {name}: {mv['description']}")
            conn.execute(text(mv["create_sql"]))
            for idx_sql in mv["indexes"]:
                conn.execute(text(idx_sql))
            print(f"     ✓ creata con {len(mv['indexes'])} indici")
    print("✅ Tutte le MV create.")


def refresh_all_views(concurrently: bool = True) -> None:
    """
    Aggiorna i dati delle materialized views.
    Con concurrently=True, il refresh non blocca le letture in corso
    (richiede almeno un indice UNIQUE sulla MV).
    """
    mode = "CONCURRENTLY" if concurrently else ""
    print(f"Refresh Materialized Views ({mode or 'blocking'})...")
    start = datetime.now(timezone.utc)
    with engine.begin() as conn:
        for name in MV_DEFINITIONS:
            try:
                conn.execute(text(f"REFRESH MATERIALIZED VIEW {mode} {name}"))
                print(f"  ✓ {name}")
            except Exception as e:
                print(f"  ✗ {name}: {e}")
    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    print(f"✅ Refresh completato in {elapsed:.2f}s")


def get_status() -> None:
    """Mostra lo stato (esistenza, numero di righe) di ogni MV."""
    print("Stato Materialized Views:")
    with engine.connect() as conn:
        for name in MV_DEFINITIONS:
            try:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar()
                print(f"  ✓ {name}: {result:,} righe")
            except Exception:
                print(f"  ✗ {name}: non esiste (esegui --create)")


def drop_all_views() -> None:
    """Elimina tutte le materialized views (per reset)."""
    with engine.begin() as conn:
        for name in reversed(list(MV_DEFINITIONS.keys())):
            conn.execute(text(f"DROP MATERIALIZED VIEW IF EXISTS {name} CASCADE"))
            print(f"  ✓ {name} eliminata")
    print("✅ Tutte le MV eliminate.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gestione Materialized Views JAnalytics")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--create",  action="store_true", help="Crea le MV")
    group.add_argument("--refresh", action="store_true", help="Aggiorna i dati")
    group.add_argument("--status",  action="store_true", help="Verifica stato")
    group.add_argument("--drop",    action="store_true", help="Elimina le MV")
    args = parser.parse_args()

    if not test_connection():
        print("[ERRORE] Impossibile connettersi al database.")
        sys.exit(1)

    if args.create:
        create_all_views()
    elif args.refresh:
        refresh_all_views(concurrently=False)  # Non-concurrent (no UNIQUE idx)
    elif args.status:
        get_status()
    elif args.drop:
        drop_all_views()
