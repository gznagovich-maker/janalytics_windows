"""
models_v2.py
============
Nuovi modelli SQLAlchemy per lo schema V2 di JAnalytics.

Cambiamenti principali rispetto a models.py (V1):
  - PokemonSet → PokemonBuild (con tabella di giunzione per le mosse)
  - TeamVariant → tabella di giunzione TeamVariantBuild (no JSON)
  - Tag + tabelle di associazione per Mosse, Abilità, Strumenti
  - TurnBoardState estratto da TurnAction (no duplicazione)
  - TurnFieldCondition rimpiazza le colonne booleane hardcoded
  - ActionEffectStatChange rimpiazza JSON stat_changes
  - MatchBrought + MatchArchetype rimpiazzano JSON in MatchSummary
  - Hash SHA-256 per PokemonBuild e TeamVariant (64 chars)
  - PokemonSpecies: tipi in colonne scalari (no JSON), stat in colonne scalari

Migrazione PostgreSQL (v3):
  - abilities_json / learnset_json → JSONB (indicizzabile con GIN)
  - raw_tags in TurnActionV2 → JSONB
  - timestamp in MatchV2 → DateTime(timezone=True) → TIMESTAMPTZ
  - damage_percent → Numeric(6,2)
  - weight → Numeric(4,3)
  - 15 nuovi Index su FK e colonne di filtro (eliminano sequential scan)
"""

from typing import Optional, List
from sqlalchemy import (
    ForeignKey, String, Integer, SmallInteger, Boolean,
    DateTime, UniqueConstraint, CheckConstraint, Index, Numeric, Column, JSON
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

# -- Fix Compatibilità SQLite vs PostgreSQL --
# Permette a SQLite di interpretare i campi JSONB (specifici di PG) come JSON standard (testo in SQLite)
@compiles(JSONB, 'sqlite')
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.connection import Base


# ──────────────────────────────────────────────────────────────────────────────
# MASTER DATA: Specie Pokémon
# ──────────────────────────────────────────────────────────────────────────────

class PokemonSpeciesV2(Base):
    """
    Dati immutabili di una specie Pokémon.
    Tipi e statistiche base in colonne scalari (non JSON) per query efficienti.
    """
    __tablename__ = "pokemon_species_v2"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    """Showdown ID (es: 'flutter-mane', 'urshifu-rapidstrike')"""

    num: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(128))
    base_species_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("pokemon_species_v2.id"), nullable=True
    )
    forme: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Tipi — colonne scalari, non JSON
    type1: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    type2: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Statistiche base — colonne scalari, indicizzabili
    bst_hp:  Mapped[int] = mapped_column(SmallInteger, default=0)
    bst_atk: Mapped[int] = mapped_column(SmallInteger, default=0)
    bst_def: Mapped[int] = mapped_column(SmallInteger, default=0)
    bst_spa: Mapped[int] = mapped_column(SmallInteger, default=0)
    bst_spd: Mapped[int] = mapped_column(SmallInteger, default=0)
    bst_spe: Mapped[int] = mapped_column(SmallInteger, default=0)

    # Dati aggiuntivi (JSONB per indicizzabilità con GIN)
    abilities_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    learnset_json:  Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    sprite_url:  Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    artwork_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Relationships
    base_species: Mapped[Optional["PokemonSpeciesV2"]] = relationship(
        "PokemonSpeciesV2", remote_side="PokemonSpeciesV2.id"
    )
    builds: Mapped[List["PokemonBuild"]] = relationship(
        "PokemonBuild", back_populates="species"
    )


# ──────────────────────────────────────────────────────────────────────────────
# SISTEMA TAG
# ──────────────────────────────────────────────────────────────────────────────

class Tag(Base):
    """
    Tag semantico usato per classificare Mosse, Abilità, Strumenti, Field
    Conditions, e Archetipi di team.
    """
    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(64))
    """Es: 'archetype', 'weather', 'terrain', 'move_effect', 'ability_effect', 'item_category'"""
    name: Mapped[str] = mapped_column(String(128), unique=True)
    """Es: 'Trick Room', 'weather_setter', 'protection', 'choice'"""

    __table_args__ = (
        UniqueConstraint("category", "name", name="uq_tag_category_name"),
    )


