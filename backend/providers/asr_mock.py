"""Mock ASR provider for testing without models."""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from .asr_base import ASRProvider, ASRResult, ASRStream


class MockASRStream(ASRStream):
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._queue: asyncio.Queue[ASRResult | None] = asyncio.Queue()
        self._counter = 0

    async def push_audio(self, chunk: bytes, timestamp_ms: int) -> None:
        # Mock transcription - just echo a counter
        self._counter += 1
        if self._counter % 10 == 0:  # Every 10th chunk
            result = ASRResult(
                session_id=self.session_id,
                text=f"Mock transcription {self._counter // 10}",
                is_final=True,
                start_ms=timestamp_ms - 1000,
                end_ms=timestamp_ms,
                confidence=0.95
            )
            await self._queue.put(result)

    async def mark_segment_end(self) -> None:
        pass

    async def finalize(self) -> None:
        await self._queue.put(None)

    async def results(self) -> AsyncIterator[ASRResult]:
        while True:
            result = await self._queue.get()
            if result is None:
                break
            yield result


class MockASRProvider(ASRProvider):
    name = "mock"

    async def setup(self) -> None:
        pass

    async def create_stream(self, session_id: str, sample_rate: int) -> ASRStream:
        return MockASRStream(session_id)