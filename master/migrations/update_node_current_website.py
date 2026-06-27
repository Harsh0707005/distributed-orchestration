import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL

def update_node_current_website():
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                ALTER TABLE nodes
                DROP COLUMN IF EXISTS total_websites_completed;
            """))
            
            conn.execute(text("""
                ALTER TABLE nodes
                ADD COLUMN IF NOT EXISTS current_website_id INTEGER REFERENCES websites(id);
            """))
            
            print("✅ Successfully removed 'total_websites_completed' and added 'current_website_id' column to nodes table")
    except Exception as e:
        print(f"❌ Error updating nodes table: {e}")
        raise
    finally:
        engine.dispose()

if __name__ == "__main__":
    update_node_current_website()

