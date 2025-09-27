-- Initialize the seminar platform database
-- This file is run automatically when PostgreSQL container starts

-- Enable UUID extension for generating room IDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create admin user with appropriate permissions
DO $$
BEGIN
	IF NOT EXISTS (
		SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'admin_user'
	) THEN
		CREATE ROLE admin_user LOGIN PASSWORD 'admin_secure_password';
	END IF;
END
$$;

GRANT ALL PRIVILEGES ON DATABASE seminar_platform TO admin_user;

-- Set timezone to UTC for consistency
ALTER DATABASE seminar_platform SET timezone TO 'UTC';

-- Create indexes that will be needed by SQLAlchemy models
-- These will be created automatically by SQLAlchemy, but we can prepare the database

-- Optional: enable statement stats if needed
-- CREATE EXTENSION IF NOT EXISTS pg_stat_statements;