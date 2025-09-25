#!/usr/bin/env python3
"""
Migration script to add password and max_participants fields to seminar_rooms table.
"""

import os
import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def run_migration():
    """Run the database migration."""
    
    # Database connection parameters
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': os.getenv('DB_PORT', '5432'),
        'database': os.getenv('DB_NAME', 'seminar_platform'),
        'user': os.getenv('DB_USER', 'seminar_user'),
        'password': os.getenv('DB_PASSWORD', 'seminar_password')
    }
    
    try:
        # Connect to database
        conn = psycopg2.connect(**db_config)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        print("Connected to database successfully")
        
        # Check if columns already exist
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'seminar_rooms' 
            AND column_name IN ('password', 'max_participants');
        """)
        
        existing_columns = [row[0] for row in cursor.fetchall()]
        
        # Add password column if it doesn't exist
        if 'password' not in existing_columns:
            print("Adding 'password' column to seminar_rooms table...")
            cursor.execute("""
                ALTER TABLE seminar_rooms 
                ADD COLUMN password VARCHAR(255);
            """)
            print("✓ Added 'password' column")
        else:
            print("✓ 'password' column already exists")
            
        # Add max_participants column if it doesn't exist
        if 'max_participants' not in existing_columns:
            print("Adding 'max_participants' column to seminar_rooms table...")
            cursor.execute("""
                ALTER TABLE seminar_rooms 
                ADD COLUMN max_participants INTEGER;
            """)
            print("✓ Added 'max_participants' column")
        else:
            print("✓ 'max_participants' column already exists")
            
        # Verify the migration
        cursor.execute("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'seminar_rooms' 
            AND column_name IN ('password', 'max_participants')
            ORDER BY column_name;
        """)
        
        result = cursor.fetchall()
        print("\nVerification - New columns:")
        for row in result:
            print(f"  {row[0]}: {row[1]} ({'NULL' if row[2] == 'YES' else 'NOT NULL'})")
            
        cursor.close()
        conn.close()
        print("\nMigration completed successfully! 🎉")
        
    except Exception as e:
        print(f"Error running migration: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migration()