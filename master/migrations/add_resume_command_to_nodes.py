"""
Migration to add resume_command column to nodes table.
This flag signals a node to resume scraping after sample review.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL


def add_resume_command_to_nodes():
    """Add resume_command column to nodes table."""
    engine = create_engine(DATABASE_URL)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    ALTER TABLE nodes
                    ADD COLUMN IF NOT EXISTS resume_command BOOLEAN DEFAULT FALSE NOT NULL;
                    """
                )
            )
            print("✅ Successfully added 'resume_command' column to nodes table")
    except Exception as e:
        print(f"❌ Error adding resume_command column: {e}")
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    add_resume_command_to_nodes()

