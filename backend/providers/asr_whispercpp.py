from __future__ import annotations

import asyncio
import io
import os
import tempfile
from pathlib import Path
from typing import AsyncIterator, Optional

from .asr_base import ASRProvider, ASRResult, ASRStream
from ..utils import ensure_dir, to_thread

try:
    from whispercpp import Whisper
except ImportError:  # pragma: no cover - optional dependency
    Whisper = None


class WhisperCppStream(ASRStream):
    def __init__(self, session_id: str, model_path: Path, sample_rate: int) -> None:
        if Whisper is None:
            raise RuntimeError(
                "whispercpp is not installed. Install with `pip install whispercpp` or switch ASR_PROVIDER.`"
            )
        self.session_id = session_id
        self.sample_rate = sample_rate
        self._model_path = model_path
        self._buffer = bytearray()
        self._queue: asyncio.Queue[Optional[ASRResult]] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._last_emitted_end = 0.0
        self._last_partial_text = ""
        self._min_partial_bytes = int(sample_rate * 2 * 1.0)  # 1 second of audio
        self._whisper = Whisper(str(model_path))

    async def push_audio(self, chunk: bytes, timestamp_ms: int) -> None:
        if not chunk:
            return
        self._buffer.extend(chunk)
        if len(self._buffer) >= self._min_partial_bytes:
            await self._run_transcription(is_final=False)

    async def mark_segment_end(self) -> None:
        await self._run_transcription(is_final=True)

    async def finalize(self) -> None:
        await self._run_transcription(is_final=True)
        await self._queue.put(None)

    async def _run_transcription(self, *, is_final: bool) -> None:
        async with self._lock:
            if not self._buffer:
                return
            pcm = bytes(self._buffer)
            if is_final:
                self._buffer.clear()
            elif len(self._buffer) > self._min_partial_bytes * 2:
                # keep only last 4 seconds for partials
                self._buffer[:] = self._buffer[-self._min_partial_bytes * 4 :]
        if not pcm:
            return
        segments = await to_thread(self._transcribe_pcm, pcm)
        for segment in segments:
            start_s, end_s, text = segment
            text = text.strip()
            if not text:
                continue
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
                    confidence=None,
                    raw={"start": start_s, "end": end_s},
                )
            )

    def _transcribe_pcm(self, pcm: bytes) -> list[tuple[float, float, str]]:
        wav_bytes = _pcm16_to_wav(pcm, sample_rate=self.sample_rate)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(wav_bytes)
            tmp.flush()
            tmp_path = tmp.name
        try:
            result = self._whisper.transcribe(tmp_path)
        finally:
            os.unlink(tmp_path)
        segments: list[tuple[float, float, str]] = []
        for seg in result:
            start_s = getattr(seg, "t0", getattr(seg, "start", 0)) / 100 if hasattr(seg, "t0") else getattr(seg, "start", 0)
            end_s = getattr(seg, "t1", getattr(seg, "end", 0)) / 100 if hasattr(seg, "t1") else getattr(seg, "end", start_s)
            text = getattr(seg, "text", "")
            if end_s <= self._last_emitted_end and text.strip():
                continue
            segments.append((start_s, end_s, text))
        return segments

    async def results(self) -> AsyncIterator[ASRResult]:
        while True:
            item = await self._queue.get()
            if item is None:
                break
            yield item


class WhisperCppASRProvider(ASRProvider):
    name = "whispercpp"

    def __init__(self, model_path: Path) -> None:
        self.model_path = model_path
        self._validated = False

    async def setup(self) -> None:
        ensure_dir(self.model_path.parent)
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Whisper.cpp model not found at {self.model_path}. Run scripts/download_models.py first."
            )
        if Whisper is None:
            raise RuntimeError("whispercpp package not installed. Install with `pip install whispercpp`." )
        self._validated = True

    async def create_stream(self, session_id: str, sample_rate: int) -> ASRStream:
        if not self._validated:
            raise RuntimeError("WhisperCppASRProvider.setup() must be awaited before use.")
        return WhisperCppStream(session_id=session_id, model_path=self.model_path, sample_rate=sample_rate)


def _pcm16_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    with io.BytesIO() as buffer:
        import wave

        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm)
        buffer.seek(0)
        return buffer.read()


__all__ = ["WhisperCppASRProvider"]
