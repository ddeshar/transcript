#!/usr/bin/env python3
"""
Migration script to fix timestamp_ms column type overflow issue.

This script changes the timestamp_ms column from INTEGER to BIGINT
to handle Unix timestamps in milliseconds without overflow.
"""

import sys
from pathlib import Path

# Add backend to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import engine
from sqlalchemy import text


def fix_timestamp_column():
    """Fix the timestamp_ms column type to handle large values."""
    
    print("Fixing timestamp_ms column type...")
    
    with engine.begin() as conn:
        try:
            # Check current column type
            result = conn.execute(text("""
                SELECT data_type 
                FROM information_schema.columns 
                WHERE table_name = 'subtitle_segments' 
                AND column_name = 'timestamp_ms'
            """))
            
            current_type = result.fetchone()
            if current_type:
                print(f"Current timestamp_ms type: {current_type[0]}")
                
                if current_type[0] in ['integer', 'int4']:
                    print("Converting INTEGER to BIGINT...")
                    
                    # Convert the column type to BIGINT
                    conn.execute(text("""
                        ALTER TABLE subtitle_segments 
                        ALTER COLUMN timestamp_ms TYPE BIGINT
                    """))
                    
                    print("✅ Successfully converted timestamp_ms to BIGINT")
                else:
                    print(f"Column is already {current_type[0]}, no change needed")
            else:
                print("❌ timestamp_ms column not found")
                
        except Exception as e:
            print(f"❌ Error fixing timestamp column: {e}")
            raise


if __name__ == "__main__":
    fix_timestamp_column()