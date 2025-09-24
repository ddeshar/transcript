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

# Followers hub: for each transcription session ID, keep a set of queues to broadcast
# real-time messages to follower WebSocket connections (e.g., teleprompter clients).
SESSION_FOLLOWERS: dict[str, set[asyncio.Queue[Optional[dict]]]] = {}


class Settings(BaseSettings):
    asr_provider: str = Field(default="mock", alias="ASR_PROVIDER")
    mt_provider: str = Field(default="mock", alias="MT_PROVIDER")
    cors_origins: str = Field(default="http://localhost:8000", alias="CORS_ORIGINS")
    audio_sample_rate: int = Field(default=16000, alias="AUDIO_SAMPLE_RATE")
    min_silence_ms: int = Field(default=600, alias="MIN_SILENCE_MS")
    status_broadcast_interval_ms: int = Field(default=1000, alias="STATUS_INTERVAL_MS")
    thai_politeness_gender: str = Field(default="female", alias="THAI_POLITENESS_GENDER")

    class Config:
        case_sensitive = False
        env_file = ".env"
        extra = "ignore"


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


async def reload_providers() -> None:
    """Dynamically reload ASR and MT providers with new settings."""
    global ASR_PROVIDER, MT_PROVIDER
    
    # Reload settings from environment
    new_settings = Settings()
    
    print(f"🔄 Reloading providers: ASR={new_settings.asr_provider}, MT={new_settings.mt_provider}")
    
    # Create new providers
    new_asr = create_asr_provider(
        new_settings.asr_provider,
        base_dir=BASE_DIR,
        settings=os.environ,
    )
    new_mt = create_mt_provider(
        new_settings.mt_provider,
        base_dir=BASE_DIR, 
        settings=os.environ,
    )
    
    # Setup new providers
    await new_asr.setup()
    await new_mt.setup()
    
    # Replace global providers
    ASR_PROVIDER = new_asr
    MT_PROVIDER = new_mt
    
    print(f"✅ Providers reloaded successfully")


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


@app.get("/settings")
async def settings_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "settings.html")


@app.get("/favicon.ico")
async def favicon() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "favicon.ico")


@app.get("/api/settings")
async def get_settings() -> JSONResponse:
    """Get current system settings and available providers."""
    
    # Check which providers are actually available based on dependencies
    available_asr_providers = ["mock"]  # Mock is always available
    # Always available providers
    available_mt_providers = ["mock", "simple_thai", "simple"]
    
    # Check ASR providers
    vosk_model_path = os.environ.get(
        "VOSK_MODEL_DIR", str(BASE_DIR / "models" / "vosk")
    )
    if Path(vosk_model_path).exists() and any(Path(vosk_model_path).glob("*")):
        available_asr_providers.append("vosk")
    
    if os.environ.get("OPENAI_API_KEY"):
        available_asr_providers.extend(["whisper_api", "openai", "whisper_gpt", "hybrid"])
    
    # Check for whisper.cpp model
    whisper_cpp_path = BASE_DIR / "models" / "whisper.cpp"
    if whisper_cpp_path.exists() and any(whisper_cpp_path.glob("*.bin")):
        available_asr_providers.append("whispercpp")

    # Check for faster-whisper (always available if installed)
    try:
        import faster_whisper  # noqa
        available_asr_providers.append("faster_whisper")
    except ImportError:
        pass
    
    # Check for official OpenAI Whisper (local, no API key needed)
    try:
        import whisper  # noqa
        available_asr_providers.append("whisper_local")
    except ImportError:
        pass
    
    # Check MT providers
    marian_model_path = os.environ.get(
        "MARIAN_MODEL_DIR", str(BASE_DIR / "models" / "marian")
    )
    if (Path(marian_model_path).exists() and
            any(Path(marian_model_path).glob("*"))):
        available_mt_providers.extend(["marian", "opus"])
    
    ct2_model_path = os.environ.get(
        "CT2_MODEL_DIR",
        str(BASE_DIR / "models" / "ctranslate2" / "en-th")
    )
    if Path(ct2_model_path).exists() and any(Path(ct2_model_path).glob("*")):
        available_mt_providers.extend(["ctranslate2", "ct2"])
    
    # Check cloud providers
    if (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or
            os.environ.get("GCP_PROJECT")):
        available_mt_providers.extend(["gtranslate", "google"])
    
    if (os.environ.get("AWS_ACCESS_KEY_ID") and
            os.environ.get("AWS_SECRET_ACCESS_KEY")):
        available_mt_providers.extend(["awstranslate", "aws"])
    
    if os.environ.get("OPENAI_API_KEY"):
        available_mt_providers.extend(["openai_gpt", "gpt", "openai"])
    
    # Get model paths and statuses
    vosk_model_path = os.environ.get(
        "VOSK_MODEL_DIR", str(BASE_DIR / "models" / "vosk")
    )
    marian_model_path = os.environ.get(
        "MARIAN_MODEL_DIR", str(BASE_DIR / "models" / "marian")
    )
    ct2_model_path = os.environ.get(
        "CT2_MODEL_DIR", str(BASE_DIR / "models" / "ctranslate2" / "en-th")
    )
    
    return JSONResponse({
        "current": {
            "asr_provider": ASR_PROVIDER.name,
            "mt_provider": MT_PROVIDER.name,
            "audio_sample_rate": settings.audio_sample_rate,
            "min_silence_ms": settings.min_silence_ms,
            "status_interval_ms": settings.status_broadcast_interval_ms,
            "cors_origins": settings.cors_origins,
        },
        "available": {
            "asr_providers": available_asr_providers,
            "mt_providers": available_mt_providers,
        },
        "models": {
            "vosk": {
                "path": vosk_model_path,
                "exists": Path(vosk_model_path).exists(),
            },
            "marian": {
                "path": marian_model_path,
                "exists": Path(marian_model_path).exists(),
            },
            "ctranslate2": {
                "path": ct2_model_path,
                "exists": Path(ct2_model_path).exists(),
            },
        },
        "languages": {
            "source": "en",  # Currently hardcoded to English
            "target": "th",  # Currently hardcoded to Thai
            "available_targets": ["th"],  # Could be expanded
        },
        "cloud_providers": {
            "openai_configured": bool(os.environ.get("OPENAI_API_KEY")),
            "gcp_configured": bool(
                os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or
                os.environ.get("GCP_PROJECT")
            ),
            "aws_configured": bool(
                os.environ.get("AWS_ACCESS_KEY_ID") and
                os.environ.get("AWS_SECRET_ACCESS_KEY")
            ),
        },
        "timestamp": utc_timestamp_ms(),
    })