class MoveTag(Base):
    """Associazione Mossa → Tag (many-to-many)."""
    __tablename__ = "move_tag"

    move_id: Mapped[str] = mapped_column(
        ForeignKey("move_v2.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True
    )


class AbilityTag(Base):
    """Associazione Abilità → Tag (many-to-many)."""
    __tablename__ = "ability_tag"

    ability_id: Mapped[str] = mapped_column(
        ForeignKey("ability_v2.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True
    )


class ItemTag(Base):
    """Associazione Strumento → Tag (many-to-many)."""
    __tablename__ = "item_tag"

    item_id: Mapped[str] = mapped_column(
        ForeignKey("item_v2.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True
    )


# ──────────────────────────────────────────────────────────────────────────────
# MOSSE, ABILITÀ, STRUMENTI
# ──────────────────────────────────────────────────────────────────────────────

class MoveV2(Base):
    """Dati di una mossa Pokémon."""
    __tablename__ = "move_v2"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(16))
    base_power: Mapped[int] = mapped_column(SmallInteger, default=0)
    accuracy: Mapped[int] = mapped_column(SmallInteger, default=100)
    priority: Mapped[int] = mapped_column(SmallInteger, default=0)
    pp: Mapped[int] = mapped_column(SmallInteger, default=0)
    target: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    short_desc: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    tags: Mapped[List["Tag"]] = relationship(
        "Tag", secondary="move_tag", lazy="selectin"
    )
    build_usages: Mapped[List["PokemonBuildMove"]] = relationship(
        "PokemonBuildMove", back_populates="move"
    )


class AbilityV2(Base):
    """Dati di un'abilità Pokémon."""
    __tablename__ = "ability_v2"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    short_desc: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    tags: Mapped[List["Tag"]] = relationship(
        "Tag", secondary="ability_tag", lazy="selectin"
    )


class ItemV2(Base):
    """Dati di uno strumento."""
    __tablename__ = "item_v2"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    short_desc: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    sprite_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    tags: Mapped[List["Tag"]] = relationship(
        "Tag", secondary="item_tag", lazy="selectin"
    )


# ──────────────────────────────────────────────────────────────────────────────
# BUILD / SET
# ──────────────────────────────────────────────────────────────────────────────

class PokemonBuild(Base):
    """
    Hash-deduplicato: identità "fuzzy" di un Pokémon (specie+abilità+strumento+tera+natura+moveset).

    EV/IV NON fanno parte dell'identità: lo stesso Miraidon Life Orb con spread diversi
    genera lo stesso build_id. I dettagli dello spread vengono registrati nella tabella
    separata PokemonBuildStats (1-to-many), permettendo di aggregare e confrontare
    le varianti di spread osservate per la stessa build.

    L'ID è uno SHA-256 deterministico calcolato da database.hash_utils.compute_build_hash().
    """
    __tablename__ = "pokemon_build"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    """SHA-256 hex (64 caratteri) — EV/IV esclusi dal calcolo"""

    species_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("pokemon_species_v2.id"), nullable=True
    )
    ability_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("ability_v2.id"), nullable=True
    )
    item_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("item_v2.id"), nullable=True
    )
    tera_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    nature:    Mapped[str] = mapped_column(String(32), default="Hardy")

    # Relationships
    species: Mapped[Optional["PokemonSpeciesV2"]] = relationship(
        "PokemonSpeciesV2", back_populates="builds"
    )
    ability: Mapped[Optional["AbilityV2"]] = relationship("AbilityV2")
    item: Mapped[Optional["ItemV2"]] = relationship("ItemV2")
    move_slots: Mapped[List["PokemonBuildMove"]] = relationship(
        "PokemonBuildMove",
        back_populates="build",
        order_by="PokemonBuildMove.slot",
        cascade="all, delete-orphan"
    )
    stats_observations: Mapped[List["PokemonBuildStats"]] = relationship(
        "PokemonBuildStats",
        back_populates="build",
        cascade="all, delete-orphan"
    )


