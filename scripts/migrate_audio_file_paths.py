#!/usr/bin/env python3
"""
Database Migration: Add file path columns to audio_segments table
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from sqlalchemy import text
from backend.database import engine


def run_migration():
    """Add file path columns to audio_segments table"""
    
    migration_sql = """
    -- Add file path columns to audio_segments table
    ALTER TABLE audio_segments
    ADD COLUMN IF NOT EXISTS file_path_en VARCHAR(500),
    ADD COLUMN IF NOT EXISTS file_path_th VARCHAR(500);

    -- Add indexes for file paths
    CREATE INDEX IF NOT EXISTS idx_audio_segments_file_path_en
    ON audio_segments(file_path_en) WHERE file_path_en IS NOT NULL;

    CREATE INDEX IF NOT EXISTS idx_audio_segments_file_path_th
    ON audio_segments(file_path_th) WHERE file_path_th IS NOT NULL;
    """
    
    try:
        with engine.connect() as conn:
            conn.execute(text(migration_sql))
            conn.commit()
            print("✓ Migration completed successfully")
            print("  - Added file_path_en column")
            print("  - Added file_path_th column")
            print("  - Created indexes for file paths")
            
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    print("Running database migration: Add file path columns")
    run_migration()