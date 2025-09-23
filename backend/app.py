from __future__ import annotations

import asyncio
import json
import os
import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from pydantic_settings import BaseSettings

from .providers import create_asr_provider, create_mt_provider
from .providers.asr_base import ASRResult, ASRStream
from .providers.mt_base import MTProvider
from .utils import SessionTranscript, format_timestamp, jsonify_log, session_id, utc_timestamp_ms
from .vad import VoiceActivityDetector

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


class Settings(BaseSettings):
    asr_provider: str = Field(default="vosk", alias="ASR_PROVIDER")
    mt_provider: str = Field(default="marian", alias="MT_PROVIDER")
    cors_origins: str = Field(default="http://localhost:8000", alias="CORS_ORIGINS")
    audio_sample_rate: int = Field(default=16000, alias="AUDIO_SAMPLE_RATE")
    min_silence_ms: int = Field(default=600, alias="MIN_SILENCE_MS")
    status_broadcast_interval_ms: int = Field(default=1000, alias="STATUS_INTERVAL_MS")

    class Config:
        case_sensitive = False


def _parse_origins(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


settings = Settings()
app = FastAPI(title="Realtime English to Thai Subtitles", version="1.0.0")

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_parse_origins(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


ASR_PROVIDER = create_asr_provider(
    settings.asr_provider,
    base_dir=BASE_DIR,
    settings=os.environ,
)
MT_PROVIDER: MTProvider = create_mt_provider(
    settings.mt_provider,
    base_dir=BASE_DIR,
    settings=os.environ,
)


@app.on_event("startup")
async def startup_event() -> None:
    await ASR_PROVIDER.setup()
    await MT_PROVIDER.setup()


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "asr_provider": ASR_PROVIDER.name,
        "mt_provider": MT_PROVIDER.name,
        "timestamp": utc_timestamp_ms(),
    })


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@dataclass
class ConnectionState:
    websocket: WebSocket
    session_id: str
    sample_rate: int
    transcript: SessionTranscript
    last_partial: str = ""
    speech_active: bool = False
    last_status: str = "idle"

    def reset_partial(self) -> None:
        self.last_partial = ""


async def websocket_sender(websocket: WebSocket, queue: "asyncio.Queue[Optional[dict]]") -> None:
    try:
        while True:
            payload = await queue.get()
            if payload is None:
                break
            await websocket.send_json(payload)
    finally:
        await websocket.close()


@app.websocket("/ws/transcribe")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    sess_id = session_id()
    state = ConnectionState(
        websocket=websocket,
        session_id=sess_id,
        sample_rate=settings.audio_sample_rate,
        transcript=SessionTranscript(),
    )
    outgoing: asyncio.Queue[Optional[dict]] = asyncio.Queue()

    async def send(payload: dict) -> None:
        await outgoing.put(payload)

    sender_task = asyncio.create_task(websocket_sender(websocket, outgoing))
    await send({"type": "session", "sessionId": sess_id})
    await send({"type": "status", "status": "ready"})

    vad = VoiceActivityDetector(sample_rate=state.sample_rate)
    asr_stream: Optional[ASRStream] = None

    async def forward_results(stream: ASRStream) -> None:
        nonlocal state
        try:
            async for result in stream.results():
                english_text = result.text.strip()
                if not english_text:
                    continue
                if not result.is_final and english_text == state.last_partial:
                    continue
                if result.is_final:
                    state.reset_partial()
                else:
                    state.last_partial = english_text
                await send({"type": "status", "status": "translating"})
                translation = await MT_PROVIDER.translate(english_text, is_final=result.is_final)
                message = {
                    "type": "partial" if not result.is_final else "final",
                    "sessionId": sess_id,
                    "segmentId": result.segment_id or f"{sess_id}-{result.end_ms}",
                    "english": english_text,
                    "thai": translation.text,
                    "timestamp_ms": result.end_ms or utc_timestamp_ms(),
                    "provider": {
                        "asr": ASR_PROVIDER.name,
                        "mt": translation.provider,
                    },
                }
                await send(message)
                if result.is_final:
                    state.transcript.add_segment(message)
                    await send({"type": "status", "status": "listening"})
        except asyncio.CancelledError:
            pass

    results_task: Optional[asyncio.Task] = None

    try:
        asr_stream = await ASR_PROVIDER.create_stream(sess_id, state.sample_rate)
        results_task = asyncio.create_task(forward_results(asr_stream))
        await send({"type": "status", "status": "listening"})
        while True:
            message = await websocket.receive()
            if "type" in message and message["type"] == "websocket.disconnect":
                break
            if "text" in message and message["text"]:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue
                kind = data.get("type")
                if kind == "config":
                    sr = data.get("sampleRate")
                    if isinstance(sr, int) and sr > 0:
                        state.sample_rate = sr
                        vad = VoiceActivityDetector(sample_rate=state.sample_rate)
                        if asr_stream:
                            # recreate stream with new rate
                            await asr_stream.finalize()
                            if results_task:
                                results_task.cancel()
                            asr_stream = await ASR_PROVIDER.create_stream(sess_id, state.sample_rate)
                            results_task = asyncio.create_task(forward_results(asr_stream))
                elif kind == "control":
                    action = data.get("action")
                    if action == "clear":
                        state.transcript.clear()
                        await send({"type": "cleared"})
                    elif action == "stop":
                        if asr_stream:
                            await asr_stream.finalize()
                    elif action == "save_request":
                        payload = state.transcript.to_serializable()
                        await send({"type": "transcript", **payload})
                continue
            chunk = message.get("bytes")
            if chunk is None:
                continue
            if asr_stream is None:
                continue
            await asr_stream.push_audio(chunk, utc_timestamp_ms())
            events = vad.process(chunk)
            for evt in events:
                if evt.type == "speech":
                    silence_deadline = None
                    if not state.speech_active:
                        state.speech_active = True
                        await send({"type": "status", "status": "transcribing"})
                elif evt.type == "silence":
                    if state.speech_active:
                        state.speech_active = False
                        await send({"type": "status", "status": "translating"})
                        await asr_stream.mark_segment_end()
    except WebSocketDisconnect:
        jsonify_log("ws_disconnect", session_id=sess_id)
    finally:
        if results_task:
            results_task.cancel()
            with contextlib.suppress(Exception):
                await results_task
        if asr_stream:
            with contextlib.suppress(Exception):
                await asr_stream.finalize()
        await outgoing.put(None)
        with contextlib.suppress(Exception):
            await sender_task


__all__ = ["app"]
