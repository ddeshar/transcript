"""Database models and configuration for the live seminar platform."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    LargeBinary,
    String,
    Text,
    create_engine,
    event,
    text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.types import TypeDecorator, VARCHAR

# Database configuration with environment variable support
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./seminar_platform.db")
DATABASE_POOL_SIZE = int(os.getenv("DATABASE_POOL_SIZE", "10"))
DATABASE_MAX_OVERFLOW = int(os.getenv("DATABASE_MAX_OVERFLOW", "20"))
DATABASE_ECHO = os.getenv("DATABASE_ECHO", "false").lower() == "true"

# Configure engine based on database type
if DATABASE_URL.startswith("postgresql"):
    engine = create_engine(
        DATABASE_URL,
        pool_size=DATABASE_POOL_SIZE,
        max_overflow=DATABASE_MAX_OVERFLOW,
        echo=DATABASE_ECHO,
        pool_pre_ping=True,  # Verify connections before use
        pool_recycle=3600    # Recycle connections every hour
    )
elif DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=DATABASE_ECHO
    )
else:
    # Generic fallback
    engine = create_engine(DATABASE_URL, echo=DATABASE_ECHO)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class JSONType(TypeDecorator):
    """Custom JSON type for SQLAlchemy."""
    impl = VARCHAR
    
    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value)
        return value
    
    def process_result_value(self, value, dialect):
        if value is not None:
            return json.loads(value)
        return value


class SeminarRoom(Base):
    """SQLAlchemy model for seminar rooms."""
    __tablename__ = "seminar_rooms"
    
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String(12), unique=True, index=True, nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    password = Column(String(255), nullable=True)  # Room access password
    max_participants = Column(Integer, nullable=True)  # Room capacity limit
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    
    # Status
    is_live = Column(Boolean, default=False, nullable=False)
    presenter_session_id = Column(String(36), nullable=True)
    
    # Statistics
    total_participants = Column(Integer, default=0)
    max_concurrent_participants = Column(Integer, default=0)
    total_duration_ms = Column(Integer, default=0)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            'room_id': self.room_id,
            'title': self.title,
            'description': self.description,
            'password': self.password,
            'max_participants': self.max_participants,
            'created_at': (
                self.created_at.isoformat() if self.created_at else None
            ),
            'started_at': (
                self.started_at.isoformat() if self.started_at else None
            ),
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'is_live': self.is_live,
            'presenter_session_id': self.presenter_session_id,
            'total_participants': self.total_participants,
            'max_concurrent_participants': self.max_concurrent_participants,
            'total_duration_ms': self.total_duration_ms,
        }
    
    def get_room_url(self, base_url: str) -> str:
        """Generate the participant URL for this room."""
        return f"{base_url}/room/{self.room_id}"
    
    def get_presenter_url(self, base_url: str) -> str:
        """Generate the presenter control URL for this room."""
        return f"{base_url}/present/{self.room_id}"


class AudioSegment(Base):
    """SQLAlchemy model for audio segments."""
    __tablename__ = "audio_segments"
    
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String(12), index=True, nullable=False)
    segment_id = Column(String(50), unique=True, nullable=False)
    
    # Timing
    timestamp_ms = Column(Integer, nullable=False)
    duration_ms = Column(Integer, nullable=False)
    sequence_number = Column(Integer, nullable=False)
    
    # Audio data (legacy binary storage)
    audio_data_en = Column(LargeBinary, nullable=True)  # English audio
    audio_data_th = Column(LargeBinary, nullable=True)  # Thai audio
    
    # File paths (new file-based storage)
    file_path_en = Column(String(500), nullable=True)  # English audio file
    file_path_th = Column(String(500), nullable=True)  # Thai audio file
    
    # Metadata
    sample_rate = Column(Integer, default=16000)
    channels = Column(Integer, default=1)
    format = Column(String(10), default="wav")
    size_bytes = Column(Integer, nullable=False)
    
    # Processing status
    is_processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            'segment_id': self.segment_id,
            'room_id': self.room_id,
            'timestamp_ms': self.timestamp_ms,
            'duration_ms': self.duration_ms,
            'sequence_number': self.sequence_number,
            'sample_rate': self.sample_rate,
            'channels': self.channels,
            'format': self.format,
            'size_bytes': self.size_bytes,
            'is_processed': self.is_processed,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class SubtitleSegment(Base):
    """SQLAlchemy model for subtitle segments."""
    __tablename__ = "subtitle_segments"
    
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String(12), index=True, nullable=False)
    segment_id = Column(String(50), unique=True, nullable=False)
    
    # Timing
    timestamp_ms = Column(Integer, nullable=False)
    duration_ms = Column(Integer, nullable=False)
    sequence_number = Column(Integer, nullable=False)
    
    # Subtitle content
    text_en = Column(Text, nullable=True)  # English text
    text_th = Column(Text, nullable=True)  # Thai text
    confidence_en = Column(Integer, nullable=True)  # ASR confidence (0-100)
    confidence_th = Column(Integer, nullable=True)  # Translation confidence
    
    # Processing metadata
    asr_provider = Column(String(20), nullable=True)  # vosk, whisper, etc.
    mt_provider = Column(String(20), nullable=True)  # marian, gtranslate
    processing_time_ms = Column(Integer, nullable=True)
    
    # Status
    is_final = Column(Boolean, default=False)
    is_visible = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            'segment_id': self.segment_id,
            'room_id': self.room_id,
            'timestamp_ms': self.timestamp_ms,
            'duration_ms': self.duration_ms,
            'sequence_number': self.sequence_number,
            'text_en': self.text_en,
            'text_th': self.text_th,
            'confidence_en': self.confidence_en,
            'confidence_th': self.confidence_th,
            'asr_provider': self.asr_provider,
            'mt_provider': self.mt_provider,
            'processing_time_ms': self.processing_time_ms,
            'is_final': self.is_final,
            'is_visible': self.is_visible,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class SessionHistory(Base):
    """SQLAlchemy model for session history and analytics."""
    __tablename__ = "session_history"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(36), unique=True, nullable=False)
    room_id = Column(String(12), index=True, nullable=False)
    
    # Session details
    session_type = Column(String(20), nullable=False)  # presenter, participant
    user_agent = Column(String(500), nullable=True)
    ip_address = Column(String(45), nullable=True)
    
    # Timing
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    
    # Activity metrics
    messages_sent = Column(Integer, default=0)
    messages_received = Column(Integer, default=0)
    audio_segments_processed = Column(Integer, default=0)
    
    # Quality metrics
    avg_latency_ms = Column(Integer, nullable=True)
    error_count = Column(Integer, default=0)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            'session_id': self.session_id,
            'room_id': self.room_id,
            'session_type': self.session_type,
            'user_agent': self.user_agent,
            'ip_address': self.ip_address,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'duration_ms': self.duration_ms,
            'messages_sent': self.messages_sent,
            'messages_received': self.messages_received,
            'audio_segments_processed': self.audio_segments_processed,
            'avg_latency_ms': self.avg_latency_ms,
            'error_count': self.error_count,
        }


class ParticipantEvent(Base):
    """SQLAlchemy model for tracking participant join/leave events."""
    __tablename__ = "participant_events"
    
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String(12), index=True, nullable=False)
    session_id = Column(String(36), nullable=False)
    
    # Event details
    event_type = Column(String(10), nullable=False)  # join, leave
    participant_id = Column(String(36), nullable=False)  # unique ID
    participant_name = Column(String(100), nullable=True)  # display name
    
    # Connection details
    user_agent = Column(String(500), nullable=True)
    ip_address = Column(String(45), nullable=True)
    referrer = Column(String(500), nullable=True)
    
    # Timing
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Event metadata  
    event_metadata = Column(JSONType, nullable=True)  # Additional event data
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            'id': self.id,
            'room_id': self.room_id,
            'session_id': self.session_id,
            'event_type': self.event_type,
            'participant_id': self.participant_id,
            'participant_name': self.participant_name,
            'user_agent': self.user_agent,
            'ip_address': self.ip_address,
            'referrer': self.referrer,
            'timestamp': self.timestamp.isoformat(),
            'event_metadata': self.event_metadata,
        }


class ParticipantStats(Base):
    """SQLAlchemy model for aggregated participant statistics."""
    __tablename__ = "participant_stats"
    
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String(12), index=True, nullable=False)
    
    # Time window for stats (5-minute intervals)
    time_window = Column(DateTime, nullable=False, index=True)
    
    # Participant counts
    current_participants = Column(Integer, default=0)
    peak_participants = Column(Integer, default=0)
    total_joins = Column(Integer, default=0)
    total_leaves = Column(Integer, default=0)
    
    # Engagement metrics
    avg_session_duration_ms = Column(Integer, nullable=True)
    bounce_rate_percent = Column(Integer, nullable=True)  # % who left quickly
    
    # Geographic data (optional)
    unique_countries = Column(Integer, nullable=True)
    unique_cities = Column(Integer, nullable=True)
    
    # Technology stats
    device_stats = Column(JSONType, nullable=True)  # mobile, desktop breakdown
    browser_stats = Column(JSONType, nullable=True)  # browser usage
    
    # Quality metrics
    connection_issues = Column(Integer, default=0)
    avg_latency_ms = Column(Integer, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            'id': self.id,
            'room_id': self.room_id,
            'time_window': self.time_window.isoformat(),
            'current_participants': self.current_participants,
            'peak_participants': self.peak_participants,
            'total_joins': self.total_joins,
            'total_leaves': self.total_leaves,
            'avg_session_duration_ms': self.avg_session_duration_ms,
            'bounce_rate_percent': self.bounce_rate_percent,
            'unique_countries': self.unique_countries,
            'unique_cities': self.unique_cities,
            'device_stats': self.device_stats,
            'browser_stats': self.browser_stats,
            'connection_issues': self.connection_issues,
            'avg_latency_ms': self.avg_latency_ms,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }


# Database utility functions
def get_db() -> Session:
    """Get database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)


def init_database():
    """Initialize database with required tables and indexes."""
    create_tables()
    
    # Add any required indexes
    with engine.connect() as conn:
        # Index for efficient room lookup
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_audio_segments_room_timestamp 
            ON audio_segments(room_id, timestamp_ms)
        """))
        
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_subtitle_segments_room_timestamp 
            ON subtitle_segments(room_id, timestamp_ms)
        """))
        
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_session_history_room_started 
            ON session_history(room_id, started_at)
        """))
        
        conn.commit()


# Event listeners for automatic data management
@event.listens_for(SubtitleSegment, 'before_update')
def update_subtitle_timestamp(mapper, connection, target):
    # pylint: disable=unused-argument
    """Update timestamp when subtitle is modified."""
    target.updated_at = datetime.utcnow()


@event.listens_for(SessionHistory, 'before_update')
def calculate_session_duration(mapper, connection, target):
    # pylint: disable=unused-argument
    """Calculate session duration when ended."""
    if target.ended_at and target.started_at:
        target.duration_ms = int(
            (target.ended_at - target.started_at).total_seconds() * 1000
        )


if __name__ == "__main__":
    # Initialize database when run directly
    print("Initializing database...")
    init_database()
    print("Database initialized successfully!")