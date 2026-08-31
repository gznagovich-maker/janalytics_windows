import os
import sys

# Aggiungiamo janalytics_windows al PYTHONPATH per importare
sys.path.append(os.path.abspath('.'))

from domain.smogon_calc import SmogonDamageCalc
from domain.team_optimizer import TeamOptimizer

def test():
    print("Inizializzando Calc...")
    calc = SmogonDamageCalc(db_path="janalytics.db")
    optimizer = TeamOptimizer(calc)
    
    pool = [
        {"name": "Incineroar", "options": {"nature": "Careful", "evs": {"hp": 252, "spd": 252}}},
        {"name": "Rillaboom", "options": {"nature": "Adamant", "evs": {"hp": 252, "atk": 252}}},
        {"name": "Flutter Mane", "options": {"nature": "Timid", "evs": {"spa": 252, "spe": 252}}},
        {"name": "Amoonguss", "options": {"nature": "Bold", "evs": {"hp": 252, "def": 252}}},
        {"name": "Urshifu-Rapid-Strike", "options": {"nature": "Jolly", "evs": {"atk": 252, "spe": 252}}},
        {"name": "Ogerpon-Hearthflame", "options": {"nature": "Jolly", "evs": {"atk": 252, "spe": 252}}},
        {"name": "Tornadus", "options": {"nature": "Timid", "evs": {"hp": 252, "spe": 252}}},
        {"name": "Chien-Pao", "options": {"nature": "Jolly", "evs": {"atk": 252, "spe": 252}}}
    ]
    
    threats = [
        {"name": "Flutter Mane", "options": {"nature": "Timid", "evs": {"spa": 252, "spe": 252}}, "common_moves": ["Moonblast", "Shadow Ball"]},
        {"name": "Ogerpon-Hearthflame", "options": {"nature": "Jolly", "evs": {"atk": 252, "spe": 252}}, "common_moves": ["Ivy Cudgel"]}
    ]
    
    print("Build Matrices...")
    optimizer.build_matrices(pool, threats)
    
    print("Matrice Danni Size:", len(optimizer.damage_matrix))
    print("Matrice Speed Size:", len(optimizer.speed_matrix))
    
    print("Test Hill Climb Generate...")
    best_team, score = optimizer.hill_climb_generate(restarts=1)
    print("Best Team Indices:", best_team)
    print("Best Score:", score)
    
    print("Test Hill Climb Optimize...")
    opt_team, opt_score, _ = optimizer.hill_climb_optimize([0, 1, 2, 3, 4, 5], max_iter=2)
    print("Opt Team Indices:", opt_team)
    print("Opt Score:", opt_score)
    
    print("Test EV Optimization...")
    mock_team_builds = [
        {"name": "Flutter Mane", "options": {"nature": "Timid", "evs": {}}, "moves": ["Moonblast"]},
        {"name": "Ogerpon-Hearthflame", "options": {"nature": "Jolly", "evs": {}}, "moves": ["Ivy Cudgel"]},
        {"name": "Incineroar", "options": {"nature": "Careful", "evs": {}}, "moves": ["Knock Off"]},
        {"name": "Rillaboom", "options": {"nature": "Adamant", "evs": {}}, "moves": ["Wood Hammer"]},
        {"name": "Tornadus", "options": {"nature": "Timid", "evs": {}}, "moves": ["Bleakwind Storm"]},
        {"name": "Chien-Pao", "options": {"nature": "Jolly", "evs": {}}, "moves": ["Icicle Crash"]}
    ]
    final_team, final_score = optimizer.optimize_evs_for_team(mock_team_builds, threats)
    print("EV Opt Score:", final_score)
    
    print("Tutto ok!")

if __name__ == "__main__":
    test()
