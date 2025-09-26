# Production Deployment Guide
## English-Thai Real-time Subtitle Platform

This guide covers deploying the English-Thai subtitle platform for production use with complete database persistence, audio recording, and subtitle history.

## 🏗️ Architecture Overview

The production system consists of:
- **FastAPI Backend**: Real-time WebSocket handling, ASR/MT processing, database operations
- **SQLAlchemy Database**: Persistent storage for rooms, audio segments, subtitles, session history  
- **Frontend**: Live subtitle display, room management interface
- **WebSocket Architecture**: Real-time audio streaming and subtitle broadcasting

## 📋 Prerequisites

- Docker and Docker Compose
- PostgreSQL database (or SQLite for smaller deployments)
- At least 8GB RAM for ML models
- 50GB+ storage for audio recordings
- SSL certificates for HTTPS

## 🚀 Deployment Steps

### 1. Environment Configuration

```bash
# Clone and prepare environment
git clone <your-repo>
cd transcript
cp .env.production .env

# Edit .env with your production settings
# Key settings to configure:
# - DATABASE_URL (PostgreSQL recommended)
# - CORS_ORIGINS (your domain)
# - API keys for cloud providers (optional)
# - SSL certificate paths
```

### 2. Database Setup

```bash
# For PostgreSQL production database
createdb subtitles_db
psql subtitles_db -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;"

# Initialize database schema
python scripts/init_production_db.py --with-sample

# Or using Docker:
docker-compose exec backend python scripts/init_production_db.py
```

### 3. Model Downloads

```bash
# Download required ML models (~6GB)
python scripts/download_models.py

# Verify models are available
ls -la models/
# Expected: vosk/, whisper.cpp/, marian/
```

### 4. SSL Configuration

```bash
# Place SSL certificates
mkdir -p ssl/
cp your-cert.pem ssl/cert.pem  
cp your-key.pem ssl/key.pem

# Update docker-compose.yml to mount SSL files
# Configure nginx reverse proxy for HTTPS termination
```

### 5. Production Docker Deployment

```bash
# Build and start services
docker-compose -f docker/docker-compose.yml up -d

# Check service status
docker-compose ps
docker-compose logs backend
docker-compose logs frontend
```

### 6. Nginx Reverse Proxy

Create `/etc/nginx/sites-available/subtitles`:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    # Frontend static files
    location / {
        proxy_pass http://127.0.0.1:5173;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # API endpoints  
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # WebSocket connections
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }
    
    # Health check
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
    }
}
```

Enable and restart nginx:
```bash
sudo ln -s /etc/nginx/sites-available/subtitles /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 🗄️ Database Features

### Core Tables

1. **SeminarRoom**: Room management with lifecycle tracking
   - `room_id`, `title`, `description`
   - `is_live`, `started_at`, `ended_at`
   - `presenter_session_id`, `total_duration_ms`
   - `total_participants`, `created_at`, `updated_at`

2. **AudioSegment**: Raw audio data with metadata
   - Bilingual audio storage (`audio_data_en`, `audio_data_th`)
   - Sample rate, channels, bit depth
   - Sequence tracking and timestamp alignment

3. **SubtitleSegment**: Processed subtitles with confidence scores
   - English and Thai text with confidence metrics
   - Processing time tracking for performance analysis
   - Sequence numbers for proper ordering

4. **SessionHistory**: Analytics and session tracking
   - Connection duration, participant counts
   - Error tracking and performance metrics
   - User session patterns for optimization

### Database Operations

```python
# Create room
room = await AsyncDatabaseService.create_room(
    title="My Seminar", 
    description="Important meeting"
)

# Start live session
await AsyncDatabaseService.start_room(room.room_id, session_id)

# Save audio segment  
await AsyncDatabaseService.save_audio_segment(
    room_id=room.room_id,
    audio_data=audio_bytes,
    audio_language="en",
    sample_rate=16000
)

# Save subtitle segment
await AsyncDatabaseService.save_subtitle_segment(
    room_id=room.room_id,
    text_en="Hello world",
    text_th="สวัสดีชาวโลก", 
    confidence_en=0.95,
    confidence_th=0.92
)

# Get room statistics
stats = DatabaseService.get_room_statistics(db, room.room_id)
```

## 🔧 API Endpoints

### Room Management
- `POST /api/rooms` - Create new room
- `GET /api/rooms` - List all rooms  
- `GET /api/rooms/{room_id}` - Get room details
- `PUT /api/rooms/{room_id}/status` - Update live status

