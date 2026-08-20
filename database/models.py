from typing import Optional, Dict, Any
from sqlalchemy import ForeignKey, String, Integer, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.connection import Base


class Trainer(Base):
    __tablename__ = "trainer"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    rating: Mapped[Optional[int]] = mapped_column(Integer)


class Match(Base):
    __tablename__ = "match"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    format: Mapped[Optional[str]] = mapped_column(String)
    timestamp: Mapped[Optional[DateTime]] = mapped_column(DateTime)
    winner_id: Mapped[Optional[str]] = mapped_column(ForeignKey("trainer.id"))

    teams = relationship("Team", back_populates="match")
    turns = relationship("Turn", back_populates="match")


class Team(Base):
    __tablename__ = "team"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("match.id"))
    trainer_id: Mapped[str] = mapped_column(ForeignKey("trainer.id"))
    player_slot: Mapped[str] = mapped_column(String)

    match = relationship("Match", back_populates="teams")
    pokemon_builds = relationship("PokemonBuild", back_populates="team")


class PokemonBuild(Base):
    __tablename__ = "pokemon_build"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("team.id"))
    species_id: Mapped[str] = mapped_column(String)
    ability: Mapped[Optional[str]] = mapped_column(String)
    item: Mapped[Optional[str]] = mapped_column(String)
    tera_type: Mapped[Optional[str]] = mapped_column(String)

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
    is_brought: Mapped[bool] = mapped_column(Boolean, default=False)

    team = relationship("Team", back_populates="pokemon_builds")


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
    actions = relationship("TurnAction", back_populates="turn", order_by="TurnAction.action_order")


class TurnAction(Base):
    __tablename__ = "turn_action"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turn_id: Mapped[int] = mapped_column(ForeignKey("turn.id"))
    action_order: Mapped[int] = mapped_column(Integer)
    action_type: Mapped[str] = mapped_column(String)

    actor_build_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pokemon_build.id"))
    target_build_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pokemon_build.id"))

    active_p1a_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pokemon_build.id"))
    active_p1b_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pokemon_build.id"))
    active_p2a_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pokemon_build.id"))
    active_p2b_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pokemon_build.id"))

    tags: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    details: Mapped[Optional[str]] = mapped_column(String)

    turn = relationship("Turn", back_populates="actions")
