"""
Official OpenAI Whisper (local) provider for faster local inference.
Uses the original whisper package from OpenAI for local processing.
"""
from __future__ import annotations

import asyncio
import io
import numpy as np
import whisper
from pathlib import Path
from typing import AsyncIterator, Optional

from .asr_base import ASRProvider, ASRResult, ASRStream
from ..utils import to_thread


class WhisperLocalStream(ASRStream):
    """Stream using official OpenAI Whisper for local processing."""
    
    def __init__(
        self, 
        session_id: str, 
        model: whisper.Whisper,
        sample_rate: int,
        chunk_duration: float = 2.0
    ) -> None:
        self.session_id = session_id
        self.model = model
        self.sample_rate = sample_rate
        self._buffer = bytearray()
        self._queue: asyncio.Queue[Optional[ASRResult]] = asyncio.Queue()
        self._lock = asyncio.Lock()
        
        # Chunk configuration for real-time processing
        self.chunk_duration = chunk_duration
        self._chunk_size_bytes = int(sample_rate * chunk_duration * 2)  # 16-bit PCM
        self._last_partial_text = ""

    async def push_audio(self, chunk: bytes, timestamp_ms: int) -> None:
        self._buffer.extend(chunk)
        
        # Process when we have enough audio
        if len(self._buffer) >= self._chunk_size_bytes:
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
            if is_final:
                # Use all remaining audio
                pcm_bytes = bytes(self._buffer)
                self._buffer.clear()
            else:
                # Use chunk with overlap for continuity
                pcm_bytes = bytes(self._buffer[:self._chunk_size_bytes])
                # Keep last 0.3 seconds for overlap (optimized for speed)
                overlap_bytes = int(self.sample_rate * 0.3 * 2)
                start_idx = self._chunk_size_bytes - overlap_bytes
                self._buffer[:] = self._buffer[start_idx:]
        
        if not pcm_bytes:
            return

        # Convert PCM to numpy array and transcribe
        try:
            result = await to_thread(self._transcribe_audio, pcm_bytes)
            if result and result["text"].strip():
                text = result["text"].strip()
                
                # Skip duplicate partials
                if not is_final and text == self._last_partial_text:
                    return
                    
                self._last_partial_text = text if not is_final else ""
                
                # Calculate timing
                duration_ms = len(pcm_bytes) // (self.sample_rate * 2) * 1000
                
                await self._queue.put(
                    ASRResult(
                        session_id=self.session_id,
                        text=text,
                        is_final=is_final,
                        start_ms=0,
                        end_ms=duration_ms,
                        confidence=0.95,  # Whisper doesn't provide confidence
                        raw=result
                    )
                )
        except Exception as e:
            print(f"Whisper transcription error: {e}")

    def _transcribe_audio(self, pcm_bytes: bytes) -> dict:
        """Transcribe PCM audio using OpenAI Whisper."""
        # Convert PCM bytes to numpy array
        audio_data = np.frombuffer(pcm_bytes, dtype=np.int16)
        # Normalize to [-1, 1] float32 as required by Whisper
        audio_float = audio_data.astype(np.float32) / 32768.0
        
        # Transcribe with Whisper
        # Using fp16=False for CPU compatibility and temperature=0 for consistency
        result = self.model.transcribe(
            audio_float,
            language="en",
            task="transcribe",
            fp16=False,  # Better CPU compatibility
            temperature=0,  # Consistent results
            beam_size=1,  # Faster decoding
            best_of=1,  # Faster decoding
            condition_on_previous_text=False,  # Avoid context buildup
        )
        
        return result

    async def results(self) -> AsyncIterator[ASRResult]:
        while True:
            result = await self._queue.get()
            if result is None:
                break
            yield result


class WhisperLocalProvider(ASRProvider):
    """Official OpenAI Whisper provider for local processing."""
    
    name = "whisper_local"

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        chunk_duration: float = 2.0,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.chunk_duration = chunk_duration
        self.model = None

    async def setup(self) -> None:
        """Load Whisper model."""
        if self.model is None:
            print(f"🔄 Loading Whisper '{self.model_size}' model...")
            self.model = await to_thread(
                whisper.load_model,
                self.model_size,
                device=self.device
            )
            print(f"✅ Whisper '{self.model_size}' model loaded ({self.device})")

    async def create_stream(self, session_id: str, sample_rate: int) -> ASRStream:
        if self.model is None:
            await self.setup()
            
        return WhisperLocalStream(
            session_id=session_id,
            model=self.model,
            sample_rate=sample_rate,
            chunk_duration=self.chunk_duration,
        )