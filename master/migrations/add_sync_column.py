import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL

def add_sync_column():
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                ALTER TABLE priority_batches 
                ADD COLUMN IF NOT EXISTS sync BOOLEAN DEFAULT FALSE NOT NULL;
            """))
            print("✅ Successfully added 'sync' column to priority_batches table")
    except Exception as e:
        print(f"❌ Error adding sync column: {e}")
        raise
    finally:
        engine.dispose()

if __name__ == "__main__":
    add_sync_column()

