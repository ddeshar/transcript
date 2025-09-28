from __future__ import annotations

import asyncio
import io
import wave
from pathlib import Path
from typing import AsyncIterator, Optional

from openai import AsyncOpenAI

from .asr_base import ASRProvider, ASRResult, ASRStream
from ..utils import to_thread


class WhisperAPIStream(ASRStream):
    def __init__(
        self, 
        session_id: str, 
        client: AsyncOpenAI, 
        model: str, 
        sample_rate: int,
        temperature: float = 0.0,
        prompt: Optional[str] = None
    ) -> None:
        self.session_id = session_id
        self.client = client
        self.model = model
        self.sample_rate = sample_rate
        self.temperature = temperature
        self.prompt = prompt
        self._buffer: bytearray = bytearray()
        self._queue: asyncio.Queue[Optional[ASRResult]] = asyncio.Queue()
        self._running = False
        self._seq = 0
        self._lock = asyncio.Lock()

    async def push_audio(self, chunk: bytes, timestamp_ms: int) -> None:
        self._buffer.extend(chunk)

    async def mark_segment_end(self) -> None:
        await self._flush(is_final=True)

    async def finalize(self) -> None:
        await self._flush(is_final=True)
        await self._queue.put(None)

    async def _flush(self, *, is_final: bool) -> None:
        if not self._buffer:
            return
        async with self._lock:
            payload = bytes(self._buffer)
            self._buffer.clear()
        if not payload:
            return
        wav_bytes = await to_thread(self._pcm16_to_wav, payload)
        # Create a proper file-like object with all necessary attributes for OpenAI API
        wav_file = io.BytesIO(wav_bytes)
        wav_file.name = "audio.wav"
        # Add content type hint for better format detection
        wav_file.content_type = "audio/wav"
        # Ensure file pointer is at the beginning
        wav_file.seek(0)
        # Prepare API parameters
        api_params = {
            "model": self.model,
            "file": wav_file,
            "language": "en",
            "response_format": "json",
            "temperature": self.temperature
        }
        
        # Add prompt if provided
        if self.prompt:
            api_params["prompt"] = self.prompt
            
        response = await self.client.audio.transcriptions.create(**api_params)
        text = (response.get("text") if isinstance(response, dict) else getattr(response, "text", "")) or ""
        text = text.strip()
        
        # Filter out common hallucinations and artifacts
        import re
        
        # Filter out common hallucinated sounds and artifacts
        hallucination_patterns = [
            r'^(uh|um|mm|hmm|pfft|huh|mhm)$',  # Common sound artifacts
            r'^[.,!?\s]*$',  # Only punctuation
            r'^(bye|hi)\.$',  # Single words with periods (often hallucinated)
            r'disclaimer|sites\.google\.com',  # Known disclaimer artifacts
            r'^[a-zA-Z]$',  # Single letters (often hallucinated)
            r'^(the|a|an|to|and|or|but)$',  # Common single words that are often hallucinated
            r'ignore.*background.*noise',  # Filter out our own prompt being transcribed!
            r'transcribe.*clearly.*spoken',  # Filter out prompt variations
            r'non-speech.*sounds',  # Filter out prompt fragments
            r'translation.*from.*english.*to.*english',  # Filter GPT confusion
            r"i'm sorry.*only provide.*translation",  # Filter GPT responses
            r'^hi\.$'  # Single "Hi." often hallucinated
        ]
        
        for pattern in hallucination_patterns:
            if re.match(pattern, text.lower()):
                import logging
                logging.info(f"Filtered out potential hallucination: '{text}'")
                return
        
        # DEBUG: Log suspicious disclaimer content
        if "disclaimer" in text.lower() or "sites.google.com" in text.lower():
            import logging
            logging.warning(f"[DEBUG] Disclaimer detected from OpenAI: '{text}' - Audio size: {len(wav_bytes)} bytes")
            return  # Skip this entirely
        
        if not text or len(text.strip()) < 2:  # Skip very short content
            return
        self._seq += 1
        # Use session_id + timestamp for unique segment IDs to prevent duplicates
        import time
        unique_segment_id = f"{self.session_id}-{int(time.time() * 1000)}-{self._seq}"
        await self._queue.put(
            ASRResult(
                session_id=self.session_id,
                text=text,
                is_final=is_final,
                start_ms=0,
                end_ms=0,
                confidence=None,
                segment_id=unique_segment_id,
                raw=response if isinstance(response, dict) else response.__dict__,
            )
        )

    def _pcm16_to_wav(self, pcm: bytes) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(pcm)
        buffer.seek(0)
        return buffer.read()

    async def results(self) -> AsyncIterator[ASRResult]:
        while True:
            item = await self._queue.get()
            if item is None:
                break
            yield item


class WhisperCloudASRProvider(ASRProvider):
    name = "whisper_api"

    def __init__(
        self, 
        api_key: Optional[str] = None, 
        model: str = "whisper-1",
        temperature: float = 0.0,
        prompt: Optional[str] = None
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.prompt = prompt
        self._client: Optional[AsyncOpenAI] = None

    async def setup(self) -> None:
        key = self.api_key
        if key is None:
            from ..utils import get_env

            key = get_env("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        self._client = AsyncOpenAI(api_key=key)

    async def create_stream(self, session_id: str, sample_rate: int) -> ASRStream:
        if self._client is None:
            raise RuntimeError("WhisperCloudASRProvider.setup() must be awaited before use.")
        return WhisperAPIStream(
            session_id=session_id, 
            client=self._client, 
            model=self.model, 
            sample_rate=sample_rate,
            temperature=self.temperature,
            prompt=self.prompt
        )


__all__ = ["WhisperCloudASRProvider"]
