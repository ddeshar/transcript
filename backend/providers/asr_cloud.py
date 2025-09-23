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
    def __init__(self, session_id: str, client: AsyncOpenAI, model: str, sample_rate: int) -> None:
        self.session_id = session_id
        self.client = client
        self.model = model
        self.sample_rate = sample_rate
        self._buffer = bytearray()
        self._queue: asyncio.Queue[Optional[ASRResult]] = asyncio.Queue()
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
        response = await self.client.audio.transcriptions.create(
            model=self.model,
            file=io.BytesIO(wav_bytes),
            language="en",
            response_format="json",
        )
        text = (response.get("text") if isinstance(response, dict) else getattr(response, "text", "")) or ""
        text = text.strip()
        if not text:
            return
        self._seq += 1
        await self._queue.put(
            ASRResult(
                session_id=self.session_id,
                text=text,
                is_final=is_final,
                start_ms=0,
                end_ms=0,
                confidence=None,
                segment_id=f"openai-{self._seq}",
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

    def __init__(self, api_key: Optional[str] = None, model: str = "whisper-1") -> None:
        self.api_key = api_key
        self.model = model
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
        return WhisperAPIStream(session_id=session_id, client=self._client, model=self.model, sample_rate=sample_rate)


__all__ = ["WhisperCloudASRProvider"]