class PokemonBuildStats(Base):
    """
    Osservazione dello spread EV/IV per una PokemonBuild specifica.
    Relazione 1 (Build) → N (Stats observations).

    Ogni volta che la stessa build viene osservata con uno spread diverso,
    viene aggiunta una nuova riga (o aggiornato l'observed_count se già presente).
    Questo permette di rispondere a domande come:
      "Quale spread è più comune per Miraidon Life Orb Protect?"
    senza frammentare l'identità della build.
    """
    __tablename__ = "pokemon_build_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    build_id: Mapped[str] = mapped_column(
        ForeignKey("pokemon_build.id", ondelete="CASCADE")
    )

    # EV spread
    ev_hp:  Mapped[int] = mapped_column(SmallInteger, default=0)
    ev_atk: Mapped[int] = mapped_column(SmallInteger, default=0)
    ev_def: Mapped[int] = mapped_column(SmallInteger, default=0)
    ev_spa: Mapped[int] = mapped_column(SmallInteger, default=0)
    ev_spd: Mapped[int] = mapped_column(SmallInteger, default=0)
    ev_spe: Mapped[int] = mapped_column(SmallInteger, default=0)

    # IV spread
    iv_hp:  Mapped[int] = mapped_column(SmallInteger, default=31)
    iv_atk: Mapped[int] = mapped_column(SmallInteger, default=31)
    iv_def: Mapped[int] = mapped_column(SmallInteger, default=31)
    iv_spa: Mapped[int] = mapped_column(SmallInteger, default=31)
    iv_spd: Mapped[int] = mapped_column(SmallInteger, default=31)
    iv_spe: Mapped[int] = mapped_column(SmallInteger, default=31)

    observed_count: Mapped[int] = mapped_column(Integer, default=1)
    """Quante volte questo spread è stato osservato per questa build"""

    __table_args__ = (
        UniqueConstraint(
            "build_id",
            "ev_hp", "ev_atk", "ev_def", "ev_spa", "ev_spd", "ev_spe",
            "iv_hp", "iv_atk", "iv_def", "iv_spa", "iv_spd", "iv_spe",
            name="uq_build_stats_spread"
        ),
    )

    build: Mapped["PokemonBuild"] = relationship(
        "PokemonBuild", back_populates="stats_observations"
    )


class PokemonBuildMove(Base):
    """
    Tabella di giunzione Build ↔ Mossa.
    Sostituisce la colonna CSV PokemonSet.moves.
    """
    __tablename__ = "pokemon_build_move"

    build_id: Mapped[str] = mapped_column(
        ForeignKey("pokemon_build.id", ondelete="CASCADE"), primary_key=True
    )
    move_id: Mapped[str] = mapped_column(
        ForeignKey("move_v2.id"), primary_key=True
    )
    slot: Mapped[int] = mapped_column(SmallInteger)
    """Slot 1-4 (ordinamento canonico: alfabetico per l'hash, ma preservato per display)"""

    __table_args__ = (
        CheckConstraint("slot BETWEEN 1 AND 4", name="ck_build_move_slot"),
        Index("idx_build_move_build_id", "build_id"),
        Index("idx_build_move_move_id",  "move_id"),
    )

    build: Mapped["PokemonBuild"] = relationship("PokemonBuild", back_populates="move_slots")
    move:  Mapped["MoveV2"] = relationship("MoveV2", back_populates="build_usages")


# ──────────────────────────────────────────────────────────────────────────────
# TEAM VARIANT
# ──────────────────────────────────────────────────────────────────────────────

class TeamVariantV2(Base):
    """
    Hash-deduplicato: un insieme di 6 PokemonBuild.
    L'ID è uno SHA-256 deterministico calcolato da hash_utils.compute_team_hash().
    """
    __tablename__ = "team_variant_v2"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    """SHA-256 hex (64 caratteri)"""
    size: Mapped[int] = mapped_column(SmallInteger, default=6)

    builds: Mapped[List["TeamVariantBuild"]] = relationship(
        "TeamVariantBuild",
        back_populates="team_variant",
        order_by="TeamVariantBuild.slot",
        cascade="all, delete-orphan"
    )


class TeamVariantBuild(Base):
    """
    Tabella di giunzione TeamVariant ↔ PokemonBuild.
    Sostituisce la colonna JSON TeamVariant.pokemon_set_ids.
    """
    __tablename__ = "team_variant_build"

    team_variant_id: Mapped[str] = mapped_column(
        ForeignKey("team_variant_v2.id", ondelete="CASCADE"), primary_key=True
    )
    build_id: Mapped[str] = mapped_column(
        ForeignKey("pokemon_build.id"), primary_key=True
    )
    slot: Mapped[int] = mapped_column(SmallInteger)
    """Slot 1-6 nell'ordine in cui il giocatore ha listato il team"""

    __table_args__ = (
        CheckConstraint("slot BETWEEN 1 AND 6", name="ck_tvb_slot"),
        Index("idx_team_variant_build_tv_id",  "team_variant_id"),
        Index("idx_team_variant_build_bid",    "build_id"),
    )

    team_variant: Mapped["TeamVariantV2"] = relationship(
        "TeamVariantV2", back_populates="builds"
    )
    build: Mapped["PokemonBuild"] = relationship("PokemonBuild")


