from __future__ import annotations

import asyncio
import numpy as np
from typing import AsyncIterator, Optional

from .asr_base import ASRProvider, ASRResult, ASRStream
from ..utils import to_thread

try:
    from faster_whisper import WhisperModel
except ImportError:  # pragma: no cover - optional dependency
    WhisperModel = None


class FasterWhisperStream(ASRStream):
    """Streaming ASR using faster-whisper with real-time audio processing."""

    def __init__(
        self,
        session_id: str,
        model: "WhisperModel",
        sample_rate: int,
        chunk_duration: float = 2.0,
        language: str = "en",
        beam_size: int = 1
    ) -> None:
        if WhisperModel is None:
            raise RuntimeError(
                "faster-whisper is not installed. Install with "
                "`pip install faster-whisper` or switch ASR_PROVIDER."
            )
        
        self.session_id = session_id
        self.sample_rate = sample_rate
        self.chunk_duration = chunk_duration
        self.language = language
        self.beam_size = beam_size
        self._model = model
        self._buffer = bytearray()
        self._queue: asyncio.Queue[Optional[ASRResult]] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._last_emitted_end = 0.0
        self._last_partial_text = ""
        
        # Audio processing config
        self._frames_per_chunk = int(sample_rate * chunk_duration)
        self._chunk_size_bytes = self._frames_per_chunk * 2  # 16-bit PCM
        
    async def push_audio(self, chunk: bytes, timestamp_ms: int) -> None:
        """Add audio chunk to buffer and process if enough data."""
        if not chunk:
            return
            
        self._buffer.extend(chunk)
        
        # Process if we have enough audio for a chunk
        if len(self._buffer) >= self._chunk_size_bytes:
            await self._process_audio_chunk(is_final=False)
    
    async def mark_segment_end(self) -> None:
        """Process any remaining audio in buffer as final."""
        await self._process_audio_chunk(is_final=True)
    
    async def finalize(self) -> None:
        """Final processing and close stream."""
        await self._process_audio_chunk(is_final=True)
        await self._queue.put(None)
    
    async def _process_audio_chunk(self, *, is_final: bool) -> None:
        """Process buffered audio with faster-whisper."""
        async with self._lock:
            if not self._buffer:
                return
                
            # Extract chunk from buffer
            if is_final:
                # Use all remaining audio
                pcm_bytes = bytes(self._buffer)
                self._buffer.clear()
            else:
                # Use exact chunk size and keep minimal overlap for speed
                pcm_bytes = bytes(self._buffer[:self._chunk_size_bytes])
                # Keep last 0.2 seconds for overlap (reduced for speed)
                overlap_bytes = int(self.sample_rate * 0.2 * 2)
                start_idx = self._chunk_size_bytes - overlap_bytes
                self._buffer[:] = self._buffer[start_idx:]
        
        if not pcm_bytes:
            return
            
        # Transcribe audio chunk
        segments = await to_thread(self._transcribe_pcm, pcm_bytes)
        
        for start_s, end_s, text in segments:
            text = text.strip()
            if not text:
                continue
                
            # Skip duplicate partials
            if not is_final and text == self._last_partial_text:
                continue
                
            self._last_partial_text = text if not is_final else ""
            
            if is_final:
                self._last_emitted_end = max(self._last_emitted_end, end_s)
            
            await self._queue.put(
                ASRResult(
                    session_id=self.session_id,
                    text=text,
                    is_final=is_final,
                    start_ms=int(start_s * 1000),
                    end_ms=int(end_s * 1000),
                )
            )
    
    def _transcribe_pcm(
        self, pcm_bytes: bytes
    ) -> list[tuple[float, float, str]]:
        """Convert PCM bytes to audio array and transcribe."""
        # Convert 16-bit PCM to float32 numpy array
        audio_data = np.frombuffer(pcm_bytes, dtype=np.int16)
        # Normalize to [-1, 1]
        audio_data = audio_data.astype(np.float32) / 32768.0

        # Transcribe with faster-whisper
        segments, _ = self._model.transcribe(
            audio_data,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=False,  # We handle VAD externally
            word_timestamps=False,  # Disable word-level timestamps for cleaner output
        )

        # Extract segments with timing
        results = []
        for segment in segments:
            start_time = getattr(segment, 'start', 0.0)
            end_time = getattr(segment, 'end', 0.0)
            text = getattr(segment, 'text', '').strip()
            if text:
                results.append((start_time, end_time, text))

        return results
    
    async def results(self) -> AsyncIterator[ASRResult]:
        """Yield transcription results as they become available."""
        while True:
            result = await self._queue.get()
            if result is None:
                break
            yield result


class FasterWhisperASRProvider(ASRProvider):
    """ASR provider using faster-whisper for efficient Whisper inference."""

    name = "faster_whisper"

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "en",
        beam_size: int = 1,
        chunk_duration: float = 2.0
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.beam_size = beam_size
        self.chunk_duration = chunk_duration
        self._model = None

    async def setup(self) -> None:
        """Initialize the faster-whisper model."""
        if WhisperModel is None:
            raise RuntimeError(
                "faster-whisper package not installed. "
                "Install with `pip install faster-whisper`."
            )

        # Load model (this downloads automatically if not present)
        self._model = await to_thread(
            WhisperModel,
            self.model_size,
            device=self.device,
            compute_type=self.compute_type
        )
        print(f"✅ Faster-Whisper model '{self.model_size}' loaded "
              f"(device={self.device}, compute_type={self.compute_type})")

    async def create_stream(
        self, session_id: str, sample_rate: int
    ) -> ASRStream:
        """Create a new transcription stream."""
        if self._model is None:
            raise RuntimeError(
                "FasterWhisperASRProvider.setup() must be awaited before use."
            )

        return FasterWhisperStream(
            session_id=session_id,
            model=self._model,
            sample_rate=sample_rate,
            chunk_duration=self.chunk_duration,
            language=self.language,
            beam_size=self.beam_size,
        )


__all__ = ["FasterWhisperASRProvider"]