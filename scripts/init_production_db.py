#!/usr/bin/env python3
"""
Database initialization script for English-Thai Subtitle Platform
Creates all required tables for production deployment
"""

import os
import sys
from pathlib import Path

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from database import init_database, engine
from db_service import DatabaseService

def create_tables():
    """Create all database tables."""
    print("Creating database tables...")
    init_database()
    print("✓ Database tables created successfully")

def verify_tables():
    """Verify all tables were created correctly."""
    from sqlalchemy import text
    
    with engine.connect() as conn:
        # Check if all expected tables exist
        tables_query = text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        
        try:
            result = conn.execute(tables_query)
            tables = [row[0] for row in result]
            
            expected_tables = [
                'seminar_rooms', 
                'audio_segments', 
                'subtitle_segments', 
                'session_history'
            ]
            
            missing_tables = [t for t in expected_tables if t not in tables]
            
            if missing_tables:
                print(f"⚠️  Missing tables: {missing_tables}")
                return False
            else:
                print(f"✓ All expected tables found: {expected_tables}")
                return True
                
        except Exception as e:
            # For SQLite, use different query
            sqlite_query = text("""
                SELECT name FROM sqlite_master 
                WHERE type='table'
            """)
            result = conn.execute(sqlite_query)
            tables = [row[0] for row in result]
            print(f"✓ Database tables: {tables}")
            return len(tables) >= 4

def create_sample_data():
    """Create sample data for testing (optional)."""
    try:
        from database import get_db
        
        db = next(get_db())
        
        # Create a sample room
        room = DatabaseService.create_room(
            db, 
            title="Production Test Room",
            description="Sample room created during deployment"
        )
        
        print(f"✓ Sample room created: {room.room_id}")
        
    except Exception as e:
        print(f"⚠️  Could not create sample data: {e}")

def main():
    """Main deployment function."""
    print("🚀 Initializing English-Thai Subtitle Platform Database")
    print("=" * 60)
    
    # Check if database URL is configured
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        print(f"📊 Using database: {db_url.split('@')[0]}@***")
    else:
        print("📊 Using default SQLite database")
    
    try:
        # Create tables
        create_tables()
        
        # Verify tables
        if not verify_tables():
            print("❌ Table verification failed")
            sys.exit(1)
        
        # Create sample data (optional)
        if "--with-sample" in sys.argv:
            create_sample_data()
        
        print("=" * 60)
        print("✅ Database initialization completed successfully!")
        print("\n📋 Next steps:")
        print("1. Start the FastAPI application")
        print("2. Configure reverse proxy (nginx/apache)")
        print("3. Set up SSL certificates")
        print("4. Configure monitoring and logging")
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()