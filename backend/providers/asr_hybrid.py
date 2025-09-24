"""
Hybrid ASR provider: Fast local English + Delayed high-quality Thai translation.
Shows English transcription immediately (~300ms) then Thai translation later (~3-4s).
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional

from .asr_base import ASRProvider, ASRResult, ASRStream
from .asr_faster_whisper import FasterWhisperASRProvider
from .asr_whisper_gpt import WhisperGPTProvider
from .asr_whisper_local import WhisperLocalProvider


class HybridStream(ASRStream):
    """Hybrid stream that combines fast local ASR with delayed cloud translation."""
    
    def __init__(
        self, 
        session_id: str,
        fast_stream: ASRStream,
        quality_stream: ASRStream,
        use_quality_stream: bool = True
    ) -> None:
        self.session_id = session_id
        self.fast_stream = fast_stream
        self.quality_stream = quality_stream
        self.use_quality_stream = use_quality_stream
        self._queue: asyncio.Queue[Optional[ASRResult]] = asyncio.Queue()
        
        # Start result forwarding tasks
        self._fast_task = asyncio.create_task(self._forward_fast_results())
        if self.use_quality_stream:
            self._quality_task = asyncio.create_task(
                self._forward_quality_results()
            )

    async def push_audio(self, chunk: bytes, timestamp_ms: int) -> None:
        # Send audio to both streams
        await self.fast_stream.push_audio(chunk, timestamp_ms)
        if self.use_quality_stream:
            await self.quality_stream.push_audio(chunk, timestamp_ms)

    async def mark_segment_end(self) -> None:
        await self.fast_stream.mark_segment_end()
        if self.use_quality_stream:
            await self.quality_stream.mark_segment_end()

    async def finalize(self) -> None:
        await self.fast_stream.finalize()
        if self.use_quality_stream:
            await self.quality_stream.finalize()
        
        # Wait for forwarding tasks to complete
        self._fast_task.cancel()
        if hasattr(self, '_quality_task'):
            self._quality_task.cancel()
        
        await self._queue.put(None)

    async def _forward_fast_results(self) -> None:
        """Forward results from fast local ASR (English)."""
        try:
            async for result in self.fast_stream.results():
                # Mark as English and fast
                result.raw = result.raw or {}
                result.raw.update({
                    "source": "fast_local",
                    "language": "en", 
                    "speed": "immediate"
                })
                await self._queue.put(result)
        except asyncio.CancelledError:
            pass

    async def _forward_quality_results(self) -> None:
        """Forward results from quality cloud ASR+MT (Thai)."""
        try:
            async for result in self.quality_stream.results():
                # Mark as Thai translation and delayed
                result.raw = result.raw or {}
                result.raw.update({
                    "source": "quality_cloud",
                    "language": "th",
                    "speed": "delayed"
                })
                await self._queue.put(result)
        except asyncio.CancelledError:
            pass

    async def results(self) -> AsyncIterator[ASRResult]:
        while True:
            result = await self._queue.get()
            if result is None:
                break
            yield result


class HybridASRProvider(ASRProvider):
    """
    Hybrid ASR provider combining fast local ASR with quality cloud translation.
    
    Workflow:
    1. Fast stream (faster-whisper): English transcription in ~300ms
    2. Quality stream (whisper API + GPT): Thai translation in ~3-4s
    3. Frontend shows English immediately, Thai appears later
    """
    
    name = "hybrid"

    def __init__(
        self,
        fast_provider: ASRProvider,
        quality_provider: Optional[ASRProvider] = None,
        enable_quality: bool = True,
    ) -> None:
        self.fast_provider = fast_provider
        self.quality_provider = quality_provider
        self.enable_quality = enable_quality and quality_provider is not None

    async def setup(self) -> None:
        """Setup both providers."""
        await self.fast_provider.setup()
        if self.enable_quality and self.quality_provider:
            try:
                await self.quality_provider.setup()
            except Exception as e:
                print(f"⚠️  Quality provider setup failed: {e}")
                print("🔄 Continuing with fast provider only")
                self.enable_quality = False

    async def create_stream(self, session_id: str, sample_rate: int) -> ASRStream:
        fast_stream = await self.fast_provider.create_stream(
            session_id, sample_rate
        )
        
        quality_stream = None
        if self.enable_quality and self.quality_provider:
            try:
                quality_stream = await self.quality_provider.create_stream(
                    f"{session_id}_thai", sample_rate
                )
            except Exception as e:
                print(f"⚠️  Quality stream creation failed: {e}")
                self.enable_quality = False
        
        return HybridStream(
            session_id=session_id,
            fast_stream=fast_stream,
            quality_stream=quality_stream,
            use_quality_stream=self.enable_quality,
        )