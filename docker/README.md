# Docker Setup

This directory contains Dockerfiles for the seminar platform.

## Files

- `Dockerfile.backend` - Multi-stage Python backend container
- `Dockerfile.frontend` - Nginx frontend container (optional separate serving)

## Usage

From the project root:

```bash
# Build and start all services
docker-compose up -d

# Build only the main application
docker-compose build app

# View logs
docker-compose logs -f app

# Stop all services
docker-compose down
```

## Services

The main `docker-compose.yml` in the project root includes:

- **db**: PostgreSQL 15 database
- **redis**: Redis for caching and sessions  
- **pgadmin**: Database administration interface (port 5050)
- **app**: Main FastAPI application (port 8000)

## Environment

The application uses `.env` file in the project root for configuration.
See `.env.template` for available options.