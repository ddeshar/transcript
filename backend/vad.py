from __future__ import annotations

import collections
from dataclasses import dataclass
from typing import Deque, Generator, Iterable, List

import webrtcvad


@dataclass
class VADEvent:
    type: str  # "speech" or "silence"
    timestamp_ms: int


class VoiceActivityDetector:
    """Simple WebRTC VAD wrapper that emits speech start/end events."""

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        padding_duration_ms: int = 1500,  # 1.5s to prevent brief pause stops
        aggressiveness: int = 1,  # Less aggressive silence detection
    ) -> None:
        if frame_duration_ms not in (10, 20, 30):
            raise ValueError("frame_duration_ms must be 10, 20, or 30")
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.frame_bytes = int(sample_rate * frame_duration_ms / 1000) * 2
        self.padding_frames = padding_duration_ms // frame_duration_ms
        self.vad = webrtcvad.Vad(aggressiveness)
        self.ring_buffer: Deque[tuple[bytes, bool]] = collections.deque(maxlen=self.padding_frames)
        self.in_speech = False
        self._processed_samples = 0
        self._leftover = b""

    def _frame_generator(self, audio: bytes) -> Generator[bytes, None, None]:
        data = self._leftover + audio
        for idx in range(0, len(data) - (len(data) % self.frame_bytes), self.frame_bytes):
            yield data[idx: idx + self.frame_bytes]
        remainder = len(data) % self.frame_bytes
        self._leftover = data[-remainder:] if remainder else b""

    def process(self, audio: bytes) -> List[VADEvent]:
        events: List[VADEvent] = []
        for frame in self._frame_generator(audio):
            try:
                # Check frame size is correct for VAD
                if len(frame) != self.frame_bytes:
                    continue
                is_speech = self.vad.is_speech(frame, self.sample_rate)
            except (ValueError, RuntimeError):
                # If VAD fails, assume it's speech to keep processing
                is_speech = True
                
            self._processed_samples += self.frame_bytes // 2
            timestamp_ms = int(
                self._processed_samples / self.sample_rate * 1000
            )
            self.ring_buffer.append((frame, is_speech))
            voiced_count = sum(1 for _, voiced in self.ring_buffer if voiced)
            threshold = 0.9 * len(self.ring_buffer)
            if not self.in_speech and voiced_count > threshold:
                self.in_speech = True
                events.append(
                    VADEvent(type="speech", timestamp_ms=timestamp_ms)
                )
            elif self.in_speech and voiced_count < 0.2 * len(self.ring_buffer):
                self.in_speech = False
                events.append(
                    VADEvent(type="silence", timestamp_ms=timestamp_ms)
                )
        return events


__all__ = ["VoiceActivityDetector", "VADEvent"]
