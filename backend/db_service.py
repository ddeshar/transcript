"""Database service layer for the live seminar platform."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from .database import (
    AudioSegment,
    SessionHistory,
    SeminarRoom,
    SubtitleSegment,
    get_db,
)


class DatabaseService:
    """Service layer for database operations."""

    @staticmethod
    def create_room(
        db: Session, title: str, description: str = None, 
        password: str = None, max_participants: int = None
    ) -> SeminarRoom:
        """Create a new seminar room."""
        room = SeminarRoom(
            room_id=uuid4().hex[:12],
            title=title,
            description=description,
            password=password,
            max_participants=max_participants,
        )
        db.add(room)
        db.commit()
        db.refresh(room)
        return room

    @staticmethod
    def get_room(db: Session, room_id: str) -> SeminarRoom | None:
        """Get a seminar room by ID."""
        return db.query(SeminarRoom).filter(
            SeminarRoom.room_id == room_id
        ).first()

    @staticmethod
    def get_all_rooms(db: Session) -> List[SeminarRoom]:
        """Get all seminar rooms, ordered by creation date."""
        return db.query(SeminarRoom).order_by(
            SeminarRoom.created_at.desc()
        ).all()

    @staticmethod
    def update_room_status(
        db: Session, 
        room_id: str, 
        is_live: bool, 
        presenter_session_id: str = None
    ) -> SeminarRoom | None:
        """Update room live status."""
        room = db.query(SeminarRoom).filter(
            SeminarRoom.room_id == room_id
        ).first()
        
        if not room:
            return None
            
        room.is_live = is_live
        
        if is_live and not room.started_at:
            room.started_at = datetime.utcnow()
            room.presenter_session_id = presenter_session_id
        elif not is_live and room.started_at and not room.ended_at:
            room.ended_at = datetime.utcnow()
            # Calculate total duration
            if room.started_at:
                duration = room.ended_at - room.started_at
                room.total_duration_ms = int(duration.total_seconds() * 1000)
        
        db.commit()
        db.refresh(room)
        return room

    @staticmethod
    def update_presenter_session(
        db: Session, 
        room_id: str, 
        presenter_session_id: Optional[str]
    ) -> SeminarRoom | None:
        """Update room presenter session ID."""
        room = db.query(SeminarRoom).filter(
            SeminarRoom.room_id == room_id
        ).first()
        
        if room:
            room.presenter_session_id = presenter_session_id
            db.commit()
            db.refresh(room)
        return room

    @staticmethod
    def update_room_participants(
        db: Session, 
        room_id: str, 
        participant_count: int
    ) -> None:
        """Update room participant statistics."""
        room = db.query(SeminarRoom).filter(
            SeminarRoom.room_id == room_id
        ).first()
        
        if room:
            room.total_participants = max(
                room.total_participants, participant_count
            )
            room.max_concurrent_participants = max(
                room.max_concurrent_participants, participant_count
            )
            db.commit()

    @staticmethod
    def save_audio_segment(
        db: Session,
        room_id: str,
        segment_id: str,
        timestamp_ms: int,
        duration_ms: int,
        sequence_number: int,
        audio_data: bytes,
        audio_language: str = "en",
        sample_rate: int = 16000,
        channels: int = 1,
        format: str = "wav",
        file_path: str = None
    ) -> AudioSegment:
        """Save an audio segment to the database."""
        segment = AudioSegment(
            room_id=room_id,
            segment_id=segment_id,
            timestamp_ms=timestamp_ms,
            duration_ms=duration_ms,
            sequence_number=sequence_number,
            sample_rate=sample_rate,
            channels=channels,
            format=format,
            size_bytes=len(audio_data),
        )
        
        # Store audio data and/or file path based on language
        if audio_language == "en":
            segment.audio_data_en = audio_data
            if file_path:
                segment.file_path_en = file_path
        elif audio_language == "th":
            segment.audio_data_th = audio_data
            if file_path:
                segment.file_path_th = file_path
            
        db.add(segment)
        db.commit()
        db.refresh(segment)
        return segment

    @staticmethod
    def save_subtitle_segment(
        db: Session,
        room_id: str,
        segment_id: str,
        timestamp_ms: int,
        duration_ms: int,
        sequence_number: int,
        text_en: str = None,
        text_th: str = None,
        confidence_en: int = None,
        confidence_th: int = None,
        asr_provider: str = None,
        mt_provider: str = None,
        processing_time_ms: int = None,
        is_final: bool = False
    ) -> SubtitleSegment:
        """Save a subtitle segment to the database."""
        segment = SubtitleSegment(
            room_id=room_id,
            segment_id=segment_id,
            timestamp_ms=timestamp_ms,
            duration_ms=duration_ms,
            sequence_number=sequence_number,
            text_en=text_en,
            text_th=text_th,
            confidence_en=confidence_en,
            confidence_th=confidence_th,
            asr_provider=asr_provider,
            mt_provider=mt_provider,
            processing_time_ms=processing_time_ms,
            is_final=is_final,
        )
        
        db.add(segment)
        db.commit()
        db.refresh(segment)
        return segment

    @staticmethod
    def update_subtitle_segment_text(
        db: Session,
        room_id: str,
        segment_id: str,
        text_en: str = None,
        text_th: str = None
    ) -> SubtitleSegment:
        """Update text content of an existing subtitle segment."""
        segment = db.query(SubtitleSegment).filter(
            SubtitleSegment.room_id == room_id,
            SubtitleSegment.segment_id == segment_id
        ).first()
        
        if segment:
            if text_en is not None:
                segment.text_en = text_en
            if text_th is not None:
                segment.text_th = text_th
            
            db.commit()
            db.refresh(segment)
            return segment
        else:
            raise ValueError(f"Subtitle segment not found: {room_id}/{segment_id}")

    @staticmethod
    def get_audio_segments(
        db: Session, 
        room_id: str,
        start_timestamp: int = None,
        end_timestamp: int = None
    ) -> List[AudioSegment]:
        """Get audio segments for a room within a time range."""
        query = db.query(AudioSegment).filter(
            AudioSegment.room_id == room_id
        )
        
        if start_timestamp is not None:
            query = query.filter(AudioSegment.timestamp_ms >= start_timestamp)
        if end_timestamp is not None:
            query = query.filter(AudioSegment.timestamp_ms <= end_timestamp)
            
        return query.order_by(AudioSegment.timestamp_ms).all()

    @staticmethod
    def get_subtitle_segments(
        db: Session, 
        room_id: str,
        start_timestamp: int = None,
        end_timestamp: int = None,
        is_visible: bool = True
    ) -> List[SubtitleSegment]:
        """Get subtitle segments for a room within a time range."""
        query = db.query(SubtitleSegment).filter(
            SubtitleSegment.room_id == room_id,
            SubtitleSegment.is_visible == is_visible
        )
        
        if start_timestamp is not None:
            query = query.filter(SubtitleSegment.timestamp_ms >= start_timestamp)
        if end_timestamp is not None:
            query = query.filter(SubtitleSegment.timestamp_ms <= end_timestamp)
            
        return query.order_by(SubtitleSegment.timestamp_ms).all()

    @staticmethod
    def create_session_history(
        db: Session,
        session_id: str,
        room_id: str,
        session_type: str,
        user_agent: str = None,
        ip_address: str = None
    ) -> SessionHistory:
        """Create a new session history record."""
        session = SessionHistory(
            session_id=session_id,
            room_id=room_id,
            session_type=session_type,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def end_session_history(
        db: Session,
        session_id: str,
        messages_sent: int = 0,
        messages_received: int = 0,
        audio_segments_processed: int = 0,
        avg_latency_ms: int = None,
        error_count: int = 0
    ) -> SessionHistory | None:
        """End a session and update statistics."""
        session = db.query(SessionHistory).filter(
            SessionHistory.session_id == session_id
        ).first()
        
        if session:
            session.ended_at = datetime.utcnow()
            session.messages_sent = messages_sent
            session.messages_received = messages_received
            session.audio_segments_processed = audio_segments_processed
            session.avg_latency_ms = avg_latency_ms
            session.error_count = error_count
            
            db.commit()
            db.refresh(session)
            
        return session

    @staticmethod
    def get_room_statistics(db: Session, room_id: str) -> Dict[str, Any]:
        """Get comprehensive statistics for a room."""
        room = db.query(SeminarRoom).filter(
            SeminarRoom.room_id == room_id
        ).first()
        
        if not room:
            return {}
            
        audio_count = db.query(AudioSegment).filter(
            AudioSegment.room_id == room_id
        ).count()
        
        subtitle_count = db.query(SubtitleSegment).filter(
            SubtitleSegment.room_id == room_id
        ).count()
        
        session_count = db.query(SessionHistory).filter(
            SessionHistory.room_id == room_id
        ).count()
        
        return {
            'room': room.to_dict(),
            'audio_segments': audio_count,
            'subtitle_segments': subtitle_count,
            'total_sessions': session_count,
        }

    @staticmethod
    def export_room_transcript(
        db: Session, 
        room_id: str,
        format: str = "json"
    ) -> Dict[str, Any]:
        """Export complete room transcript with audio and subtitles."""
        room = db.query(SeminarRoom).filter(
            SeminarRoom.room_id == room_id
        ).first()
        
        if not room:
            return {}
            
        subtitles = db.query(SubtitleSegment).filter(
            SubtitleSegment.room_id == room_id,
            SubtitleSegment.is_visible == True
        ).order_by(SubtitleSegment.timestamp_ms).all()
        
        audio_segments = db.query(AudioSegment).filter(
            AudioSegment.room_id == room_id
        ).order_by(AudioSegment.timestamp_ms).all()
        
        return {
            'room_info': room.to_dict(),
            'subtitles': [s.to_dict() for s in subtitles],
            'audio_segments': [a.to_dict() for a in audio_segments],
            'export_timestamp': datetime.utcnow().isoformat(),
        }


# Async wrapper for database operations
class AsyncDatabaseService:
    """Async wrapper for database operations."""
    
    @staticmethod
    async def execute_sync(func, *args, **kwargs):
        """Execute a sync database operation asynchronously."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args, **kwargs)
    
    @classmethod
    async def create_room(cls, title: str, description: str = None, 
                         password: str = None, max_participants: int = None) -> SeminarRoom:
        """Async create room operation."""
        def _create_room():
            db = next(get_db())
            try:
                return DatabaseService.create_room(
                    db, title, description, password, max_participants
                )
            finally:
                db.close()
                
        return await cls.execute_sync(_create_room)
    
    @classmethod
    async def get_room(cls, room_id: str) -> SeminarRoom | None:
        """Async get room operation."""
        def _get_room():
            db = next(get_db())
            try:
                return DatabaseService.get_room(db, room_id)
            finally:
                db.close()
                
        return await cls.execute_sync(_get_room)
    
    @classmethod
    async def save_audio_segment(
        cls,
        room_id: str,
        segment_id: str,
        timestamp_ms: int,
        duration_ms: int,
        sequence_number: int,
        audio_data: bytes,
        audio_language: str = "en",
        **kwargs
    ) -> AudioSegment:
        """Async save audio segment operation."""
        def _save_audio():
            db = next(get_db())
            try:
                return DatabaseService.save_audio_segment(
                    db, room_id, segment_id, timestamp_ms, duration_ms,
                    sequence_number, audio_data, audio_language, **kwargs
                )
            finally:
                db.close()
                
        return await cls.execute_sync(_save_audio)
    
    @classmethod
    async def save_subtitle_segment(
        cls,
        room_id: str,
        segment_id: str,
        timestamp_ms: int,
        duration_ms: int,
        sequence_number: int,
        **subtitle_data
    ) -> SubtitleSegment:
        """Async save subtitle segment operation."""
        def _save_subtitle():
            db = next(get_db())
            try:
                return DatabaseService.save_subtitle_segment(
                    db, room_id, segment_id, timestamp_ms, duration_ms,
                    sequence_number, **subtitle_data
                )
            finally:
                db.close()
                
        return await cls.execute_sync(_save_subtitle)

    @classmethod
    async def get_room_subtitle_segments(
        cls, room_id: str, is_visible: bool = True
    ) -> List[SubtitleSegment]:
        """Async get subtitle segments for a room."""
        def _get_subtitles():
            db = next(get_db())
            try:
                return DatabaseService.get_subtitle_segments(
                    db, room_id, is_visible=is_visible
                )
            finally:
                db.close()
                
        return await cls.execute_sync(_get_subtitles)

    @classmethod
    async def update_subtitle_segment_text(
        cls, room_id: str, segment_id: str, text_en: str = None, text_th: str = None
    ) -> SubtitleSegment:
        """Async update subtitle segment text."""
        def _update_text():
            db = next(get_db())
            try:
                return DatabaseService.update_subtitle_segment_text(
                    db, room_id, segment_id, text_en, text_th
                )
            finally:
                db.close()
                
        return await cls.execute_sync(_update_text)

    @classmethod
    async def update_presenter_session(
        cls, room_id: str, presenter_session_id: Optional[str]
    ) -> SeminarRoom | None:
        """Async update presenter session operation."""
        def _update_presenter():
            db = next(get_db())
            try:
                return DatabaseService.update_presenter_session(
                    db, room_id, presenter_session_id
                )
            finally:
                db.close()
                
        return await cls.execute_sync(_update_presenter)

    @classmethod
    async def start_room(
        cls, room_id: str, presenter_session_id: str
    ) -> SeminarRoom | None:
        """Start a room session."""
        def _start_room():
            db = next(get_db())
            try:
                return DatabaseService.update_room_status(
                    db, room_id, True, presenter_session_id
                )
            finally:
                db.close()
                
        return await cls.execute_sync(_start_room)

    @classmethod
    async def end_room(cls, room_id: str) -> SeminarRoom | None:
        """End a room session."""
        def _end_room():
            db = next(get_db())
            try:
                return DatabaseService.update_room_status(
                    db, room_id, False
                )
            finally:
                db.close()
                
        return await cls.execute_sync(_end_room)

    @classmethod
    async def get_active_rooms(cls) -> List[SeminarRoom]:
        """Get all active (live) rooms."""
        def _get_active_rooms():
            db = next(get_db())
            try:
                return db.query(SeminarRoom).filter(
                    SeminarRoom.is_live.is_(True)
                ).all()
            finally:
                db.close()
                
        return await cls.execute_sync(_get_active_rooms)

    @classmethod
    async def list_rooms(cls) -> List[SeminarRoom]:
        """List all rooms."""
        def _list_rooms():
            db = next(get_db())
            try:
                return DatabaseService.get_all_rooms(db)
            finally:
                db.close()
                
        return await cls.execute_sync(_list_rooms)

    @classmethod
    async def get_stable_session_id(cls, room_id: str) -> str:
        """Get or create a stable session ID for a room."""
        import hashlib
        # Generate a deterministic session ID based on room ID
        # This ensures the same room always gets the same session ID
        stable_id = hashlib.md5(f"room_{room_id}_stable".encode()).hexdigest()
        return stable_id

    # Participant Analytics Methods
    @classmethod
    async def record_participant_event(
        cls,
        room_id: str,
        session_id: str,
        event_type: str,  # "join" or "leave"
        participant_id: str,
        participant_name: str = None,
        user_agent: str = None,
        ip_address: str = None,
        metadata: Dict[str, Any] = None
    ):
        """Record a participant join/leave event."""
        def _record_event():
            from .database import ParticipantEvent
            db = next(get_db())
            try:
                event = ParticipantEvent(
                    room_id=room_id,
                    session_id=session_id,
                    event_type=event_type,
                    participant_id=participant_id,
                    participant_name=participant_name,
                    user_agent=user_agent,
                    ip_address=ip_address,
                    metadata=metadata or {}
                )
                db.add(event)
                db.commit()
                return event
            finally:
                db.close()
                
        await cls.execute_sync(_record_event)
        
        # Update real-time stats
        await cls.update_participant_stats(room_id)

    @classmethod
    async def update_participant_stats(cls, room_id: str):
        """Update participant statistics for the current time window."""
        def _update_stats():
            from .database import ParticipantEvent, ParticipantStats
            from datetime import datetime, timedelta
            import math
            
            db = next(get_db())
            try:
                now = datetime.utcnow()
                # Round to nearest 5-minute window
                window_start = now.replace(
                    minute=(now.minute // 5) * 5, second=0, microsecond=0
                )
                
                # Get or create stats record for this window
                stats = db.query(ParticipantStats).filter(
                    ParticipantStats.room_id == room_id,
                    ParticipantStats.time_window == window_start
                ).first()
                
                if not stats:
                    stats = ParticipantStats(
                        room_id=room_id,
                        time_window=window_start
                    )
                    db.add(stats)
                
                # Calculate current participants
                window_end = window_start + timedelta(minutes=5)
                
                # Get all events in this window
                events = db.query(ParticipantEvent).filter(
                    ParticipantEvent.room_id == room_id,
                    ParticipantEvent.timestamp >= window_start,
                    ParticipantEvent.timestamp < window_end
                ).order_by(ParticipantEvent.timestamp).all()
                
                # Calculate stats
                current_count = 0
                peak_count = 0
                total_joins = 0
                total_leaves = 0
                
                for event in events:
                    if event.event_type == "join":
                        current_count += 1
                        total_joins += 1
                    elif event.event_type == "leave":
                        current_count = max(0, current_count - 1)
                        total_leaves += 1
                    
                    peak_count = max(peak_count, current_count)
                
                # Update stats
                stats.current_participants = current_count
                stats.peak_participants = max(stats.peak_participants or 0, peak_count)
                stats.total_joins = total_joins
                stats.total_leaves = total_leaves
                
                db.commit()
                return stats
            finally:
                db.close()
                
        return await cls.execute_sync(_update_stats)

    @classmethod
    async def get_participant_stats(cls, room_id: str, hours: int = 24):
        """Get participant statistics for a room over the last N hours."""
        def _get_stats():
            from .database import ParticipantStats
            from datetime import datetime, timedelta
            
            db = next(get_db())
            try:
                since = datetime.utcnow() - timedelta(hours=hours)
                
                return db.query(ParticipantStats).filter(
                    ParticipantStats.room_id == room_id,
                    ParticipantStats.time_window >= since
                ).order_by(ParticipantStats.time_window).all()
            finally:
                db.close()
                
        return await cls.execute_sync(_get_stats)

    @classmethod
    async def get_participant_events(cls, room_id: str, hours: int = 24):
        """Get all participant events for a room."""
        def _get_events():
            from .database import ParticipantEvent
            from datetime import datetime, timedelta
            
            db = next(get_db())
            try:
                since = datetime.utcnow() - timedelta(hours=hours)
                
                return db.query(ParticipantEvent).filter(
                    ParticipantEvent.room_id == room_id,
                    ParticipantEvent.timestamp >= since
                ).order_by(ParticipantEvent.timestamp).all()
            finally:
                db.close()
                
        return await cls.execute_sync(_get_events)

    @classmethod
    async def get_current_participant_count(cls, room_id: str):
        """Get the current number of active participants."""
        def _get_count():
            from .database import ParticipantEvent
            from datetime import datetime, timedelta
            
            db = next(get_db())
            try:
                # Look at events in the last hour to determine current count
                since = datetime.utcnow() - timedelta(hours=1)
                
                events = db.query(ParticipantEvent).filter(
                    ParticipantEvent.room_id == room_id,
                    ParticipantEvent.timestamp >= since
                ).order_by(ParticipantEvent.timestamp).all()
                
                # Track unique participants and their last action
                participant_status = {}
                for event in events:
                    participant_status[event.participant_id] = event.event_type
                
                # Count participants whose last action was "join"
                current_count = sum(
                    1 for status in participant_status.values() 
                    if status == "join"
                )
                
                return current_count
            finally:
                db.close()
                
        return await cls.execute_sync(_get_count)