# ──────────────────────────────────────────────────────────────────────────────
# TRAINER
# ──────────────────────────────────────────────────────────────────────────────

class TrainerV2(Base):
    """Trainer (username Showdown)."""
    __tablename__ = "trainer_v2"

    id:     Mapped[str] = mapped_column(String(128), primary_key=True)
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


# ──────────────────────────────────────────────────────────────────────────────
# MATCH
# ──────────────────────────────────────────────────────────────────────────────

class MatchV2(Base):
    """Un singolo match / replay Pokémon Showdown."""
    __tablename__ = "match_v2"

    id:        Mapped[str] = mapped_column(String(256), primary_key=True)
    format:    Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """Timestamp con timezone (TIMESTAMPTZ) — UTC"""
    winner_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("trainer_v2.id"), nullable=True
    )

    __table_args__ = (
        Index("idx_match_v2_format", "format"),
    )

    teams:   Mapped[List["MatchTeamV2"]] = relationship(
        "MatchTeamV2", back_populates="match", cascade="all, delete-orphan"
    )
    turns:   Mapped[List["TurnV2"]] = relationship(
        "TurnV2", back_populates="match", cascade="all, delete-orphan"
    )
    summary: Mapped[Optional["MatchSummaryV2"]] = relationship(
        "MatchSummaryV2", back_populates="match",
        uselist=False, cascade="all, delete-orphan"
    )


class MatchTeamV2(Base):
    """Associazione Match ↔ Trainer ↔ TeamVariant."""
    __tablename__ = "match_team_v2"

    id:              Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id:        Mapped[str] = mapped_column(ForeignKey("match_v2.id", ondelete="CASCADE"))
    trainer_id:      Mapped[str] = mapped_column(ForeignKey("trainer_v2.id"))
    player_slot:     Mapped[str] = mapped_column(String(2))
    """'p1' o 'p2'"""
    team_variant_id: Mapped[str] = mapped_column(ForeignKey("team_variant_v2.id"))

    __table_args__ = (
        Index("idx_match_team_v2_match_id",    "match_id"),
        Index("idx_match_team_v2_trainer_id",  "trainer_id"),
        Index("idx_match_team_v2_variant_id",  "team_variant_id"),
    )

    match:        Mapped["MatchV2"] = relationship("MatchV2", back_populates="teams")
    variant:      Mapped["TeamVariantV2"] = relationship("TeamVariantV2")
    trainer:      Mapped["TrainerV2"] = relationship("TrainerV2")


# ──────────────────────────────────────────────────────────────────────────────
# TURN, BOARD STATE, FIELD CONDITIONS
# ──────────────────────────────────────────────────────────────────────────────

class TurnV2(Base):
    """Un singolo turno di un match."""
    __tablename__ = "turn_v2"

    id:           Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id:     Mapped[str] = mapped_column(ForeignKey("match_v2.id", ondelete="CASCADE"))
    turn_number:  Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        Index("idx_turn_v2_match_id", "match_id"),
    )

    match:        Mapped["MatchV2"] = relationship("MatchV2", back_populates="turns")
    actions:      Mapped[List["TurnActionV2"]] = relationship(
        "TurnActionV2", back_populates="turn",
        order_by="TurnActionV2.action_order",
        cascade="all, delete-orphan"
    )
    board_state:  Mapped[Optional["TurnBoardState"]] = relationship(
        "TurnBoardState", back_populates="turn",
        uselist=False, cascade="all, delete-orphan"
    )
    field_conditions: Mapped[List["TurnFieldCondition"]] = relationship(
        "TurnFieldCondition", back_populates="turn",
        cascade="all, delete-orphan"
    )


