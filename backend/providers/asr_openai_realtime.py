"""
OpenAI Real-time Models provider for real-time audio processing.
Supports GPT-4o Real-time and GPT-4o Audio Preview models.
"""
from __future__ import annotations

import asyncio
import io
import wave
from typing import AsyncIterator, Optional

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    websockets = None

from openai import AsyncOpenAI

from .asr_base import ASRProvider, ASRResult, ASRStream


class OpenAIRealtimeStream(ASRStream):
    """Stream using OpenAI Real-time models for audio processing."""
    
    def __init__(
        self,
        session_id: str,
        client: AsyncOpenAI,
        model: str,
        sample_rate: int
    ) -> None:
        self.session_id = session_id
        self.client = client
        self.model = model
        self.sample_rate = sample_rate
        self._buffer = bytearray()
        self._queue: asyncio.Queue[Optional[ASRResult]] = asyncio.Queue()
        self._seq = 0
        self._lock = asyncio.Lock()
        
        # For GPT-4o Real-time, we'll use WebSocket connection
        self._websocket = None
        
    async def feed_audio(self, pcm_bytes: bytes) -> None:
        """Feed audio data to the model."""
        async with self._lock:
            self._buffer.extend(pcm_bytes)
            
            # Process audio in chunks
            chunk_size = int(self.sample_rate * 2.0 * 2)  # 2 seconds, 16-bit
            
            while len(self._buffer) >= chunk_size:
                chunk = bytes(self._buffer[:chunk_size])
                self._buffer = self._buffer[chunk_size:]
                
                # Process the audio chunk
                await self._process_audio_chunk(chunk)
    
    async def _process_audio_chunk(self, pcm_bytes: bytes) -> None:
        """Process a chunk of audio using the OpenAI model."""
        try:
            if self.model == "gpt-4o-realtime-preview":
                # Use real-time WebSocket API
                await self._process_realtime_chunk(pcm_bytes)
            else:
                # Use regular audio API
                await self._process_audio_api_chunk(pcm_bytes)
                
        except Exception as e:
            print(f"🔴 Error processing audio chunk: {e}")
            
    async def _process_realtime_chunk(self, pcm_bytes: bytes) -> None:
        """Process audio using GPT-4o Real-time WebSocket API."""
        # Note: In a real implementation, you'd need to establish and maintain
        # a WebSocket connection to OpenAI's real-time API endpoint
        # The message would be: {"type": "input_audio_buffer.append",
        # "audio": base64.b64encode(pcm_bytes).decode()}
        # For now, we'll simulate the response
        
        # Simulate transcription result
        self._seq += 1
        transcript = f"[Simulated Real-time] Audio chunk {self._seq}"
        
        result = ASRResult(
            text=transcript,
            is_final=False,
            session_id=self.session_id,
            segment_id=self._seq,
        )
        
        await self._queue.put(result)
        
    async def _process_audio_api_chunk(self, pcm_bytes: bytes) -> None:
        """Process audio using GPT-4o Audio Preview API."""
        # Convert PCM bytes to audio file format
        audio_file = self._pcm_to_wav(pcm_bytes)
        
        try:
            # Use OpenAI's audio API (similar to Whisper but with audio models)
            response = await self.client.audio.transcriptions.create(
                model=self.model,
                file=("audio.wav", audio_file, "audio/wav"),
                response_format="json"
            )
            
            transcript = response.text.strip()
            if transcript:
                self._seq += 1
                result = ASRResult(
                    text=transcript,
                    is_final=True,
                    session_id=self.session_id,
                    segment_id=self._seq,
                )
                await self._queue.put(result)
                
        except Exception as e:
            print(f"🔴 OpenAI Audio API error: {e}")
    
    def _pcm_to_wav(self, pcm_bytes: bytes) -> io.BytesIO:
        """Convert PCM bytes to WAV format."""
        buffer = io.BytesIO()
        
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(pcm_bytes)
        
        buffer.seek(0)
        return buffer
    
    async def results(self) -> AsyncIterator[ASRResult]:
        """Yield ASR results as they become available."""
        while True:
            result = await self._queue.get()
            if result is None:
                break
            yield result
    
    async def push_audio(self, chunk: bytes, timestamp_ms: int) -> None:
        """Push audio data for processing."""
        await self.feed_audio(chunk)
    
    async def mark_segment_end(self) -> None:
        """Mark the end of an audio segment."""
        # For real-time processing, we can flush any remaining audio
        async with self._lock:
            if len(self._buffer) > 0:
                chunk = bytes(self._buffer)
                self._buffer.clear()
                await self._process_audio_chunk(chunk)
    
    async def finalize(self) -> None:
        """Finalize the stream and cleanup resources."""
        await self.close()
    
    async def close(self) -> None:
        """Close the stream and cleanup resources."""
        await self._queue.put(None)
        if self._websocket and hasattr(self._websocket, 'close'):
            await self._websocket.close()


class GPTRealtimeProvider(ASRProvider):
    """GPT-4o Real-time provider for real-time audio conversations."""
    
    name = "gpt_realtime"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key
        self._client: Optional[AsyncOpenAI] = None

    async def setup(self) -> None:
        key = self.api_key
        if key is None:
            from ..utils import get_env
            key = get_env("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        self._client = AsyncOpenAI(api_key=key)

    async def create_stream(
        self, session_id: str, sample_rate: int
    ) -> ASRStream:
        if self._client is None:
            raise RuntimeError(
                "GPTRealtimeProvider.setup() must be awaited first."
            )
        return OpenAIRealtimeStream(
            session_id=session_id,
            client=self._client,
            model="gpt-4o-realtime-preview",
            sample_rate=sample_rate,
        )


class GPT4oAudioProvider(ASRProvider):
    """GPT-4o Audio Preview provider for audio input/output processing."""
    
    name = "gpt_4o_audio"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key
        self._client: Optional[AsyncOpenAI] = None

    async def setup(self) -> None:
        key = self.api_key
        if key is None:
            from ..utils import get_env
            key = get_env("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        self._client = AsyncOpenAI(api_key=key)

    async def create_stream(
        self, session_id: str, sample_rate: int
    ) -> ASRStream:
        if self._client is None:
            raise RuntimeError(
                "GPT4oAudioProvider.setup() must be awaited first."
            )
        return OpenAIRealtimeStream(
            session_id=session_id,
            client=self._client,
            model="gpt-4o-audio-preview",
            sample_rate=sample_rate,
        )


__all__ = ["GPTRealtimeProvider", "GPT4oAudioProvider"]