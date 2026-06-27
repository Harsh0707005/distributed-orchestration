"""
Migration to add region column to nodes table.
This column stores the AWS region where the node is running.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL


def add_region_to_nodes():
    """Add region column to nodes table."""
    engine = create_engine(DATABASE_URL)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    ALTER TABLE nodes
                    ADD COLUMN IF NOT EXISTS region VARCHAR DEFAULT 'ap-south-1';
                    """
                )
            )
            print("✅ Successfully added 'region' column to nodes table")
    except Exception as e:
        print(f"❌ Error adding region column: {e}")
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    add_region_to_nodes()

