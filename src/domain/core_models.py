from dataclasses import dataclass, field
from typing import List, Tuple, Dict

@dataclass
class CoreCombo:
    pokemon: Tuple[str, ...]
    usage_percent: float
    weaknesses: List[str]
    resistances: List[str]
    top_threats: List[str]

@dataclass
class CoreTeammates:
    core_2: List[CoreCombo] = field(default_factory=list)
    core_3: List[CoreCombo] = field(default_factory=list)
    core_4: List[CoreCombo] = field(default_factory=list)

@dataclass
class BuildDetails:
    item: str
    nature: str
    moves: str
    usage_percent: float
    occurrences: int
    cores: CoreTeammates

@dataclass
class PokemonUsageStats:
    species_id: str
    usage_percent: float
    total_occurrences: int
    global_cores: CoreTeammates
    builds: List[BuildDetails]
