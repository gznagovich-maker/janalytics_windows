import sys
import os
import glob

# Setup sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.parser.showdown import parse_showdown_log
from database.repository import save_parsed_match_to_db
from database.connection import Base, SessionLocal, engine
from sqlalchemy.exc import IntegrityError

def main():
    print("Initializing database...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    log_dir = r"C:\Users\Mirco\.gemini\antigravity\brain\c178b6bb-f583-42d5-be41-4d06727e7d6d\scratch"
    log_files = glob.glob(os.path.join(log_dir, "*.log"))
    
    print(f"Found {len(log_files)} logs in scratch directory.")
    
    for log_path in log_files:
        filename = os.path.basename(log_path)
        match_id = filename.replace('.log', '')
        print(f"\n--- Importing {match_id} ---")
        
        with open(log_path, 'r', encoding='utf-8') as f:
            log_content = f.read()
            
        try:
            parsed_match = parse_showdown_log(log_content)
            save_parsed_match_to_db(parsed_match, match_id)
            print(f"Successfully imported {match_id}.")
        except IntegrityError:
            print(f"Match {match_id} already exists in database. Skipping.")
        except Exception as e:
            print(f"Failed to import {match_id}: {e}")

if __name__ == "__main__":
    main()
