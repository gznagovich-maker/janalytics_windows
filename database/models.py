from typing import Optional, Dict, Any, List
from sqlalchemy import ForeignKey, String, Integer, Float, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.connection import Base


class Trainer(Base):
    __tablename__ = "trainer"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    rating: Mapped[Optional[int]] = mapped_column(Integer)


class PokemonSpecies(Base):
    __tablename__ = "pokemon_species"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    num: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String)
    base_species: Mapped[Optional[str]] = mapped_column(String)
    forme: Mapped[Optional[str]] = mapped_column(String)
    types: Mapped[Any] = mapped_column(JSON)
    base_stats: Mapped[Any] = mapped_column(JSON)
    sprite_url: Mapped[Optional[str]] = mapped_column(String)
    artwork_url: Mapped[Optional[str]] = mapped_column(String)


class Ability(Base):
    __tablename__ = "ability"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    short_desc: Mapped[str] = mapped_column(String)


class Item(Base):
    __tablename__ = "item"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    short_desc: Mapped[str] = mapped_column(String)
    effect: Mapped[Optional[str]] = mapped_column(String)
    sprite_url: Mapped[Optional[str]] = mapped_column(String)


class Move(Base):
    __tablename__ = "move"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)
    base_power: Mapped[int] = mapped_column(Integer)
    accuracy: Mapped[int] = mapped_column(Integer)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    short_desc: Mapped[str] = mapped_column(String)


class PokemonSet(Base):
    """Hash univoco di una build di un pokemon. Elimina la ridondanza."""
    __tablename__ = "pokemon_set"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # Hash univoco
    species_id: Mapped[str] = mapped_column(ForeignKey("pokemon_species.id"))
    ability_id: Mapped[Optional[str]] = mapped_column(ForeignKey("ability.id"))
    item_id: Mapped[Optional[str]] = mapped_column(ForeignKey("item.id"))
    tera_type: Mapped[Optional[str]] = mapped_column(String)
    moves: Mapped[Optional[str]] = mapped_column(String)  # CSV di stringhe ID

    ev_hp: Mapped[int] = mapped_column(Integer, default=0)
    ev_atk: Mapped[int] = mapped_column(Integer, default=0)
    ev_def: Mapped[int] = mapped_column(Integer, default=0)
    ev_spa: Mapped[int] = mapped_column(Integer, default=0)
    ev_spd: Mapped[int] = mapped_column(Integer, default=0)
    ev_spe: Mapped[int] = mapped_column(Integer, default=0)

    iv_hp: Mapped[int] = mapped_column(Integer, default=31)
    iv_atk: Mapped[int] = mapped_column(Integer, default=31)
    iv_def: Mapped[int] = mapped_column(Integer, default=31)
    iv_spa: Mapped[int] = mapped_column(Integer, default=31)
    iv_spd: Mapped[int] = mapped_column(Integer, default=31)
    iv_spe: Mapped[int] = mapped_column(Integer, default=31)

    nature: Mapped[str] = mapped_column(String, default="Hardy")
    
    species = relationship("PokemonSpecies")
    ability = relationship("Ability")
    item = relationship("Item")


class TeamVariant(Base):
    """Hash univoco di un team completo (6 PokemonSet)."""
    __tablename__ = "team_variant"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # Hash univoco dei 6 set
    # Salviamo i riferimenti in JSON o CSV per evitare 6 colonne fisse o tabelle di junction per query analitiche
    pokemon_set_ids: Mapped[Any] = mapped_column(JSON) # Lista di stringhe ID


class Match(Base):
    __tablename__ = "match"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    format: Mapped[Optional[str]] = mapped_column(String)
    timestamp: Mapped[Optional[DateTime]] = mapped_column(DateTime)
    winner_id: Mapped[Optional[str]] = mapped_column(ForeignKey("trainer.id"))

    teams = relationship("MatchTeam", back_populates="match", cascade="all, delete-orphan")
    turns = relationship("Turn", back_populates="match", cascade="all, delete-orphan")
    summary = relationship("MatchSummary", back_populates="match", uselist=False, cascade="all, delete-orphan")


class MatchTeam(Base):
    __tablename__ = "match_team"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("match.id"))
    trainer_id: Mapped[str] = mapped_column(ForeignKey("trainer.id"))
    player_slot: Mapped[str] = mapped_column(String)
    team_variant_id: Mapped[str] = mapped_column(ForeignKey("team_variant.id"))

    match = relationship("Match", back_populates="teams")
    variant = relationship("TeamVariant")


