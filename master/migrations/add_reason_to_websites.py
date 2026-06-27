"""
Migration to add reason field to websites table
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL

def add_reason_to_websites():
    """Add reason column to websites table."""
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.begin() as conn:
            # Check if column already exists
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='websites' AND column_name='reason'
            """))
            
            if result.fetchone():
                print("✅ 'reason' column already exists in websites table")
            else:
                conn.execute(text("""
                    ALTER TABLE websites 
                    ADD COLUMN reason TEXT;
                """))
                print("✅ Successfully added 'reason' column to websites table")
    except Exception as e:
        print(f"❌ Error adding reason column: {e}")
        raise
    finally:
        engine.dispose()

if __name__ == "__main__":
    add_reason_to_websites()

