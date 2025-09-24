"""
Enhanced OpenAI Whisper API provider with translation capabilities.
Uses OpenAI's Whisper for ASR + GPT for high-quality Thai translation.
"""
from __future__ import annotations

import asyncio
import io
import wave
from typing import AsyncIterator, Optional

from openai import AsyncOpenAI

from .asr_base import ASRProvider, ASRResult, ASRStream
from ..utils import to_thread


class WhisperGPTStream(ASRStream):
    """Stream that combines Whisper ASR with GPT translation for Thai."""
    
    def __init__(
        self, 
        session_id: str, 
        client: AsyncOpenAI, 
        whisper_model: str,
        gpt_model: str,
        sample_rate: int
    ) -> None:
        self.session_id = session_id
        self.client = client
        self.whisper_model = whisper_model
        self.gpt_model = gpt_model
        self.sample_rate = sample_rate
        self._buffer = bytearray()
        self._queue: asyncio.Queue[Optional[ASRResult]] = asyncio.Queue()
        self._seq = 0
        self._lock = asyncio.Lock()
        
        # Translation prompt for better Thai translation
        self.translation_prompt = """Translate this English text to natural Thai for subtitles. Return only the Thai translation: """

    async def push_audio(self, chunk: bytes, timestamp_ms: int) -> None:
        self._buffer.extend(chunk)
        
        # Process in smaller chunks for real-time feeling
        if len(self._buffer) >= self.sample_rate * 2 * 3:  # 3 seconds of audio
            await self._process_chunk(is_final=False)

    async def mark_segment_end(self) -> None:
        await self._process_chunk(is_final=True)

    async def finalize(self) -> None:
        await self._process_chunk(is_final=True)
        await self._queue.put(None)

    async def _process_chunk(self, *, is_final: bool) -> None:
        if not self._buffer:
            return
            
        async with self._lock:
            payload = bytes(self._buffer)
            if not is_final:
                # Keep some buffer for overlap
                overlap_samples = self.sample_rate * 2 * 1  # 1 second
                self._buffer = self._buffer[-overlap_samples:]
            else:
                self._buffer.clear()
        
        if not payload:
            return

        # Step 1: Whisper ASR (very fast)
        wav_bytes = await to_thread(self._pcm16_to_wav, payload)
        
        try:
            # Create proper file-like object for OpenAI API
            wav_file = io.BytesIO(wav_bytes)
            wav_file.name = "audio.wav"
            wav_file.content_type = "audio/wav"
            wav_file.seek(0)
            
            # Use Whisper for transcription
            transcription_response = await self.client.audio.transcriptions.create(
                model=self.whisper_model,
                file=wav_file,
                language="en",
                response_format="json",
            )
            
            english_text = transcription_response.text.strip()
            if not english_text:
                return
                
            # Step 2: Send English result immediately (fast feedback)
            await self._queue.put(
                ASRResult(
                    session_id=self.session_id,
                    text=english_text,
                    is_final=False,  # English is partial
                    start_ms=0,
                    end_ms=len(payload) // (self.sample_rate * 2) * 1000,
                    confidence=0.95,
                    raw={"language": "en", "type": "transcription"}
                )
            )
            
            # Step 3: GPT translation to Thai (parallel processing)
            # Only translate meaningful phrases (at least 3 words and 10 characters)
            # Also check confidence and avoid translating noise/artifacts
            words = english_text.split()
            if (len(words) >= 3 and 
                len(english_text.strip()) >= 10 and
                not any(word.lower() in ["um", "uh", "ah", "eh", "mmm"] 
                       for word in words)):
                thai_text = await self._translate_to_thai(english_text)
                
                # Only send translation if valid and meaningful
                if (thai_text and 
                    thai_text != english_text and 
                    len(thai_text.strip()) > 2):
                    await self._queue.put(
                        ASRResult(
                            session_id=self.session_id,
                            text=thai_text,
                            is_final=is_final,
                            start_ms=0,
                            end_ms=len(payload) // (self.sample_rate * 2) * 1000,
                            confidence=0.90,
                            raw={"language": "th", "type": "translation", "source": english_text}
                        )
                    )
                
        except Exception as e:
            # Fallback: return what we have
            await self._queue.put(
                ASRResult(
                    session_id=self.session_id,
                    text=f"[Audio processing error: {str(e)}]",
                    is_final=is_final,
                    start_ms=0,
                    end_ms=1000,
                    confidence=0.0,
                    raw={"error": str(e)}
                )
            )

    async def _translate_to_thai(self, english_text: str) -> str:
        """Use GPT for Thai translation with gender-appropriate politeness."""
        if not english_text or len(english_text.strip()) < 3:
            return ""  # Don't translate very short or empty text
            
        # Filter out common false positives and noise
        text_lower = english_text.lower().strip()
        noise_patterns = [
            "thank you", "thanks", "bye", "hello", "hi", 
            "um", "uh", "ah", "oh"
        ]
        if (any(pattern in text_lower for pattern in noise_patterns) and 
            len(text_lower.split()) <= 2):
            return ""  # Don't translate short phrases that might be noise
            
        try:
            # Get gender setting from environment
            import os
            gender = os.getenv("THAI_POLITENESS_GENDER", "female").lower()
            politeness_particle = "ครับ" if gender in ["male", "m", "ครับ"] else "ค่ะ"
            
            system_prompt = f"""You are a Thai translator for live subtitles.
Rules:
1. Translate English to natural Thai
2. Use ONLY {politeness_particle} for politeness (NEVER use ค่ะ/ครับ or mixed forms)
3. Keep it concise for subtitles
4. Return only the Thai translation
5. Do NOT include both gender particles - use {politeness_particle} only"""

            response = await self.client.chat.completions.create(
                model=self.gpt_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Translate: {english_text}"}
                ],
                max_tokens=60,
                temperature=0.1,
            )
            
            thai_text = response.choices[0].message.content.strip()
            
            # Enhanced filtering for invalid responses
            if (thai_text and
                not thai_text.startswith("Sorry") and
                not thai_text.startswith("ขอโทษ") and
                not thai_text.startswith("I can't") and
                not thai_text.startswith("I cannot") and
                "ค่ะ/ครับ" not in thai_text and
                len(thai_text) > 0 and
                thai_text != english_text):
                
                # Clean up any remaining dual politeness particles aggressively
                thai_text = thai_text.replace("ค่ะ/ครับ", politeness_particle)
                thai_text = thai_text.replace("ครับ/ค่ะ", politeness_particle)
                thai_text = thai_text.replace("ค่ะครับ", politeness_particle)
                thai_text = thai_text.replace("ครับค่ะ", politeness_particle)
                thai_text = thai_text.replace(" ค่ะ ครับ", f" {politeness_particle}")
                thai_text = thai_text.replace(" ครับ ค่ะ", f" {politeness_particle}")
                
                # If gender is male, replace any remaining ค่ะ with ครับ
                if gender in ["male", "m", "ครับ"]:
                    thai_text = thai_text.replace("ค่ะ", "ครับ")
                else:
                    # If gender is female, replace any remaining ครับ with ค่ะ
                    thai_text = thai_text.replace("ครับ", "ค่ะ")
                
                return thai_text
            return ""  # Don't return invalid translations
            
        except Exception:
            return ""  # Don't return errors

    def _pcm16_to_wav(self, pcm_data: bytes) -> bytes:
        """Convert PCM16 audio data to WAV format."""
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(pcm_data)
        return buffer.getvalue()

    async def results(self) -> AsyncIterator[ASRResult]:
        while True:
            result = await self._queue.get()
            if result is None:
                break
            yield result


class WhisperGPTProvider(ASRProvider):
    """OpenAI Whisper + GPT provider for English transcription and Thai translation."""
    
    name = "whisper_gpt"

    def __init__(
        self,
        api_key: str,
        whisper_model: str = "whisper-1",
        gpt_model: str = "gpt-3.5-turbo",
    ) -> None:
        self.client = AsyncOpenAI(api_key=api_key)
        self.whisper_model = whisper_model
        self.gpt_model = gpt_model

    async def setup(self) -> None:
        """Setup is minimal for cloud API."""
        pass

    async def create_stream(self, session_id: str, sample_rate: int) -> ASRStream:
        return WhisperGPTStream(
            session_id=session_id,
            client=self.client,
            whisper_model=self.whisper_model,
            gpt_model=self.gpt_model,
            sample_rate=sample_rate,
        )