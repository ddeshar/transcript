"""Data models for the live seminar platform."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4


@dataclass
class SeminarRoom:
    """A seminar room with live streaming capabilities."""
    room_id: str
    title: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    is_live: bool = False
    presenter_session_id: Optional[str] = None
    audio_segments: List[Dict[str, Any]] = field(default_factory=list)
    subtitle_segments: List[Dict[str, Any]] = field(default_factory=list)
    
    @classmethod
    def create(cls, title: str) -> SeminarRoom:
        """Create a new seminar room with auto-generated ID."""
        return cls(
            room_id=uuid4().hex[:12],  # Shorter, URL-friendly ID
            title=title
        )
    
    def start_live(self, presenter_session_id: str) -> None:
        """Start the live session."""
        self.is_live = True
        self.started_at = datetime.utcnow()
        self.presenter_session_id = presenter_session_id
    
    def end_live(self) -> None:
        """End the live session."""
        self.is_live = False
        self.ended_at = datetime.utcnow()
    
    def add_audio_segment(
        self, timestamp_ms: int, audio_data: bytes, duration_ms: int
    ) -> None:
        """Add an audio segment for replay functionality."""
        self.audio_segments.append({
            'timestamp_ms': timestamp_ms,
            'duration_ms': duration_ms,
            'size_bytes': len(audio_data),
            'segment_id': f'{self.room_id}_{len(self.audio_segments)}'
        })
    
    def add_subtitle_segment(self, segment: Dict[str, Any]) -> None:
        """Add a subtitle segment with English and Thai text."""
        segment['room_id'] = self.room_id
        self.subtitle_segments.append(segment)
    
    def get_room_url(self, base_url: str) -> str:
        """Generate the participant URL for this room."""
        return f"{base_url}/room/{self.room_id}"
    
    def get_presenter_url(self, base_url: str) -> str:
        """Generate the presenter control URL for this room."""
        return f"{base_url}/present/{self.room_id}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'room_id': self.room_id,
            'title': self.title,
            'created_at': self.created_at.isoformat(),
            'started_at': (
                self.started_at.isoformat() if self.started_at else None
            ),
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'is_live': self.is_live,
            'presenter_session_id': self.presenter_session_id,
            'participant_count': len(
                ROOM_PARTICIPANTS.get(self.room_id, set())
            ),
            'audio_segments_count': len(self.audio_segments),
            'subtitle_segments_count': len(self.subtitle_segments),
            'duration_ms': self._get_duration_ms()
        }
    
    def _get_duration_ms(self) -> Optional[int]:
        """Calculate total duration of the seminar."""
        if not self.started_at:
            return None
        end_time = self.ended_at or datetime.utcnow()
        return int((end_time - self.started_at).total_seconds() * 1000)


# Global storage for participants (still needed for WebSocket management)
# room_id -> set of participant WebSocket queues
ROOM_PARTICIPANTS: Dict[str, set] = {}