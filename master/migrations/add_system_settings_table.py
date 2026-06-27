"""
Migration to create system_settings table and add default sample_size setting.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL


def add_system_settings_table():
    """Create system_settings table and add default sample_size."""
    engine = create_engine(DATABASE_URL)
    try:
        with engine.begin() as conn:
            # Create system_settings table
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS system_settings (
                        id SERIAL PRIMARY KEY,
                        key VARCHAR UNIQUE NOT NULL,
                        value TEXT NOT NULL,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
            )
            print("✅ Created system_settings table")
            
            # Add default sample_size if it doesn't exist
            result = conn.execute(
                text("SELECT COUNT(*) FROM system_settings WHERE key = 'sample_size'")
            )
            count = result.scalar()
            
            if count == 0:
                conn.execute(
                    text(
                        """
                        INSERT INTO system_settings (key, value)
                        VALUES ('sample_size', '100')
                        """
                    )
                )
                print("✅ Added default sample_size setting (100)")
            else:
                print("✅ sample_size setting already exists")
    except Exception as e:
        print(f"❌ Error creating system_settings table: {e}")
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    add_system_settings_table()

