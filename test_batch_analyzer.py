from domain.smogon_calc import SmogonDamageCalc
from domain.batch_analyzer import BatchDamageAnalyzer

def main():
    # Inizializza il calcolatore usando il db interno
    calc = SmogonDamageCalc(db_path="janalytics.db")
    analyzer = BatchDamageAnalyzer(calc_instance=calc, meta_format_name="vgc_reg_g")
    
    # Esempio di team utente
    my_team = [
        {
            "name": "Amoonguss",
            "options": {
                "item": "Rocky Helmet",
                "nature": "Bold",
                "evs": {"hp": 252, "def": 252, "spd": 4},
                "teraType": "Water"
            },
            "moves": ["Spore", "Pollen Puff", "Rage Powder", "Protect"]
        },
        {
            "name": "Ogerpon-Hearthflame",
            "options": {
                "item": "Hearthflame Mask",
                "nature": "Jolly",
                "evs": {"hp": 4, "atk": 252, "spe": 252},
                "teraType": "Fire"
            },
            "moves": ["Ivy Cudgel", "Horn Leech", "Spiky Shield", "Swords Dance"]
        }
    ]
    
    report = analyzer.generate_batch_report(my_team)
    print(report)
    
if __name__ == "__main__":
    main()
