from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, List, Optional

from .asr_base import ASRProvider, ASRResult, ASRStream
from ..utils import ensure_dir, to_thread


@dataclass
class VoskConfig:
    model_path: Path


class VoskASRStream(ASRStream):
    def __init__(self, session_id: str, recognizer, sample_rate: int) -> None:
        self.session_id = session_id
        self._recognizer = recognizer
        self.sample_rate = sample_rate
        self._queue: asyncio.Queue[Optional[ASRResult]] = asyncio.Queue()
        self._samples_processed = 0
        self._last_partial = ""
        self._lock = asyncio.Lock()

    async def push_audio(self, chunk: bytes, timestamp_ms: int) -> None:
        if not chunk:
            return
        async with self._lock:
            events = await to_thread(self._process_chunk, chunk)
        for event in events:
            await self._queue.put(event)
        self._samples_processed += len(chunk) // 2

    def _process_chunk(self, chunk: bytes) -> List[ASRResult]:
        results: List[ASRResult] = []
        if self._recognizer.AcceptWaveform(chunk):
            data = json.loads(self._recognizer.Result())
            if not data:
                return results
            text = data.get("text", "").strip()
            if text:
                start_ms, end_ms, confidence = _extract_timing(data)
                results.append(
                    ASRResult(
                        session_id=self.session_id,
                        text=text,
                        is_final=True,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        confidence=confidence,
                        raw=data,
                    )
                )
            self._last_partial = ""
        else:
            partial = json.loads(self._recognizer.PartialResult()).get("partial", "").strip()
            if partial and partial != self._last_partial:
                current_ms = int(self._samples_processed / self.sample_rate * 1000)
                results.append(
                    ASRResult(
                        session_id=self.session_id,
                        text=partial,
                        is_final=False,
                        start_ms=max(current_ms - 800, 0),
                        end_ms=current_ms,
                        confidence=None,
                    )
                )
                self._last_partial = partial
        return results

    async def mark_segment_end(self) -> None:
        await self._flush()

    async def finalize(self) -> None:
        await self._flush()
        await self._queue.put(None)

    async def _flush(self) -> None:
        async with self._lock:
            data = await to_thread(self._recognizer.FinalResult)
        if data:
            payload = json.loads(data)
            text = payload.get("text", "").strip()
            if text:
                start_ms, end_ms, confidence = _extract_timing(payload)
                await self._queue.put(
                    ASRResult(
                        session_id=self.session_id,
                        text=text,
                        is_final=True,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        confidence=confidence,
                        raw=payload,
                    )
                )
        self._last_partial = ""

    async def results(self) -> AsyncIterator[ASRResult]:
        while True:
            item = await self._queue.get()
            if item is None:
                break
            yield item


class VoskASRProvider(ASRProvider):
    name = "vosk"

    def __init__(self, model_dir: Path, model_name: str | None = None) -> None:
        self.model_dir = ensure_dir(model_dir)
        self.model_name = model_name
        self._vosk_model = None

    async def setup(self) -> None:
        import vosk

        model_path = self.model_dir if self.model_name is None else self.model_dir / self.model_name
        if not model_path.exists():
            raise FileNotFoundError(
                f"Vosk model not found at {model_path}. Run scripts/download_models.py first."
            )
        self._vosk_model = await to_thread(vosk.Model, str(model_path))

    async def create_stream(self, session_id: str, sample_rate: int) -> ASRStream:
        import vosk

        if self._vosk_model is None:
            raise RuntimeError("VoskASRProvider.setup() must be awaited before use.")
        recognizer = vosk.KaldiRecognizer(self._vosk_model, sample_rate)
        recognizer.SetWords(True)
        return VoskASRStream(session_id=session_id, recognizer=recognizer, sample_rate=sample_rate)


def _extract_timing(payload: dict) -> tuple[int, int, Optional[float]]:
    words = payload.get("result")
    if not words:
        return 0, 0, payload.get("confidence")
    start = words[0].get("start", 0.0)
    end = words[-1].get("end", start)
    confidences = [w.get("conf", 0.0) for w in words if "conf" in w]
    confidence = None
    if confidences:
        confidence = sum(confidences) / max(len(confidences), 1)
    return int(start * 1000), int(end * 1000), confidence


__all__ = ["VoskASRProvider"]