class MatchSummary(Base):
    """Statistiche pre-calcolate del match per query analitiche veloci."""
    __tablename__ = "match_summary"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("match.id"))
    
    p1_brought_pokemon: Mapped[Any] = mapped_column(JSON, default=list) # Lista di species_id portati
    p2_brought_pokemon: Mapped[Any] = mapped_column(JSON, default=list) 
    
    p1_archetypes: Mapped[Any] = mapped_column(JSON, default=list)
    p2_archetypes: Mapped[Any] = mapped_column(JSON, default=list)
    
    total_turns: Mapped[int] = mapped_column(Integer, default=0)
    
    match = relationship("Match", back_populates="summary")


class Turn(Base):
    __tablename__ = "turn"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("match.id"))
    turn_number: Mapped[int] = mapped_column(Integer)
    weather: Mapped[Optional[str]] = mapped_column(String)
    terrain: Mapped[Optional[str]] = mapped_column(String)
    trick_room: Mapped[bool] = mapped_column(Boolean, default=False)
    p1_tailwind: Mapped[bool] = mapped_column(Boolean, default=False)
    p2_tailwind: Mapped[bool] = mapped_column(Boolean, default=False)
    p1_reflect: Mapped[bool] = mapped_column(Boolean, default=False)
    p2_reflect: Mapped[bool] = mapped_column(Boolean, default=False)
    p1_lightscreen: Mapped[bool] = mapped_column(Boolean, default=False)
    p2_lightscreen: Mapped[bool] = mapped_column(Boolean, default=False)
    p1_aurora_veil: Mapped[bool] = mapped_column(Boolean, default=False)
    p2_aurora_veil: Mapped[bool] = mapped_column(Boolean, default=False)

    match = relationship("Match", back_populates="turns")
    actions = relationship("TurnAction", back_populates="turn", cascade="all, delete-orphan", order_by="TurnAction.action_order")


class TurnAction(Base):
    __tablename__ = "turn_action"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turn_id: Mapped[int] = mapped_column(ForeignKey("turn.id"))
    action_order: Mapped[int] = mapped_column(Integer)
    action_type: Mapped[str] = mapped_column(String)
    move_id: Mapped[Optional[str]] = mapped_column(ForeignKey("move.id"))

    actor_set_id: Mapped[Optional[str]] = mapped_column(ForeignKey("pokemon_set.id"))
    target_set_id: Mapped[Optional[str]] = mapped_column(ForeignKey("pokemon_set.id"))

    active_p1a_id: Mapped[Optional[str]] = mapped_column(ForeignKey("pokemon_set.id"))
    active_p1b_id: Mapped[Optional[str]] = mapped_column(ForeignKey("pokemon_set.id"))
    active_p2a_id: Mapped[Optional[str]] = mapped_column(ForeignKey("pokemon_set.id"))
    active_p2b_id: Mapped[Optional[str]] = mapped_column(ForeignKey("pokemon_set.id"))

    ability_activated: Mapped[Optional[str]] = mapped_column(String)
    item_consumed: Mapped[Optional[str]] = mapped_column(String)

    tags: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    details: Mapped[Optional[str]] = mapped_column(String)

    turn = relationship("Turn", back_populates="actions")
    effects = relationship("ActionEffect", back_populates="turn_action", cascade="all, delete-orphan")


class ActionEffect(Base):
    __tablename__ = "action_effect"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turn_action_id: Mapped[int] = mapped_column(ForeignKey("turn_action.id"))
    target_set_id: Mapped[Optional[str]] = mapped_column(ForeignKey("pokemon_set.id"))
    
    damage_percent: Mapped[float] = mapped_column(Float, default=0.0)
    stat_changes: Mapped[Dict[str, int]] = mapped_column(JSON, default=dict)
    status_inflicted: Mapped[Optional[str]] = mapped_column(String)
    is_crit: Mapped[bool] = mapped_column(Boolean, default=False)
    effectiveness: Mapped[Optional[str]] = mapped_column(String)
    ability_activated: Mapped[Optional[str]] = mapped_column(String)
    item_consumed: Mapped[Optional[str]] = mapped_column(String)
    is_protected: Mapped[bool] = mapped_column(Boolean, default=False)
    
    turn_action = relationship("TurnAction", back_populates="effects")

PokemonBuild = PokemonSet
Team = MatchTeam
