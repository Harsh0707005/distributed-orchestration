import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL

def move_terminated_to_status():
    engine = create_engine(DATABASE_URL)
    
    try:
        # First transaction: Add 'terminated' to the enum type
        with engine.begin() as conn:
            # First, check if terminated column exists
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='websites' AND column_name='terminated';
            """))
            terminated_exists = result.fetchone() is not None
            
            # Add 'terminated' to the enum type if it doesn't exist
            conn.execute(text("""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_enum 
                        WHERE enumlabel = 'terminated' 
                        AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'website_status')
                    ) THEN
                        ALTER TYPE website_status ADD VALUE 'terminated';
                    END IF;
                END $$;
            """))
            print("✅ Successfully added 'terminated' to website_status enum")
        
        # Second transaction: Migrate data and drop column (enum value must be committed first)
        if terminated_exists:
            with engine.begin() as conn:
                # Update websites with terminated=True to status='terminated'
                conn.execute(text("""
                    UPDATE websites 
                    SET status = 'terminated' 
                    WHERE terminated = TRUE;
                """))
                print("✅ Migrated terminated=True websites to status='terminated'")
                
                # Drop the terminated column
                conn.execute(text("""
                    ALTER TABLE websites 
                    DROP COLUMN IF EXISTS terminated;
                """))
                print("✅ Successfully dropped 'terminated' column from websites table")
        else:
            print("ℹ️  'terminated' column does not exist, skipping migration")
                
    except Exception as e:
        print(f"❌ Error moving terminated to status: {e}")
        raise
    finally:
        engine.dispose()

if __name__ == "__main__":
    move_terminated_to_status()

