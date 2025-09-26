"""
Base Text-to-Speech (TTS) provider interface.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
import asyncio
from dataclasses import dataclass


@dataclass
class TTSVoice:
    """Voice configuration for TTS."""
    id: str
    name: str
    gender: str  # 'male', 'female', 'neutral'
    language: str
    accent: Optional[str] = None
    description: Optional[str] = None


@dataclass
class TTSRequest:
    """TTS request parameters."""
    text: str
    voice_id: str
    speed: float = 1.0
    pitch: float = 1.0
    volume: float = 1.0
    language: str = "th"


@dataclass
class TTSResult:
    """TTS synthesis result."""
    audio_data: bytes
    format: str  # 'mp3', 'wav', 'ogg'
    sample_rate: int
    duration_ms: int
    voice_used: str
    success: bool = True
    error_message: Optional[str] = None


class TTSProvider(ABC):
    """Base class for TTS providers."""
    
    def __init__(self, **kwargs):
        self.config = kwargs
    
    @abstractmethod
    async def setup(self) -> bool:
        """Initialize the TTS provider."""
        pass
    
    @abstractmethod
    async def synthesize(self, request: TTSRequest) -> TTSResult:
        """Synthesize speech from text."""
        pass
    
    @abstractmethod
    def get_available_voices(self) -> List[TTSVoice]:
        """Get list of available voices."""
        pass
    
    @abstractmethod
    def get_supported_languages(self) -> List[str]:
        """Get list of supported language codes."""
        pass
    
    async def cleanup(self) -> None:
        """Clean up resources."""
        pass
    
    def is_voice_available(self, voice_id: str) -> bool:
        """Check if a voice ID is available."""
        voices = self.get_available_voices()
        return any(voice.id == voice_id for voice in voices)
    
    def get_default_voice(self, language: str = "th", gender: str = "female") -> Optional[TTSVoice]:
        """Get default voice for language and gender preference."""
        voices = self.get_available_voices()
        
        # Filter by language
        lang_voices = [v for v in voices if v.language == language]
        if not lang_voices:
            return voices[0] if voices else None
        
        # Filter by gender preference
        gender_voices = [v for v in lang_voices if v.gender == gender]
        return gender_voices[0] if gender_voices else lang_voices[0]