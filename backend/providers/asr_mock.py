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
        # Mock transcription with realistic test sentences
        self._counter += 1
        
        test_sentences = [
            "Hello and welcome to today's presentation.",
            "We'll be discussing artificial intelligence.",
            "Machine learning is transforming industries.",
            "Natural language processing enables computers to understand.",
            "Deep learning uses neural networks for complex tasks.",
            "Thank you for your attention to this topic.",
            "Let's explore some practical applications.",
            "The future of technology looks very promising."
        ]
        
        if self._counter % 15 == 0:  # Every 15th chunk (~3-4 seconds)
            sentence_index = (self._counter // 15 - 1) % len(test_sentences)
            result = ASRResult(
                session_id=self.session_id,
                text=test_sentences[sentence_index],
                is_final=True,
                start_ms=timestamp_ms - 2000,
                end_ms=timestamp_ms,
                confidence=0.95,
                segment_id=f"mock-{self._counter // 15}"
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

    async def create_stream(
        self, session_id: str, sample_rate: int
    ) -> ASRStream:
        return MockASRStream(session_id)