@app.post("/api/settings")
async def update_settings(new_settings: dict) -> JSONResponse:
    """Update system settings (note: requires restart to take effect)."""
    # This would typically require a restart to take effect
    # For now, just return what would be changed
    changes = {}
    
    if "asr_provider" in new_settings:
        changes["asr_provider"] = {
            "old": ASR_PROVIDER.name,
            "new": new_settings["asr_provider"]
        }
    
    if "mt_provider" in new_settings:
        changes["mt_provider"] = {
            "old": MT_PROVIDER.name,
            "new": new_settings["mt_provider"]
        }
    
    return JSONResponse({
        "message": "Settings update received. Restart required.",
        "changes": changes,
        "restart_required": True,
    })


@app.get("/api/env")
async def get_env_vars() -> JSONResponse:
    """Get current environment variables for editing."""
    # Only return safe-to-edit variables
    editable_vars = {
        "ASR_PROVIDER": os.environ.get("ASR_PROVIDER", ""),
        "MT_PROVIDER": os.environ.get("MT_PROVIDER", ""),
        "AUDIO_SAMPLE_RATE": os.environ.get("AUDIO_SAMPLE_RATE", ""),
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),
        "OPENAI_WHISPER_MODEL": os.environ.get("OPENAI_WHISPER_MODEL", ""),
        "FASTER_WHISPER_MODEL": os.environ.get("FASTER_WHISPER_MODEL", ""),
        "FASTER_WHISPER_DEVICE": os.environ.get("FASTER_WHISPER_DEVICE", ""),
        "FASTER_WHISPER_COMPUTE_TYPE": os.environ.get(
            "FASTER_WHISPER_COMPUTE_TYPE", ""
        ),
        "FASTER_WHISPER_LANGUAGE": os.environ.get(
            "FASTER_WHISPER_LANGUAGE", ""
        ),
        "FASTER_WHISPER_BEAM_SIZE": os.environ.get(
            "FASTER_WHISPER_BEAM_SIZE", ""
        ),
        "FASTER_WHISPER_CHUNK_DURATION": os.environ.get(
            "FASTER_WHISPER_CHUNK_DURATION", ""
        ),
        "GCP_PROJECT": os.environ.get("GCP_PROJECT", ""),
        "GOOGLE_APPLICATION_CREDENTIALS": os.environ.get(
            "GOOGLE_APPLICATION_CREDENTIALS", ""
        ),
        "AWS_REGION": os.environ.get("AWS_REGION", ""),
        "AWS_ACCESS_KEY_ID": os.environ.get("AWS_ACCESS_KEY_ID", ""),
        "AWS_SECRET_ACCESS_KEY": os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
        "HUGGINGFACE_TOKEN": os.environ.get("HUGGINGFACE_TOKEN", ""),
        "MIN_SILENCE_MS": os.environ.get("MIN_SILENCE_MS", ""),
        "STATUS_INTERVAL_MS": os.environ.get("STATUS_INTERVAL_MS", ""),
        "THAI_POLITENESS_GENDER": os.environ.get("THAI_POLITENESS_GENDER", ""),
    }
    
    return JSONResponse({
        "variables": editable_vars,
        "timestamp": utc_timestamp_ms(),
    })


