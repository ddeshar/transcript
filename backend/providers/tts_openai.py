"""
OpenAI Text-to-Speech (TTS) provider with voice selection.
"""

import os
import asyncio
import aiohttp
from typing import List, Optional
import logging

from .tts_base import TTSProvider, TTSVoice, TTSRequest, TTSResult

logger = logging.getLogger(__name__)


class OpenAITTSProvider(TTSProvider):
    """OpenAI TTS provider with multiple voice options."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_key = kwargs.get('api_key') or os.getenv('OPENAI_API_KEY')
        self.model = kwargs.get('model') or os.getenv('OPENAI_TTS_MODEL', 'tts-1')
        self.default_voice = kwargs.get('voice') or os.getenv('OPENAI_TTS_VOICE', 'nova')
        self.default_speed = float(kwargs.get('speed', os.getenv('OPENAI_TTS_SPEED', '1.0')))
        self.base_url = "https://api.openai.com/v1/audio/speech"
        self.session: Optional[aiohttp.ClientSession] = None
        
        # OpenAI TTS voices
        self.voices = [
            TTSVoice(
                id="alloy",
                name="Alloy",
                gender="neutral",
                language="th",
                description="Balanced, clear voice suitable for most content"
            ),
            TTSVoice(
                id="echo",
                name="Echo",
                gender="male",
                language="th",
                description="Deep, resonant male voice"
            ),
            TTSVoice(
                id="fable",
                name="Fable",
                gender="female",
                language="th",
                description="Warm, expressive female voice"
            ),
            TTSVoice(
                id="onyx",
                name="Onyx",
                gender="male",
                language="th",
                description="Strong, authoritative male voice"
            ),
            TTSVoice(
                id="nova",
                name="Nova",
                gender="female",
                language="th",
                description="Bright, energetic female voice"
            ),
            TTSVoice(
                id="shimmer",
                name="Shimmer",
                gender="female",
                language="th",
                description="Gentle, soothing female voice"
            )
        ]
    
    async def setup(self) -> bool:
        """Initialize OpenAI TTS provider."""
        if not self.api_key:
            logger.error("OpenAI API key not found")
            return False
        
        self.session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            timeout=aiohttp.ClientTimeout(total=30)
        )
        
        logger.info("OpenAI TTS provider initialized successfully")
        return True
    
    async def synthesize(self, request: TTSRequest) -> TTSResult:
        """Synthesize speech using OpenAI TTS API."""
        if not self.session:
            await self.setup()
        
        try:
            # Validate voice
            if not self.is_voice_available(request.voice_id):
                default_voice = self.get_default_voice(request.language, "female")
                if default_voice:
                    request.voice_id = default_voice.id
                    logger.warning(f"Voice not found, using default: {request.voice_id}")
                else:
                    return TTSResult(
                        audio_data=b"",
                        format="mp3",
                        sample_rate=22050,
                        duration_ms=0,
                        voice_used=request.voice_id,
                        success=False,
                        error_message="No valid voice available"
                    )
            
            # Prepare request payload
            payload = {
                "model": self.model,
                "input": request.text,
                "voice": request.voice_id,
                "response_format": "mp3",
                "speed": max(0.25, min(4.0, request.speed))  # OpenAI limits: 0.25-4.0
            }
            
            async with self.session.post(self.base_url, json=payload) as response:
                if response.status == 200:
                    audio_data = await response.read()
                    
                    # Estimate duration (rough calculation)
                    # Average: 150 characters per minute for Thai
                    chars_per_second = 2.5
                    duration_ms = int((len(request.text) / chars_per_second) * 1000)
                    
                    return TTSResult(
                        audio_data=audio_data,
                        format="mp3",
                        sample_rate=22050,  # OpenAI default
                        duration_ms=duration_ms,
                        voice_used=request.voice_id,
                        success=True
                    )
                else:
                    error_text = await response.text()
                    logger.error(f"OpenAI TTS API error: {response.status} - {error_text}")
                    return TTSResult(
                        audio_data=b"",
                        format="mp3",
                        sample_rate=22050,
                        duration_ms=0,
                        voice_used=request.voice_id,
                        success=False,
                        error_message=f"API error: {response.status}"
                    )
        
        except Exception as e:
            logger.error(f"OpenAI TTS synthesis error: {str(e)}")
            return TTSResult(
                audio_data=b"",
                format="mp3",
                sample_rate=22050,
                duration_ms=0,
                voice_used=request.voice_id,
                success=False,
                error_message=str(e)
            )
    
    def get_available_voices(self) -> List[TTSVoice]:
        """Get list of available OpenAI voices."""
        return self.voices
    
    def get_supported_languages(self) -> List[str]:
        """Get supported languages."""
        return ["th", "en", "es", "fr", "de", "it", "pt", "ru", "ja", "ko", "zh"]
    
    async def cleanup(self) -> None:
        """Clean up resources."""
        if self.session:
            await self.session.close()
            self.session = None