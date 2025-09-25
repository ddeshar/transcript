-- Initialize the seminar platform database
-- This file is run automatically when PostgreSQL container starts

-- Enable UUID extension for generating room IDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create admin user with appropriate permissions
CREATE USER IF NOT EXISTS admin_user WITH PASSWORD 'admin_secure_password';
GRANT ALL PRIVILEGES ON DATABASE seminar_platform TO admin_user;

-- Set timezone to UTC for consistency
ALTER DATABASE seminar_platform SET timezone TO 'UTC';

-- Create indexes that will be needed by SQLAlchemy models
-- These will be created automatically by SQLAlchemy, but we can prepare the database

-- Log successful initialization
INSERT INTO pg_stat_statements_info (dealloc) VALUES (0) ON CONFLICT DO NOTHING;