@app.post("/api/env")
async def update_env_vars(env_update: dict) -> JSONResponse:
    """Update environment variables in .env file."""
    try:
        # Determine which .env file to update
        # (prefer .env.docker for Docker environments)
        env_file_path = BASE_DIR / ".env.docker"
        if not env_file_path.exists():
            env_file_path = BASE_DIR / ".env"
        
        # Read current .env file
        env_lines = []
        if env_file_path.exists():
            with open(env_file_path, 'r', encoding='utf-8') as f:
                env_lines = f.readlines()
        
        # Track changes
        changes = {}
        updated_vars = set()
        
        # Process each variable in the update
        for key, value in env_update.get("variables", {}).items():
            if not key:  # Skip empty keys
                continue
                
            # Clean the value
            clean_value = str(value).strip()
            old_value = os.environ.get(key, "")
            
            if clean_value != old_value:
                changes[key] = {"old": old_value, "new": clean_value}
            
            # Update environment variable immediately for this session
            os.environ[key] = clean_value
            updated_vars.add(key)
            
            # Update or add line in .env file
            found = False
            for i, line in enumerate(env_lines):
                if line.strip() and not line.strip().startswith('#'):
                    if '=' in line:
                        env_key = line.split('=', 1)[0].strip()
                        if env_key == key:
                            env_lines[i] = f"{key}={clean_value}\n"
                            found = True
                            break
            
            # If not found, add at the end
            if not found:
                if env_lines and not env_lines[-1].endswith('\n'):
                    env_lines.append('\n')
                env_lines.append(f"{key}={clean_value}\n")
        
        # Write updated .env file
        with open(env_file_path, 'w', encoding='utf-8') as f:
            f.writelines(env_lines)
        
        # Dynamically reinitialize providers if ASR or MT changed
        provider_reloaded = False
        if "ASR_PROVIDER" in changes or "MT_PROVIDER" in changes:
            try:
                await reload_providers()
                provider_reloaded = True
            except Exception as e:
                print(f"⚠️ Failed to reload providers: {e}")

        return JSONResponse({
            "message": f"Updated {len(changes)} environment variables " +
                       f"in {env_file_path.name}",
            "changes": changes,
            "file_updated": str(env_file_path),
            "providers_reloaded": provider_reloaded,
            "restart_recommended": not provider_reloaded and len(changes) > 0,
        })
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": "Failed to update environment variables",
                "details": str(e)
            }
        )


@app.post("/api/restart")
async def restart_container() -> JSONResponse:
    """Trigger a container restart (for Docker environments)."""
    def delayed_exit():
        import time
        import os
        time.sleep(1)
        os._exit(0)
    
    # Schedule delayed exit to allow response to be sent
    import threading
    threading.Timer(1.0, delayed_exit).start()
    
    return JSONResponse({
        "message": "Container restart initiated",
        "timestamp": utc_timestamp_ms(),
    })


@app.get("/teleprompter")
async def teleprompter() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "teleprompter.html")


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

    vad = VoiceActivityDetector(
        sample_rate=state.sample_rate,
        aggressiveness=3,  # Most aggressive noise filtering (0-3)
        padding_duration_ms=200  # Shorter padding to reduce false speech detection
    )
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
                # Broadcast to any registered followers for this session
                followers = SESSION_FOLLOWERS.get(sess_id)
                if followers:
                    for q in list(followers):
                        with contextlib.suppress(Exception):
                            await q.put(message)
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
                        vad = VoiceActivityDetector(
                            sample_rate=state.sample_rate,
                            aggressiveness=3,  # Most aggressive filtering
                            padding_duration_ms=200
                        )
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
        # Cleanup followers (close their queues)
        if sess_id in SESSION_FOLLOWERS:
            for q in list(SESSION_FOLLOWERS[sess_id]):
                with contextlib.suppress(Exception):
                    await q.put(None)
            SESSION_FOLLOWERS.pop(sess_id, None)
        with contextlib.suppress(Exception):
            await sender_task


__all__ = ["app"]


async def _follower_sender(ws: WebSocket, queue: "asyncio.Queue[Optional[dict]]") -> None:
    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            await ws.send_json(item)
    finally:
        with contextlib.suppress(Exception):
            await ws.close()


@app.websocket("/ws/follow/{sess_id}")
async def ws_follow(websocket: WebSocket, sess_id: str) -> None:
    await websocket.accept()
    q: asyncio.Queue[Optional[dict]] = asyncio.Queue()
    # Register follower
    SESSION_FOLLOWERS.setdefault(sess_id, set()).add(q)
    sender = asyncio.create_task(_follower_sender(websocket, q))
    try:
        # Followers are receive-only; keep connection open until disconnect
        while True:
            msg = await websocket.receive()
            if "type" in msg and msg["type"] == "websocket.disconnect":
                break
    finally:
        # Unregister follower
        with contextlib.suppress(KeyError):
            SESSION_FOLLOWERS.get(sess_id, set()).discard(q)
        with contextlib.suppress(Exception):
            await q.put(None)
        with contextlib.suppress(Exception):
            await sender
