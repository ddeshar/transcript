"""
Google Cloud Text-to-Speech provider
"""

import logging
from typing import List

from .tts_base import TTSProvider, TTSRequest, TTSResult, TTSVoice

logger = logging.getLogger(__name__)

try:
    from google.cloud import texttospeech
    GOOGLE_TTS_AVAILABLE = True
except ImportError:
    logger.warning(
        "Google Cloud Text-to-Speech not available. "
        "Install google-cloud-texttospeech"
    )
    GOOGLE_TTS_AVAILABLE = False


class GoogleTTSProvider(TTSProvider):
    """Google Cloud Text-to-Speech provider with high-quality Thai voices"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.client = None
        self._voices_cache = None
        
        # Google Cloud TTS configuration
        self.voice_config = {
            'th': {
                'voice_id': 'th-TH-Standard-A',  # High quality Thai voice
                'gender': 'FEMALE',
                'speaking_rate': 1.0,
                'pitch': 0.0
            },
            'en': {
                'voice_id': 'en-US-Wavenet-F',  # High quality English voice
                'gender': 'FEMALE',
                'speaking_rate': 1.0,
                'pitch': 0.0
            }
        }
    
    async def setup(self) -> bool:
        """Initialize Google Cloud TTS client"""
        if not GOOGLE_TTS_AVAILABLE:
            logger.error("Google Cloud TTS not available")
            return False
        
        try:
            # Initialize the client
            self.client = texttospeech.TextToSpeechClient()
            
            # Test connection by listing voices
            voices_response = self.client.list_voices()
            logger.info(
                f"Google TTS initialized successfully. "
                f"Available voices: {len(voices_response.voices)}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Google TTS: {e}")
            return False
    
    async def synthesize(self, request: TTSRequest) -> TTSResult:
        """Synthesize speech using Google Cloud TTS"""
        if not self.client:
            return TTSResult(
                audio_data=b'',
                format='mp3',
                sample_rate=22050,
                duration_ms=0,
                voice_used='',
                success=False,
                error_message="TTS client not initialized"
            )
        
        try:
            # Get voice configuration
            lang_config = self.voice_config.get(
                request.language, self.voice_config['th']
            )
            
            # Set up the synthesis input
            synthesis_input = texttospeech.SynthesisInput(text=request.text)
            
            # Configure voice
            lang_code = (
                f"{request.language}-TH" if request.language == 'th'
                else "en-US"
            )
            voice = texttospeech.VoiceSelectionParams(
                language_code=lang_code,
                name=request.voice_id or lang_config['voice_id'],
                ssml_gender=getattr(
                    texttospeech.SsmlVoiceGender, lang_config['gender']
                )
            )
            
            # Configure audio format
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=request.speed,
                pitch=request.pitch,
                volume_gain_db=0.0
            )
            
            # Perform synthesis
            response = self.client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config
            )
            
            # Calculate approximate duration (rough estimate)
            duration_ms = len(request.text) * 100  # ~100ms per char
            
            logger.info(
                "Google TTS synthesized %d characters in %s",
                len(request.text), request.language
            )
            
            return TTSResult(
                audio_data=response.audio_content,
                format='mp3',
                sample_rate=22050,
                duration_ms=duration_ms,
                voice_used=voice.name,
                success=True
            )
            
        except Exception as e:
            logger.error("Google TTS synthesis failed: %s", str(e))
            return TTSResult(
                audio_data=b'',
                format='mp3',
                sample_rate=22050,
                duration_ms=0,
                voice_used='',
                success=False,
                error_message=str(e)
            )
    
    def get_available_voices(self) -> List[TTSVoice]:
        """Get available Google Cloud TTS voices"""
        if self._voices_cache:
            return self._voices_cache
        
        if not self.client:
            return []
        
        try:
            response = self.client.list_voices()
            voices = []
            
            for voice in response.voices:
                for lang_code in voice.language_codes:
                    if lang_code in ['th-TH', 'en-US']:
                        gender_map = {
                            0: 'neutral',  # SSML_VOICE_GENDER_UNSPECIFIED
                            1: 'male',     # MALE
                            2: 'female',   # FEMALE
                            3: 'neutral'   # NEUTRAL
                        }
                        
                        voices.append(TTSVoice(
                            id=voice.name,
                            name=voice.name,
                            gender=gender_map.get(
                                voice.ssml_gender, 'neutral'
                            ),
                            language=lang_code[:2],  # 'th' or 'en'
                            accent=lang_code,
                            description=f"Google Cloud {voice.name}"
                        ))
            
            self._voices_cache = voices
            return voices
            
        except Exception as e:
            logger.error("Failed to get Google TTS voices: %s", str(e))
            return []
    
    def get_supported_languages(self) -> List[str]:
        """Get supported language codes"""
        return ['th', 'en']
    
    async def cleanup(self) -> None:
        """Cleanup Google TTS resources"""
        if self.client:
            # Google client doesn't need explicit cleanup
            pass
        logger.info("Google TTS provider cleaned up")