### Real-time Communication
- `WS /ws/transcribe` - Audio streaming for transcription
- `WS /ws/room/{room_id}` - Participant connections
- `WS /ws/follow/{session_id}` - Teleprompter following

### Interfaces  
- `/room/{room_id}` - Participant view
- `/present/{room_id}` - Presenter controls
- `/test-transcribe` - Development testing

## 📊 Monitoring & Analytics

### Health Checks

```bash
# Application health
curl https://your-domain.com/health

# Database connectivity
curl https://your-domain.com/api/rooms

# WebSocket connectivity  
wscat -c wss://your-domain.com/ws/room/test-room-id
```

### Logs and Metrics

```bash
# Application logs
docker-compose logs -f backend

# Database performance
# Monitor connection counts, query performance
SELECT * FROM pg_stat_activity WHERE application_name LIKE 'subtitle%';

# Audio processing metrics
# Check models/ directory for processing times
# Monitor WebSocket connection counts
```

### Performance Optimization

1. **Database Indexing**
   ```sql
   CREATE INDEX idx_room_created_at ON seminar_rooms(created_at);
   CREATE INDEX idx_audio_room_timestamp ON audio_segments(room_id, timestamp_ms);
   CREATE INDEX idx_subtitle_room_sequence ON subtitle_segments(room_id, sequence_number);
   ```

2. **Connection Pooling**
   - Configure `DB_POOL_SIZE` and `DB_MAX_OVERFLOW` in .env
   - Monitor connection usage in production

3. **Audio Storage Optimization**
   - Consider compression for long-term audio storage
   - Implement audio cleanup policies for old recordings
   - Use cloud storage for audio archives

## 🔒 Security Considerations

### API Security
- Enable API key authentication in production
- Configure CORS origins restrictively  
- Use HTTPS everywhere with proper certificates
- Implement rate limiting per the .env configuration

### Database Security
- Use read-only database users for reporting
- Enable connection encryption (SSL)
- Regular backups with encryption
- Monitor for suspicious query patterns

### WebSocket Security  
- Validate room access permissions
- Implement connection limits per room
- Monitor for abuse patterns
- Consider authentication for sensitive rooms

## 📦 Backup & Recovery

### Automated Backups
```bash
# Database backup
pg_dump subtitles_db > backup-$(date +%Y%m%d).sql

# Audio files backup  
tar -czf audio-backup-$(date +%Y%m%d).tar.gz data/audio/

# Full system backup
docker-compose exec backend python scripts/export_room_data.py --all
```

### Recovery Procedures
```bash
# Database restore
psql subtitles_db < backup-20241225.sql

# Verify data integrity
python scripts/verify_database.py
```

## 🚨 Troubleshooting

### Common Issues

1. **WebSocket Connection Failures**
   - Check nginx WebSocket proxy configuration
   - Verify SSL certificate validity
   - Monitor connection limits and timeouts

2. **Audio Processing Errors**
   - Verify models are downloaded and accessible
   - Check available memory for ML processing
   - Monitor audio chunk sizes and sample rates

3. **Database Performance**
   - Monitor connection pool exhaustion
   - Check for slow queries and optimize indexes
   - Verify disk space for audio storage

### Debug Mode

```bash
# Enable debug logging
echo "LOG_LEVEL=DEBUG" >> .env
docker-compose restart backend

# Test audio pipeline  
python scripts/simulate_client.py --audio sample_audio/en_sample.wav --room-id test-room
```

## 📈 Scaling Considerations

### Horizontal Scaling
- Use Redis for session management across instances
- Implement database read replicas for reporting
- Consider microservices for ASR and MT processing
- Use load balancers for WebSocket connections

### Storage Scaling  
- Implement audio archiving to cloud storage
- Use database partitioning for large subtitle tables
- Consider CDN for frontend asset delivery

## ✅ Production Checklist

- [ ] Environment variables configured
- [ ] Database schema initialized
- [ ] ML models downloaded and tested
- [ ] SSL certificates installed and valid
- [ ] Nginx reverse proxy configured
- [ ] Health checks responding
- [ ] Room creation/management working
- [ ] WebSocket connections functional
- [ ] Audio/subtitle saving to database
- [ ] Monitoring and logging configured
- [ ] Backup procedures tested
- [ ] Security hardening applied

## 🎯 Success Metrics

After deployment, verify:
- Room creation and participant connections work
- Real-time subtitles display with < 2s latency
- Audio segments save to database without errors
- Subtitle confidence scores > 85% for clear speech
- System handles concurrent sessions as per configuration
- Database performance meets response time requirements

The platform is now production-ready with complete database persistence, audio recording capabilities, and comprehensive subtitle history for analytics and replay functionality.