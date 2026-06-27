"""
Migration to add new website statuses: paused, rejected, manual_extraction
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL


def add_new_website_statuses():
    """Add new statuses to website_status enum."""
    engine = create_engine(DATABASE_URL)
    try:
        with engine.begin() as conn:
            # Check if enum values already exist
            result = conn.execute(text("""
                SELECT enumlabel 
                FROM pg_enum 
                WHERE enumtypid = (
                    SELECT oid FROM pg_type WHERE typname = 'website_status'
                ) AND enumlabel IN ('paused', 'rejected', 'manual_extraction')
            """))
            existing = [row[0] for row in result]
            
            # Add new enum values if they don't exist
            if 'paused' not in existing:
                conn.execute(text("ALTER TYPE website_status ADD VALUE IF NOT EXISTS 'paused'"))
                print("✅ Added 'paused' status to website_status enum")
            
            if 'rejected' not in existing:
                conn.execute(text("ALTER TYPE website_status ADD VALUE IF NOT EXISTS 'rejected'"))
                print("✅ Added 'rejected' status to website_status enum")
            
            if 'manual_extraction' not in existing:
                conn.execute(text("ALTER TYPE website_status ADD VALUE IF NOT EXISTS 'manual_extraction'"))
                print("✅ Added 'manual_extraction' status to website_status enum")
            
            if len(existing) == 3:
                print("✅ All new statuses already exist in website_status enum")
    except Exception as e:
        print(f"❌ Error adding new website statuses: {e}")
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    add_new_website_statuses()

