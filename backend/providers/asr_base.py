from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import AsyncIterator, Optional


@dataclass
class ASRResult:
    session_id: str
    text: str
    is_final: bool
    start_ms: int
    end_ms: int
    confidence: Optional[float] = None
    segment_id: Optional[str] = None
    raw: Optional[dict] = None


class ASRStream(abc.ABC):
    @abc.abstractmethod
    async def push_audio(self, chunk: bytes, timestamp_ms: int) -> None:
        ...

    @abc.abstractmethod
    async def mark_segment_end(self) -> None:
        ...

    @abc.abstractmethod
    async def finalize(self) -> None:
        ...

    @abc.abstractmethod
    async def results(self) -> AsyncIterator[ASRResult]:
        ...


class ASRProvider(abc.ABC):
    name: str

    @abc.abstractmethod
    async def setup(self) -> None:
        ...

    @abc.abstractmethod
    async def create_stream(self, session_id: str, sample_rate: int) -> ASRStream:
        ...


__all__ = ["ASRResult", "ASRStream", "ASRProvider"]
