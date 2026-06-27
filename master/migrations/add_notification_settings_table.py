import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL


def add_notification_settings_table():
    engine = create_engine(DATABASE_URL)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS notification_settings (
                        id SERIAL PRIMARY KEY,
                        emails JSONB,
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );
                    """
                )
            )
            # Ensure there is always at least one row
            conn.execute(
                text(
                    """
                    INSERT INTO notification_settings (id, emails)
                    VALUES (1, '[]'::jsonb)
                    ON CONFLICT (id) DO NOTHING;
                    """
                )
            )
            print("✅ notification_settings table ready")
    except Exception as e:
        print(f"❌ Error adding notification_settings table: {e}")
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    add_notification_settings_table()