class TurnBoardState(Base):
    """
    Stato del campo in un turno (4 posizioni attive).
    DEDUPLICATO: una sola riga per turno invece di N righe in TurnAction.
    Sostituisce active_p1a_id, active_p1b_id, active_p2a_id, active_p2b_id
    che erano duplicati in ogni TurnAction.
    """
    __tablename__ = "turn_board_state"

    id:          Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turn_id:     Mapped[int] = mapped_column(
        ForeignKey("turn_v2.id", ondelete="CASCADE"), unique=True
    )
    p1a_build_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("pokemon_build.id"), nullable=True
    )
    p1b_build_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("pokemon_build.id"), nullable=True
    )
    p2a_build_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("pokemon_build.id"), nullable=True
    )
    p2b_build_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("pokemon_build.id"), nullable=True
    )

    __table_args__ = (
        Index("idx_board_state_turn_id", "turn_id"),
    )

    turn: Mapped["TurnV2"] = relationship("TurnV2", back_populates="board_state")


class TurnFieldCondition(Base):
    """
    Condizione di campo attiva in un turno.
    Sostituisce le 10 colonne booleane hardcoded in Turn
    (trick_room, tailwind, reflect, lightscreen, aurora_veil, weather, terrain, ecc.)
    """
    __tablename__ = "turn_field_condition"

    id:        Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turn_id:   Mapped[int] = mapped_column(ForeignKey("turn_v2.id", ondelete="CASCADE"))
    side:      Mapped[str] = mapped_column(String(8), default="field")
    """'field' (TR, Gravity), 'p1', 'p2' (Tailwind, Reflect, ecc.)"""
    tag_id:    Mapped[int] = mapped_column(ForeignKey("tag.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("turn_id", "side", "tag_id", name="uq_tfc_turn_side_tag"),
        Index("idx_field_cond_turn_id", "turn_id"),
    )

    turn: Mapped["TurnV2"] = relationship("TurnV2", back_populates="field_conditions")
    tag:  Mapped["Tag"] = relationship("Tag")


# ──────────────────────────────────────────────────────────────────────────────
# TURN ACTIONS & EFFECTS
# ──────────────────────────────────────────────────────────────────────────────

class TurnActionV2(Base):
    """Un'azione (mossa, switch, faint) all'interno di un turno."""
    __tablename__ = "turn_action_v2"

    id:             Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turn_id:        Mapped[int] = mapped_column(ForeignKey("turn_v2.id", ondelete="CASCADE"))
    action_order:   Mapped[int] = mapped_column(Integer)
    action_type:    Mapped[str] = mapped_column(String(32))
    """'move', 'switch', 'drag', 'faint', 'upkeep', ecc."""

    actor_build_id:  Mapped[Optional[str]] = mapped_column(
        ForeignKey("pokemon_build.id"), nullable=True
    )
    target_build_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("pokemon_build.id"), nullable=True
    )
    move_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("move_v2.id"), nullable=True
    )
    details: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # raw_tags migrato a JSONB (PostgreSQL): indicizzabile, queryabile con operatori nativi
    raw_tags: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    """JSONB grezzo dal parser — per debugging e future query JSONB"""

    __table_args__ = (
        Index("idx_turn_action_v2_turn_id",   "turn_id"),
        Index("idx_turn_action_v2_move_id",   "move_id"),
        Index("idx_turn_action_v2_actor_id",  "actor_build_id"),
    )

    turn:    Mapped["TurnV2"] = relationship("TurnV2", back_populates="actions")
    move:    Mapped[Optional["MoveV2"]] = relationship("MoveV2")
    effects: Mapped[List["ActionEffectV2"]] = relationship(
        "ActionEffectV2", back_populates="turn_action", cascade="all, delete-orphan"
    )


class ActionEffectV2(Base):
    """Effetto di un'azione su un target (danno, status, crit, ecc.)."""
    __tablename__ = "action_effect_v2"

    id:              Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turn_action_id:  Mapped[int] = mapped_column(
        ForeignKey("turn_action_v2.id", ondelete="CASCADE")
    )
    target_build_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("pokemon_build.id"), nullable=True
    )
    damage_percent:  Mapped[float] = mapped_column(Numeric(6, 2), default=0.0)
    """Numeric(6,2) per precisione esatta (vs Float con floating point error)"""
    status_inflicted: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    is_crit:         Mapped[bool] = mapped_column(Boolean, default=False)
    effectiveness:   Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    ability_activated: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    item_consumed:   Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_protected:    Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("idx_action_effect_v2_action_id",  "turn_action_id"),
        Index("idx_action_effect_v2_target_bid", "target_build_id"),
    )

    turn_action: Mapped["TurnActionV2"] = relationship(
        "TurnActionV2", back_populates="effects"
    )
    stat_changes: Mapped[List["ActionEffectStatChange"]] = relationship(
        "ActionEffectStatChange", back_populates="effect", cascade="all, delete-orphan"
    )


