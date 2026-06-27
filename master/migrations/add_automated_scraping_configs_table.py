import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL


def add_automated_scraping_configs_table():
    engine = create_engine(DATABASE_URL)
    try:
        with engine.begin() as conn:
            # Create enum type for scraping status
            conn.execute(
                text(
                    """
                    DO $$ BEGIN
                        CREATE TYPE scraping_status AS ENUM ('ready', 'in_queue', 'completed', 'blocked');
                    EXCEPTION
                        WHEN duplicate_object THEN null;
                    END $$;
                    """
                )
            )
            
            # Create the table
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS automated_scraping_configs (
                        id SERIAL PRIMARY KEY,
                        website VARCHAR NOT NULL,
                        country VARCHAR NOT NULL,
                        currency VARCHAR,
                        name_selector TEXT,
                        description_selector TEXT,
                        price_selector TEXT,
                        images_container_selector TEXT,
                        status scraping_status NOT NULL DEFAULT 'ready',
                        reason TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    );
                    """
                )
            )
            
            # Create index on website and country for faster lookups
            conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_automated_scraping_configs_website_country 
                    ON automated_scraping_configs(website, country);
                    """
                )
            )
            
            print("✅ Successfully created 'automated_scraping_configs' table")
    except Exception as e:
        print(f"❌ Error creating automated_scraping_configs table: {e}")
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    add_automated_scraping_configs_table()
