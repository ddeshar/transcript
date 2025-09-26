"""
Mock Text-to-Speech (TTS) provider for testing and development.
"""

import asyncio
from typing import List
import logging

from .tts_base import TTSProvider, TTSVoice, TTSRequest, TTSResult

logger = logging.getLogger(__name__)


class MockTTSProvider(TTSProvider):
    """Mock TTS provider for testing purposes."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Mock voices for testing
        self.voices = [
            TTSVoice(
                id="mock_thai_female",
                name="Mock Thai Female",
                gender="female",
                language="th",
                description="Mock Thai female voice for testing"
            ),
            TTSVoice(
                id="mock_thai_male",
                name="Mock Thai Male",
                gender="male",
                language="th",
                description="Mock Thai male voice for testing"
            ),
            TTSVoice(
                id="mock_en_female",
                name="Mock English Female",
                gender="female",
                language="en",
                description="Mock English female voice for testing"
            )
        ]
    
    async def setup(self) -> bool:
        """Initialize mock TTS provider."""
        logger.info("Mock TTS provider initialized successfully")
        return True
    
    async def synthesize(self, request: TTSRequest) -> TTSResult:
        """Mock synthesis - returns empty audio data."""
        
        # Simulate processing delay
        await asyncio.sleep(0.1)
        
        logger.info(f"Mock TTS synthesis: '{request.text[:50]}...' "
                   f"(voice: {request.voice_id})")
        
        # Calculate mock duration based on text length
        # Approximate 150 characters per minute for Thai
        chars_per_second = 2.5
        duration_ms = int((len(request.text) / chars_per_second) * 1000)
        
        return TTSResult(
            audio_data=b"",  # Empty for mock
            format="mp3",
            sample_rate=22050,
            duration_ms=duration_ms,
            voice_used=request.voice_id,
            success=True
        )
    
    def get_available_voices(self) -> List[TTSVoice]:
        """Get list of available mock voices."""
        return self.voices
    
    def get_supported_languages(self) -> List[str]:
        """Get supported languages."""
        return ["th", "en"]
    
    async def cleanup(self) -> None:
        """Clean up resources (nothing to clean for mock)."""
        pass