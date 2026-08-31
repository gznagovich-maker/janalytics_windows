"""
alembic/env.py — Configurazione Alembic per JAnalytics PostgreSQL
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# ──────────────────────────────────────────────────────────────────────────────
# Aggiunge la root del progetto al path per importare i modelli
# ──────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT = str(Path(__file__).parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Importa Base e tutti i modelli V2 (necessario per autogenerate)
from database.connection import Base, DATABASE_URL  # noqa: E402
import database.models_v2  # noqa: F401 — registra i modelli nel metadata

# ──────────────────────────────────────────────────────────────────────────────
# Config Alembic
# ──────────────────────────────────────────────────────────────────────────────
config = context.config

# Sovrascrive sqlalchemy.url dall'alembic.ini con il valore da .env
config.set_main_option("sqlalchemy.url", DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Esegue le migration in modalità 'offline' (genera SQL senza connessione)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Esegue le migration connettendosi al database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,      # Rileva cambio di tipo colonna
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
