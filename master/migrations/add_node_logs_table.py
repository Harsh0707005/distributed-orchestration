import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL

def add_node_logs_table():
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.begin() as conn:
            # Check if table exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'node_logs'
                );
            """))
            
            table_exists = result.scalar()
            
            if not table_exists:
                conn.execute(text("""
                    CREATE TABLE node_logs (
                        id SERIAL PRIMARY KEY,
                        node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                        message TEXT NOT NULL,
                        level VARCHAR(20) DEFAULT 'INFO' NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    );
                """))
                
                # Create index on node_id for faster queries
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_node_logs_node_id 
                    ON node_logs(node_id);
                """))
                
                # Create index on created_at for faster sorting
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_node_logs_created_at 
                    ON node_logs(created_at DESC);
                """))
                
                print("✅ Successfully created 'node_logs' table with indexes")
            else:
                print("ℹ️  'node_logs' table already exists")
    except Exception as e:
        print(f"❌ Error creating node_logs table: {e}")
        raise
    finally:
        engine.dispose()

if __name__ == "__main__":
    add_node_logs_table()

