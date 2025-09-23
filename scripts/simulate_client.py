#!/usr/bin/env python3
"""Send sample audio to the websocket backend for integration testing."""

from __future__ import annotations

import argparse
import asyncio
import json
import wave
from pathlib import Path

import websockets

DEFAULT_WS_URL = "ws://localhost:8000/ws/transcribe"
DEFAULT_AUDIO = Path(__file__).resolve().parent.parent / "sample_audio" / "en_sample.wav"


async def stream_audio(ws_url: str, audio_path: Path, chunk_ms: int = 200) -> None:
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    async with websockets.connect(ws_url) as ws:
        async def receiver():
            try:
                async for message in ws:
                    data = json.loads(message)
                    kind = data.get("type")
                    if kind in {"partial", "final"}:
                        print(f"[{kind.upper()}] EN: {data.get('english')} | TH: {data.get('thai')}")
                    elif kind == "status":
                        print(f"[STATUS] {data.get('status')}")
            except asyncio.CancelledError:
                pass

        recv_task = asyncio.create_task(receiver())
        with wave.open(str(audio_path), "rb") as wav:
            sample_rate = wav.getframerate()
            sample_width = wav.getsampwidth()
            channels = wav.getnchannels()
            if sample_width != 2 or channels != 1:
                raise ValueError("Audio file must be mono 16-bit PCM")
            await ws.send(json.dumps({"type": "config", "sampleRate": sample_rate}))
            frame_bytes = int(sample_rate * sample_width * chunk_ms / 1000)
            print("Streaming audio…")
            chunk = wav.readframes(frame_bytes // sample_width)
            while chunk:
                await ws.send(chunk)
                await asyncio.sleep(chunk_ms / 1000.0)
                chunk = wav.readframes(frame_bytes // sample_width)
        await asyncio.sleep(2)
        recv_task.cancel()
        with contextlib.suppress(Exception):
            await recv_task


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate a websocket client streaming audio")
    parser.add_argument("--url", default=DEFAULT_WS_URL, help="WebSocket endpoint")
    parser.add_argument("--audio", default=str(DEFAULT_AUDIO), help="Path to WAV file")
    parser.add_argument("--chunk-ms", type=int, default=200, help="Chunk duration in milliseconds")
    args = parser.parse_args()
    asyncio.run(stream_audio(args.url, Path(args.audio), chunk_ms=args.chunk_ms))


if __name__ == "__main__":
    import contextlib

    main()
