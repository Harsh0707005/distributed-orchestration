import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL

def add_priority_batches_table():
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS priority_batches (
                    id SERIAL PRIMARY KEY,
                    website_id INTEGER NOT NULL REFERENCES websites(id),
                    url VARCHAR NOT NULL,
                    website_url VARCHAR NOT NULL,
                    result TEXT NOT NULL,
                    model VARCHAR NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))
            
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_priority_batches_website_id 
                ON priority_batches(website_id);
            """))
            
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_priority_batches_created_at 
                ON priority_batches(created_at);
            """))
            
            print("✅ Successfully created 'priority_batches' table and indexes")
    except Exception as e:
        print(f"❌ Error creating priority_batches table: {e}")
        raise
    finally:
        engine.dispose()

if __name__ == "__main__":
    add_priority_batches_table()

