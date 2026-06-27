import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL

def add_null_heartbeat_count():
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                ALTER TABLE nodes
                ADD COLUMN IF NOT EXISTS null_heartbeat_count INTEGER DEFAULT 0 NOT NULL;
            """))
            
            print("✅ Successfully added 'null_heartbeat_count' column to nodes table")
    except Exception as e:
        print(f"❌ Error adding null_heartbeat_count column: {e}")
        raise
    finally:
        engine.dispose()

if __name__ == "__main__":
    add_null_heartbeat_count()

