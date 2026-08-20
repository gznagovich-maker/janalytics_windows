import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# 1. Calcola il percorso assoluto basato sulla posizione di questo file
# (Questo assicura che il db sia sempre nella root del progetto PokemonLogParser)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "vgc_replays.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

# 2. Imposta echo=True. Questo stamperà a schermo TUTTE le query (CREATE TABLE, INSERT, ecc.)
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def init_db():
    """Inizializza il database creando le tabelle se non esistono."""
    Base.metadata.create_all(bind=engine)