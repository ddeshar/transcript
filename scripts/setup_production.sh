#!/bin/bash

# Seminar Platform Production Setup Script
# This script sets up the production environment with PostgreSQL and proper directory structure

set -e  # Exit on any error

echo "🚀 Setting up Seminar Platform for Production..."

# Create required directories
echo "📁 Creating data directories..."
mkdir -p docker/data/postgres
mkdir -p docker/data/redis
mkdir -p docker/data/media/{audio,exports}
mkdir -p docker/data/logs
mkdir -p docker/data/backups

# Set proper permissions for Docker volumes
echo "🔐 Setting directory permissions..."
chmod 755 docker/data
chmod 755 docker/data/*

# Check if .env.docker exists
if [ ! -f .env.docker ]; then
    echo "⚠️  .env.docker not found. Creating from template..."
    cp .env.example .env.docker
    echo "📝 Please edit .env.docker with your production values"
fi

# Check if Docker and Docker Compose are installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Pull required Docker images
echo "📦 Pulling Docker images..."
cd docker
docker-compose pull

# Build the application images
echo "🔨 Building application images..."
docker-compose build --no-cache

echo "✅ Setup complete!"
echo ""
echo "🎯 Next steps:"
echo "1. Edit .env.docker with your production settings"
echo "2. Update JWT_SECRET_KEY and ADMIN_PASSWORD in .env.docker"
echo "3. Run: cd docker && docker-compose up -d"
echo "4. Check logs: cd docker && docker-compose logs -f"
echo ""
echo "🌐 Access URLs (after startup):"
echo "   - Frontend: http://localhost:5173"
echo "   - API: http://localhost:8000"
echo "   - Admin Login: http://localhost:5173/login"
echo "   - Health Check: http://localhost:8000/health"
echo ""
echo "📊 Database:"
echo "   - PostgreSQL: localhost:5432"
echo "   - Database: seminar_platform"
echo "   - Username: seminar_user"
echo ""
echo "🔍 Monitoring:"
echo "   - Data stored in: ./docker/data/"
echo "   - Logs: ./docker/data/logs/"
echo "   - Backups: ./docker/data/backups/"