"""
connection.py
=============
Configurazione del database PostgreSQL per JAnalytics.

Legge la variabile d'ambiente DATABASE_URL da:
  1. Variabile d'ambiente del sistema
  2. File .env nella directory base dell'applicazione

Compatibile con esecuzione diretta (Python) e build PyInstaller.
"""

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker

# ──────────────────────────────────────────────────────────────────────────────
# Directory base (compatibile con PyInstaller)
# ──────────────────────────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent.parent

# ──────────────────────────────────────────────────────────────────────────────
# Caricamento variabili d'ambiente da .env (se presente)
# ──────────────────────────────────────────────────────────────────────────────
def _load_dotenv(base_dir: Path) -> None:
    """Carica il file .env senza dipendere obbligatoriamente da python-dotenv."""
    env_file = base_dir / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=str(env_file), override=False)
    except ImportError:
        # Fallback manuale se python-dotenv non è installato
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())

_load_dotenv(BASE_DIR)

# ──────────────────────────────────────────────────────────────────────────────
# URL di connessione
# ──────────────────────────────────────────────────────────────────────────────
# Se c'è un file .env usa quello (es. per il tuo sviluppo in Postgres)
# Altrimenti usa SQLite creando un file locale nel computer dell'utente finale
default_db_path = Path.home() / "JAnalytics" / "vgc_replays.db"
default_db_path.parent.mkdir(parents=True, exist_ok=True)
default_sqlite_url = f"sqlite:///{default_db_path}"

DATABASE_URL: str = os.environ.get("DATABASE_URL", default_sqlite_url)

# Parametri pool configurabili da env
_POOL_SIZE    = int(os.environ.get("DB_POOL_SIZE",    "5"))
_MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW", "10"))
_POOL_TIMEOUT = int(os.environ.get("DB_POOL_TIMEOUT", "30"))
_ECHO         = os.environ.get("DB_ECHO", "false").lower() == "true"

# ──────────────────────────────────────────────────────────────────────────────
# Engine SQLAlchemy
# ──────────────────────────────────────────────────────────────────────────────
# Rimuoviamo gli argomenti specifici di Postgres se stiamo usando SQLite
is_sqlite = DATABASE_URL.startswith("sqlite")

if is_sqlite:
    engine = create_engine(
        DATABASE_URL,
        echo=_ECHO,
        # In SQLite non servono pool complessi e connect_args postgres
    )
else:
    engine = create_engine(
        DATABASE_URL,
        echo=_ECHO,
        pool_size=_POOL_SIZE,
        max_overflow=_MAX_OVERFLOW,
        pool_timeout=_POOL_TIMEOUT,
        pool_pre_ping=True,
        connect_args={"options": "-c timezone=UTC"},
    )

# ──────────────────────────────────────────────────────────────────────────────
# Session factory
# ──────────────────────────────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ──────────────────────────────────────────────────────────────────────────────
# Base dichiarativa ORM
# ──────────────────────────────────────────────────────────────────────────────
Base = declarative_base()


# ──────────────────────────────────────────────────────────────────────────────
# Funzioni di inizializzazione
# ──────────────────────────────────────────────────────────────────────────────
def init_db() -> None:
    """
    Crea tutte le tabelle definite nei modelli (se non esistono già).
    Equivalente a `CREATE TABLE IF NOT EXISTS` per ogni modello mappato.
    Usare Alembic per le migrazioni in produzione.
    """
    Base.metadata.create_all(bind=engine)


def test_connection() -> bool:
    """
    Verifica che la connessione al database sia attiva.
    Restituisce True se OK, False in caso di errore.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"[DB] Errore di connessione: {e}")
        return False


def get_db_info() -> dict:
    """Restituisce informazioni sulla connessione attiva (per debug/UI)."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT current_database(), current_user, version()"
            )).fetchone()
            return {
                "database": result[0],
                "user": result[1],
                "version": result[2].split(",")[0],
                "url": DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL,
            }
    except Exception as e:
        return {"error": str(e)}