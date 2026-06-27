import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL

def add_terminated_column():
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                ALTER TABLE websites 
                ADD COLUMN IF NOT EXISTS terminated BOOLEAN DEFAULT FALSE NOT NULL;
            """))
            print("✅ Successfully added 'terminated' column to websites table")
    except Exception as e:
        print(f"❌ Error adding terminated column: {e}")
        raise
    finally:
        engine.dispose()

if __name__ == "__main__":
    add_terminated_column()

