# Production Deployment Guide

This guide covers deploying the Seminar Platform in a production environment with PostgreSQL database, authentication system, and Docker containers.

## Quick Start

1. **Run the setup script:**
   ```bash
   ./scripts/setup_production.sh
   ```

2. **Configure environment:**
   ```bash
   cp .env.docker.example .env.docker
   # Edit .env.docker with your production values
   ```

3. **Start the services:**
   ```bash
   cd docker
   docker-compose up -d
   ```

## Production Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Backend       │    │   Database      │
│   (nginx:80)    │───▶│   (FastAPI)     │───▶│   (PostgreSQL)  │
│   Static Files  │    │   WebSocket     │    │   Persistent    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │     Redis       │
                       │   (Sessions)    │
                       └─────────────────┘
```

## Environment Configuration

### Core Settings (.env.docker)

```bash
# Application
BASE_URL=https://your-domain.com
FRONTEND_URL=https://your-domain.com
ENVIRONMENT=production
DEBUG=false

# Database
DATABASE_URL=postgresql://seminar_user:your_password@db:5432/seminar_platform

# Authentication
JWT_SECRET_KEY=your-very-secure-secret-key-here
ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@your-domain.com
ADMIN_PASSWORD=secure_admin_password
```

### Security Configuration

```bash
# JWT Settings
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS Origins (comma-separated)
CORS_ORIGINS=https://your-domain.com,https://app.your-domain.com

# SSL/TLS (for production)
FORCE_HTTPS=true
SECURE_COOKIES=true
```

## Authentication System

### User Roles

- **Admin**: Can create rooms, access analytics, manage system
- **Participant**: Can join rooms (no authentication required)

### Admin Access

1. **Login URL**: `https://your-domain.com/login`
2. **Default Credentials**:
   - Username: admin (configurable via `ADMIN_USERNAME`)
   - Password: admin123 (configurable via `ADMIN_PASSWORD`)

### API Authentication

```javascript
// Login
POST /api/auth/login
{
  "username": "admin",
  "password": "password"
}

// Response
{
  "access_token": "jwt_token_here",
  "refresh_token": "refresh_token_here",
  "user": {...}
}

// Authenticated requests
Authorization: Bearer jwt_token_here
```

## Database Management

### PostgreSQL Setup

The production setup includes:
- PostgreSQL 15 with persistent storage
- Automatic database initialization
- Connection pooling and optimization
- Regular backup capabilities

### Data Persistence

```bash
# Data locations (Docker host)
./docker/data/postgres/     # Database files
./docker/data/redis/        # Session cache
./docker/data/media/        # Audio files & exports
./docker/data/logs/         # Application logs
./docker/data/backups/      # Database backups
```

### Database Backup

```bash
# Manual backup
docker-compose exec db pg_dump -U seminar_user seminar_platform > backup.sql

# Restore from backup
docker-compose exec -T db psql -U seminar_user seminar_platform < backup.sql
```

## Monitoring & Analytics

### Health Checks

- **Application**: `GET /health`
- **Database**: Built-in PostgreSQL health checks
- **Redis**: Built-in Redis health checks

### Participant Analytics

The system tracks:
- Real-time participant counts
- Join/leave events with timestamps
- Peak attendance statistics
- Session duration analytics
- Exportable reports (JSON, CSV, Excel)

### Log Management

```bash
# View logs
docker-compose logs -f app          # Application logs
docker-compose logs -f db           # Database logs
docker-compose logs -f redis        # Redis logs

# Log rotation is configured automatically
LOG_RETENTION_DAYS=30
LOG_ROTATION_SIZE=10MB
```

## Audio & Media Storage

### File Storage Configuration

```bash
# Storage paths
MEDIA_ROOT=/app/media
AUDIO_UPLOAD_PATH=/app/media/audio
SUBTITLE_EXPORT_PATH=/app/media/exports

# File limits
MAX_AUDIO_FILE_SIZE=100              # MB
AUDIO_FORMATS=wav,mp3,m4a,webm
```

### Export Features

