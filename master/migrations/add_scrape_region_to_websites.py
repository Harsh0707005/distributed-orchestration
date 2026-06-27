"""
Migration to add scrape_region column to websites table.
This column stores the AWS region from which the website should be scraped.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL


def add_scrape_region_to_websites():
    """Add scrape_region column to websites table."""
    engine = create_engine(DATABASE_URL)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    ALTER TABLE websites
                    ADD COLUMN IF NOT EXISTS scrape_region VARCHAR DEFAULT 'ap-south-1';
                    """
                )
            )
            print("✅ Successfully added 'scrape_region' column to websites table")
    except Exception as e:
        print(f"❌ Error adding scrape_region column: {e}")
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    add_scrape_region_to_websites()