class ActionEffectStatChange(Base):
    """
    Variazione di stat causata da un effetto.
    Sostituisce il JSON dict stat_changes in ActionEffect.
    """
    __tablename__ = "action_effect_stat_change"

    id:        Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    effect_id: Mapped[int] = mapped_column(
        ForeignKey("action_effect_v2.id", ondelete="CASCADE")
    )
    stat:   Mapped[str] = mapped_column(String(8))
    """'atk', 'def', 'spa', 'spd', 'spe', 'acc', 'eva'"""
    stages: Mapped[int] = mapped_column(SmallInteger)

    __table_args__ = (
        Index("idx_stat_change_effect_id", "effect_id"),
    )

    effect: Mapped["ActionEffectV2"] = relationship(
        "ActionEffectV2", back_populates="stat_changes"
    )


# ──────────────────────────────────────────────────────────────────────────────
# ANALYTICS SUMMARY
# ──────────────────────────────────────────────────────────────────────────────

class MatchSummaryV2(Base):
    """Statistiche pre-calcolate per query analitiche veloci."""
    __tablename__ = "match_summary_v2"

    id:           Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id:     Mapped[str] = mapped_column(
        ForeignKey("match_v2.id", ondelete="CASCADE"), unique=True
    )
    total_turns:  Mapped[int] = mapped_column(Integer, default=0)

    match:    Mapped["MatchV2"] = relationship("MatchV2", back_populates="summary")
    brought:  Mapped[List["MatchBrought"]] = relationship(
        "MatchBrought", back_populates="summary", cascade="all, delete-orphan"
    )
    archetypes: Mapped[List["MatchArchetype"]] = relationship(
        "MatchArchetype", back_populates="summary", cascade="all, delete-orphan"
    )


class MatchBrought(Base):
    """
    Pokémon portati in campo da un giocatore in un match.
    Sostituisce la lista JSON p1_brought_pokemon / p2_brought_pokemon.
    """
    __tablename__ = "match_brought"

    id:          Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    summary_id:  Mapped[int] = mapped_column(
        ForeignKey("match_summary_v2.id", ondelete="CASCADE")
    )
    player_slot: Mapped[str] = mapped_column(String(2))
    """'p1' o 'p2'"""
    build_id:    Mapped[str] = mapped_column(ForeignKey("pokemon_build.id"))

    __table_args__ = (
        Index("idx_match_brought_summary_id", "summary_id"),
        Index("idx_match_brought_build_id",   "build_id"),
    )

    summary: Mapped["MatchSummaryV2"] = relationship(
        "MatchSummaryV2", back_populates="brought"
    )
    build: Mapped["PokemonBuild"] = relationship("PokemonBuild")


class MatchArchetype(Base):
    """
    Archetipo assegnato a un team in un match specifico.
    Sostituisce la lista JSON p1_archetypes / p2_archetypes.
    Il tag_id punta a un Tag di categoria 'archetype'.
    """
    __tablename__ = "match_archetype"

    id:          Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    summary_id:  Mapped[int] = mapped_column(
        ForeignKey("match_summary_v2.id", ondelete="CASCADE")
    )
    player_slot: Mapped[str] = mapped_column(String(2))
    tag_id:      Mapped[int] = mapped_column(ForeignKey("tag.id"))
    weight:      Mapped[float] = mapped_column(Numeric(4, 3), default=1.0)
    """Numeric(4,3) per peso archetipo (0.000-1.000)"""

    __table_args__ = (
        Index("idx_match_archetype_summary_id", "summary_id"),
    )

    summary: Mapped["MatchSummaryV2"] = relationship(
        "MatchSummaryV2", back_populates="archetypes"
    )
    tag: Mapped["Tag"] = relationship("Tag")


# ──────────────────────────────────────────────────────────────────────────────
# Alias di compatibilità — usati dal codice applicativo durante la transizione
# ──────────────────────────────────────────────────────────────────────────────

PokemonBuildV2 = PokemonBuild
TeamV2 = MatchTeamV2