- **Transcripts**: JSON, TXT, SRT formats
- **Analytics**: CSV, Excel with participant data
- **Audio**: Original files preserved
- **Subtitles**: Multiple language formats

## Performance Optimization

### WebSocket Configuration

```bash
# Connection limits
WEBSOCKET_MAX_CONNECTIONS=100
WEBSOCKET_TIMEOUT=300

# Audio processing
AUDIO_CHUNK_SIZE=8192
SAMPLE_RATE=16000
MAX_SILENCE_DURATION=30
```

### Database Optimization

```bash
# Connection pooling
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=30

# Performance monitoring
DATABASE_ECHO=false                  # Set to true for debugging
```

## SSL/HTTPS Setup

### Using Let's Encrypt (Recommended)

1. **Install Certbot:**
   ```bash
   sudo apt install certbot python3-certbot-nginx
   ```

2. **Get certificates:**
   ```bash
   sudo certbot --nginx -d your-domain.com
   ```

3. **Update docker-compose.yml:**
   ```yaml
   nginx:
     ports:
       - "443:443"
       - "80:80"
     volumes:
       - /etc/letsencrypt:/etc/letsencrypt:ro
   ```

### Custom SSL Certificates

```yaml
nginx:
  volumes:
    - ./ssl/cert.pem:/etc/nginx/ssl/cert.pem:ro
    - ./ssl/key.pem:/etc/nginx/ssl/key.pem:ro
```

## Scaling & High Availability

### Horizontal Scaling

```yaml
# docker-compose.yml
app:
  deploy:
    replicas: 3
  depends_on:
    - db
    - redis
```

### Load Balancing

```nginx
# nginx.conf
upstream app_servers {
    server app1:8000;
    server app2:8000;
    server app3:8000;
}
```

### Database Replication

For high-traffic deployments, consider:
- PostgreSQL read replicas
- Connection pooling with pgbouncer
- Regular backup automation

## Troubleshooting

### Common Issues

1. **Permission denied on data directories:**
   ```bash
   sudo chown -R $USER:$USER docker/data/
   chmod -R 755 docker/data/
   ```

2. **Database connection failed:**
   - Check PostgreSQL logs: `docker-compose logs db`
   - Verify DATABASE_URL in .env.docker
   - Ensure database container is healthy

3. **WebSocket connection issues:**
   - Check CORS_ORIGINS configuration
   - Verify BASE_URL matches your domain
   - Check firewall/proxy settings

4. **Authentication not working:**
   - Verify JWT_SECRET_KEY is set
   - Check admin user creation in logs
   - Ensure cookies are allowed in browser

### Debug Mode

```bash
# Enable debug logging
DEBUG=true
LOG_LEVEL=debug
DATABASE_ECHO=true

# Restart services
docker-compose restart
```

### Performance Issues

1. **High memory usage:**
   - Check for memory leaks in logs
   - Increase container memory limits
   - Monitor with `docker stats`

2. **Slow database queries:**
   - Enable query logging
   - Check connection pool settings
   - Consider database indexing

3. **WebSocket disconnections:**
   - Increase timeout values
   - Check network stability
   - Monitor connection counts

## Security Checklist

- [ ] Change default admin password
- [ ] Use strong JWT_SECRET_KEY (32+ characters)
- [ ] Enable HTTPS/SSL in production
- [ ] Configure firewall rules
- [ ] Regular security updates
- [ ] Monitor access logs
- [ ] Backup encryption
- [ ] Database access restrictions

## Maintenance

### Regular Tasks

1. **Weekly:**
   - Check application logs
   - Verify backup integrity
   - Monitor disk usage

2. **Monthly:**
   - Update Docker images
   - Review security logs
   - Clean old export files

3. **Quarterly:**
   - Security audit
   - Performance review
   - Dependency updates

### Backup Strategy

```bash
# Automated backup script
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
docker-compose exec db pg_dump -U seminar_user seminar_platform | \
  gzip > "backups/db_backup_${DATE}.sql.gz"
```

This production deployment provides a robust, scalable foundation for the Seminar Platform with enterprise-grade features including authentication, analytics, monitoring, and data persistence.