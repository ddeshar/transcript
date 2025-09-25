from __future__ import annotations

import asyncio
import contextlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from uuid import uuid4

from fastapi import (
    FastAPI, 
    WebSocket, 
    WebSocketDisconnect, 
    HTTPException, 
    Depends
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from .database import init_database, get_db
from .db_service import DatabaseService, AsyncDatabaseService
from .models import ROOM_PARTICIPANTS
from .providers import create_asr_provider, create_mt_provider
from .providers.asr_base import ASRStream
from .providers.mt_base import MTProvider
from .utils import (
    SessionTranscript,
    get_logger,
    jsonify_log,
    session_id,
    utc_timestamp_ms,
)
from .vad import VoiceActivityDetector

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

# Followers hub maps each transcription session ID to follower queues that
# should receive real-time messages (e.g., teleprompter clients).
SESSION_FOLLOWERS: Dict[str, set] = {}

# Active sessions to support session following and room management
ACTIVE_SESSIONS: Dict[str, ConnectionState] = {}


class Settings(BaseSettings):
    asr_provider: str = Field(default="mock", alias="ASR_PROVIDER")
    mt_provider: str = Field(default="mock", alias="MT_PROVIDER")
    cors_origins: str = Field(
        default="http://localhost:8000",
        alias="CORS_ORIGINS",
    )
    audio_sample_rate: int = Field(default=16000, alias="AUDIO_SAMPLE_RATE")
    min_silence_ms: int = Field(default=600, alias="MIN_SILENCE_MS")
    status_broadcast_interval_ms: int = Field(
        default=1000,
        alias="STATUS_INTERVAL_MS",
    )
    thai_politeness_gender: str = Field(
        default="female",
        alias="THAI_POLITENESS_GENDER",
    )

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
    app.mount(
        "/static",
        StaticFiles(directory=str(FRONTEND_DIR)),
        name="static",
    )


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

# Initialize database on startup
init_database()
get_logger().info("Database initialized successfully")


async def reload_providers() -> None:
    """Dynamically reload ASR and MT providers with new settings."""
    global ASR_PROVIDER, MT_PROVIDER
    
    # Reload settings from environment
    new_settings = Settings()
    
    print(
        "🔄 Reloading providers: ASR=",
        new_settings.asr_provider,
        ", MT=",
        new_settings.mt_provider,
        sep="",
    )
    
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
    
    print("✅ Providers reloaded successfully")


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
    available_mt_providers = ["mock", "simple_thai"]
    
    # Check ASR providers
    vosk_model_path = os.environ.get(
        "VOSK_MODEL_DIR", str(BASE_DIR / "models" / "vosk")
    )
    if Path(vosk_model_path).exists() and any(Path(vosk_model_path).glob("*")):
        available_asr_providers.append("vosk")
    
    if os.environ.get("OPENAI_API_KEY"):
        available_asr_providers.extend(
            ["whisper_api", "whisper_gpt", "hybrid"]
        )
    
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
        available_mt_providers.append("marian")
    
    ct2_model_path = os.environ.get(
        "CT2_MODEL_DIR",
        str(BASE_DIR / "models" / "ctranslate2" / "en-th")
    )
    if Path(ct2_model_path).exists() and any(Path(ct2_model_path).glob("*")):
        available_mt_providers.append("ctranslate2")
    
    # Check cloud providers
    if (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or
            os.environ.get("GCP_PROJECT")):
        available_mt_providers.append("gtranslate")
    
    if (os.environ.get("AWS_ACCESS_KEY_ID") and
            os.environ.get("AWS_SECRET_ACCESS_KEY")):
        available_mt_providers.append("awstranslate")
    
    if os.environ.get("OPENAI_API_KEY"):
        available_mt_providers.append("openai_gpt")
    
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
        "dependencies": {
            "asr_mt_compatibility": {
                # ASR providers that do translation internally (no MT needed)
                "whisper_gpt": {
                    "requires_mt": False,
                    "recommended_mt": "simple_thai",  # Pass-through
                    "description": "Whisper + GPT with built-in Thai translation"
                },
                # Standard ASR providers (require separate MT)
                "whisper_api": {
                    "requires_mt": True,
                    "recommended_mt": "openai_gpt",
                    "compatible_mt": ["openai_gpt", "awstranslate", "simple_thai"],
                    "description": "OpenAI Whisper API (English only)"
                },
                "vosk": {
                    "requires_mt": True,
                    "recommended_mt": "openai_gpt",
                    "compatible_mt": ["openai_gpt", "awstranslate", "marian", "ctranslate2", "simple_thai"],
                    "description": "Local Vosk ASR (English only)"
                },
                "faster_whisper": {
                    "requires_mt": True,
                    "recommended_mt": "openai_gpt",
                    "compatible_mt": ["openai_gpt", "awstranslate", "marian", "ctranslate2", "simple_thai"],
                    "description": "Fast local Whisper (English only)"
                },
                "whisper_local": {
                    "requires_mt": True,
                    "recommended_mt": "openai_gpt", 
                    "compatible_mt": ["openai_gpt", "awstranslate", "marian", "ctranslate2", "simple_thai"],
                    "description": "Local OpenAI Whisper (English only)"
                },
                "whispercpp": {
                    "requires_mt": True,
                    "recommended_mt": "marian",
                    "compatible_mt": ["openai_gpt", "awstranslate", "marian", "ctranslate2", "simple_thai"],
                    "description": "Whisper.cpp (fast, local)"
                },
                "hybrid": {
                    "requires_mt": False,
                    "recommended_mt": "simple_thai",
                    "description": "Fast local + quality cloud hybrid"
                },
                "mock": {
                    "requires_mt": True,
                    "recommended_mt": "mock",
                    "compatible_mt": ["mock"],
                    "description": "Testing provider"
                }
            },
            "provider_categories": {
                "cloud_asr": ["whisper_api", "whisper_gpt"],
                "local_asr": ["vosk", "faster_whisper", "whisper_local", "whispercpp"],  
                "hybrid_asr": ["hybrid"],
                "cloud_mt": ["openai_gpt", "awstranslate"],
                "local_mt": ["marian", "ctranslate2"],
                "passthrough_mt": ["simple_thai"],
                "testing": ["mock"]
            }
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


# === SEMINAR ROOM API ENDPOINTS ===

class CreateRoomRequest(BaseModel):
    title: str


class RoomResponse(BaseModel):
    room_id: str
    title: str
    is_live: bool
    participant_url: str
    presenter_url: str
    created_at: str
    started_at: str | None = None
    ended_at: str | None = None
    participant_count: int = 0
    duration_ms: int | None = None


@app.post("/api/rooms", response_model=RoomResponse)
async def create_room(request: CreateRoomRequest) -> RoomResponse:
    """Create a new seminar room."""
    # Create room in database
    room = await AsyncDatabaseService.create_room(
        title=request.title,
        description=getattr(request, 'description', None)
    )
    
    base_url = "http://localhost:8000"  # In production, get from request
    return RoomResponse(
        room_id=room.room_id,
        title=room.title,
        is_live=room.is_live,
        participant_url=room.get_room_url(base_url),
        presenter_url=room.get_presenter_url(base_url),
        created_at=room.created_at.isoformat(),
        started_at=room.started_at.isoformat() if room.started_at else None,
        ended_at=room.ended_at.isoformat() if room.ended_at else None,
        participant_count=len(ROOM_PARTICIPANTS.get(room.room_id, set())),
        duration_ms=room.total_duration_ms
    )


@app.get("/api/rooms", response_model=list[RoomResponse])
async def list_rooms() -> list[RoomResponse]:
    """List all seminar rooms."""
    base_url = "http://localhost:8000"  # In production, get from request
    rooms_data = await AsyncDatabaseService.list_rooms()
    rooms = []
    
    for room in rooms_data:
        rooms.append(RoomResponse(
            room_id=room.room_id,
            title=room.title,
            is_live=room.is_live,
            participant_url=room.get_room_url(base_url),
            presenter_url=room.get_presenter_url(base_url),
            created_at=room.created_at.isoformat(),
            started_at=(room.started_at.isoformat()
                        if room.started_at else None),
            ended_at=room.ended_at.isoformat() if room.ended_at else None,
            participant_count=len(ROOM_PARTICIPANTS.get(room.room_id, set())),
            duration_ms=room.total_duration_ms
        ))
    
    return sorted(rooms, key=lambda r: r.created_at, reverse=True)


@app.get("/api/rooms/{room_id}", response_model=RoomResponse)
async def get_room(room_id: str) -> RoomResponse:
    """Get details of a specific room."""
    room = await AsyncDatabaseService.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    base_url = "http://localhost:8000"  # In production, get from request
    
    return RoomResponse(
        room_id=room.room_id,
        title=room.title,
        is_live=room.is_live,
        participant_url=room.get_room_url(base_url),
        presenter_url=room.get_presenter_url(base_url),
        created_at=room.created_at.isoformat(),
        started_at=(room.started_at.isoformat()
                    if room.started_at else None),
        ended_at=room.ended_at.isoformat() if room.ended_at else None,
        participant_count=len(ROOM_PARTICIPANTS.get(room.room_id, set())),
        duration_ms=room.total_duration_ms
    )


@app.get("/room/{room_id}")
async def room_page(room_id: str) -> FileResponse:
    """Serve the participant interface for a room."""
    room = await AsyncDatabaseService.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return FileResponse(FRONTEND_DIR / "room.html")


@app.get("/present/{room_id}")
async def presenter_page(room_id: str) -> FileResponse:
    """Serve the presenter interface for a room."""
    room = await AsyncDatabaseService.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return FileResponse(FRONTEND_DIR / "presenter.html")


@app.get("/test-transcribe")
async def test_transcribe_page() -> FileResponse:
    """Serve the test transcription interface for debugging."""
    return FileResponse(FRONTEND_DIR / "test-transcribe.html")


class RoomStatusUpdate(BaseModel):
    is_live: bool
    presenter_session_id: str | None = None


@app.put("/api/rooms/{room_id}/status")
async def update_room_status(room_id: str, update: RoomStatusUpdate) -> dict:
    """Update room live status."""
    room = await AsyncDatabaseService.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    if update.is_live and not room.is_live:
        # Starting live session
        updated_room = await AsyncDatabaseService.start_room(
            room_id, update.presenter_session_id or ""
        )
        
        # Notify all room participants that the session has started
        participants = ROOM_PARTICIPANTS.get(room_id, set())
        message = {
            "type": "room_status",
            "is_live": True,
            "room_id": room_id,
            "participant_count": len(participants)
        }
        for participant_queue in participants:
            with contextlib.suppress(Exception):
                await participant_queue.put(message)
                
    elif not update.is_live and room.is_live:
        # Ending live session
        updated_room = await AsyncDatabaseService.end_room(room_id)
        
        # Notify all room participants that the session has ended
        participants = ROOM_PARTICIPANTS.get(room_id, set())
        message = {
            "type": "room_status",
            "is_live": False,
            "room_id": room_id,
            "participant_count": len(participants)
        }
        for participant_queue in participants:
            with contextlib.suppress(Exception):
                await participant_queue.put(message)
    else:
        updated_room = room
    
    return {"success": True, "is_live": updated_room.is_live}


# Participant Analytics Endpoints
@app.get("/api/rooms/{room_id}/analytics")
async def get_room_analytics(room_id: str, hours: int = 24):
    """Get participant analytics for a room."""
    try:
        # Check if room exists
        room = await AsyncDatabaseService.get_room(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        # Get participant statistics
        stats = await AsyncDatabaseService.get_participant_stats(room_id, hours)
        events = await AsyncDatabaseService.get_participant_events(room_id, hours)
        current_count = await AsyncDatabaseService.get_current_participant_count(room_id)
        
        # Calculate summary metrics
        total_participants = len(set(event.participant_id for event in events))
        peak_participants = max((s.peak_participants or 0 for s in stats), default=0)
        
        # Prepare time series data for charts
        time_series = []
        for stat in stats:
            time_series.append({
                "timestamp": stat.time_window.isoformat(),
                "current_participants": stat.current_participants,
                "peak_participants": stat.peak_participants,
                "total_joins": stat.total_joins,
                "total_leaves": stat.total_leaves
            })
        
        return {
            "room_id": room_id,
            "summary": {
                "current_participants": current_count,
                "total_participants": total_participants,
                "peak_participants": peak_participants,
                "total_events": len(events)
            },
            "time_series": time_series,
            "events": [event.to_dict() for event in events[-50:]]  # Last 50 events
        }
        
    except Exception as e:
        get_logger().error(f"Error getting room analytics for {room_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Analytics failed: {str(e)}")


@app.get("/api/rooms/{room_id}/participants/current")
async def get_current_participants(room_id: str):
    """Get current participant count for a room."""
    try:
        room = await AsyncDatabaseService.get_room(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        count = await AsyncDatabaseService.get_current_participant_count(room_id)
        websocket_count = len(ROOM_PARTICIPANTS.get(room_id, set()))
        
        return {
            "room_id": room_id,
            "current_participants": count,
            "websocket_connections": websocket_count,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        get_logger().error(f"Error getting current participants for {room_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@dataclass
class ConnectionState:
    websocket: WebSocket
    session_id: str
    sample_rate: int
    transcript: SessionTranscript
    last_partial: str = ""
    speech_active: bool = False
    last_status: str = "idle"
    created_at: datetime = field(default_factory=datetime.utcnow)
    transcript_path: Path | None = None
    room_id: str | None = None

    def reset_partial(self) -> None:
        self.last_partial = ""


def auto_save_transcript(state: ConnectionState) -> None:
    """Persist the running transcript to a single file per session."""

    try:
        subtitles_dir = Path("/app/subtitles")
        subtitles_dir.mkdir(parents=True, exist_ok=True)

        if state.transcript_path is None:
            filename = f"transcript_session_{state.session_id[:8]}.txt"
            state.transcript_path = subtitles_dir / filename

        content = state.transcript.to_text().strip()
        if not content:
            return

        fmt = "%Y-%m-%d %H:%M:%S UTC"
        header = (
            f"Session: {state.session_id}\n"
            f"Started: {state.created_at.strftime(fmt)}\n"
            f"Saved: {datetime.utcnow().strftime(fmt)}\n"
        )
        divider = "=" * 50 + "\n\n"

        with open(state.transcript_path, "w", encoding="utf-8") as handle:
            handle.write(header)
            handle.write(divider)
            handle.write(content)

        print("💾 Auto-saved transcript to", state.transcript_path.name)
    except OSError as err:  # pragma: no cover - log only
        print(f"❌ Failed to auto-save transcript: {err}")


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
    
    # Register session for room management and following
    ACTIVE_SESSIONS[sess_id] = state
    
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
                
                # EMERGENCY FILTER: Block any disclaimer content
                disclaimer_patterns = [
                    "please see the complete disclaimer",
                    "sites.google.com",
                    "all rights reserved",
                    "privacy policy",
                    "terms of service",
                    "disclaimer"
                ]
                if any(pattern in english_text.lower() for pattern in disclaimer_patterns):
                    # Log blocked content for debugging
                    jsonify_log("WARNING", {
                        "message": "Blocked disclaimer content",
                        "text": english_text,
                        "session": sess_id
                    })
                    continue  # Skip this result completely
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
                
                # Broadcast to room participants if this session is a presenter
                active_rooms = await AsyncDatabaseService.get_active_rooms()
                for room in active_rooms:
                    if room.presenter_session_id == sess_id:
                        participants = ROOM_PARTICIPANTS.get(
                            room.room_id, set()
                        )
                        for participant_q in participants:
                            with contextlib.suppress(Exception):
                                await participant_q.put(message)
                        break
                
                if result.is_final:
                    state.transcript.add_segment(message)
                    auto_save_transcript(state)
                    
                    # Save to database if linked to a room
                    if state.room_id:
                        try:
                            # Save subtitle segment
                            await AsyncDatabaseService.save_subtitle_segment(
                                room_id=state.room_id,
                                segment_id=message.get("segmentId", ""),
                                timestamp_ms=message.get("startMs", 0),
                                duration_ms=(message.get("endMs", 0) -
                                             message.get("startMs", 0)),
                                sequence_number=len(state.transcript.segments),
                                text_en=message.get("text", ""),
                                text_th=message.get("thai", ""),
                                confidence_en=message.get("confidence", 0.0),
                                confidence_th=(
                                    getattr(translation, 'confidence', 0.0)
                                    if 'translation' in locals() else 0.0
                                ),
                                processing_time_ms=message.get(
                                    "processingMs", 0
                                ),
                                is_final=True
                            )
                        except Exception as e:
                            get_logger().error(f"Failed to save subtitle: {e}")
                    
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
                    room_id = data.get("roomId")
                    
                    # Link session to room if roomId provided
                    if room_id:
                        room = await AsyncDatabaseService.get_room(room_id)
                        if room:
                            state.room_id = room_id
                            if not room.presenter_session_id:
                                await AsyncDatabaseService.update_presenter_session(
                                    room_id, sess_id
                                )
                                get_logger().info(
                                    f"Linked session {sess_id} to room {room_id}"
                                )
                    
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
            timestamp = utc_timestamp_ms()
            await asr_stream.push_audio(chunk, timestamp)
            
            # Save audio chunk to database if linked to room
            if state.room_id:
                try:
                    await AsyncDatabaseService.save_audio_segment(
                        room_id=state.room_id,
                        segment_id=f"{sess_id}-{timestamp}",
                        timestamp_ms=timestamp,
                        duration_ms=(len(chunk) * 1000 //
                                     (state.sample_rate * 2)),
                        sequence_number=int(timestamp / 1000),  # rough seq
                        audio_data=chunk,
                        audio_language="en",  # assuming English input
                        sample_rate=state.sample_rate,
                        channels=1,
                        bit_depth=16
                    )
                except Exception:
                    # Don't log every chunk save error to avoid spam
                    pass
            
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
        # Remove from active sessions
        ACTIVE_SESSIONS.pop(sess_id, None)
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


@app.websocket("/ws/room/{room_id}")
async def ws_room_participant(websocket: WebSocket, room_id: str) -> None:
    """Room participant WebSocket for real-time updates."""
    room = await AsyncDatabaseService.get_room(room_id)
    if not room:
        await websocket.close(code=4404, reason="Room not found")
        return
        
    await websocket.accept()
    
    # Generate unique participant ID and extract connection info
    participant_id = str(uuid4())
    session_id = str(uuid4())
    client_host = websocket.client.host if websocket.client else "unknown"
    user_agent = websocket.headers.get("user-agent", "unknown")
    
    get_logger().info(f"Participant {participant_id} connected to room: {room_id}")

    # Record participant join event
    await AsyncDatabaseService.record_participant_event(
        room_id=room_id,
        session_id=session_id,
        event_type="join",
        participant_id=participant_id,
        user_agent=user_agent,
        ip_address=client_host,
        metadata={"connection_time": datetime.utcnow().isoformat()}
    )

    q: asyncio.Queue[Optional[dict]] = asyncio.Queue()
    room_participants = ROOM_PARTICIPANTS.setdefault(room_id, set())
    room_participants.add(q)
    
    # Send current room status
    await websocket.send_json({
        "type": "room_status",
        "is_live": room.is_live,
        "participant_count": len(room_participants)
    })
    
    # If room has a presenter session, send existing transcript
    if (room.presenter_session_id and
            room.presenter_session_id in ACTIVE_SESSIONS):
        session_state = ACTIVE_SESSIONS[room.presenter_session_id]
        await websocket.send_json({
            "type": "transcript",
            "transcript": session_state.transcript.to_serializable()
        })

    sender = asyncio.create_task(_follower_sender(websocket, q))
    try:
        # Room participants are receive-only; keep connection open
        while True:
            msg = await websocket.receive()
            if "type" in msg and msg["type"] == "websocket.disconnect":
                break
    finally:
        # Record participant leave event
        with contextlib.suppress(Exception):
            await AsyncDatabaseService.record_participant_event(
                room_id=room_id,
                session_id=session_id,
                event_type="leave",
                participant_id=participant_id,
                user_agent=user_agent,
                ip_address=client_host,
                metadata={"disconnect_time": datetime.utcnow().isoformat()}
            )
        
        # Unregister participant
        with contextlib.suppress(KeyError):
            room_participants.discard(q)
        with contextlib.suppress(Exception):
            await q.put(None)
        with contextlib.suppress(Exception):
            await sender


# Room Data Export Endpoints
@app.get("/api/rooms/{room_id}/export")
async def export_room_data(room_id: str):
    """Export all room data including transcripts and audio files"""
    import zipfile
    import tempfile
    import json
    from io import BytesIO
    
    try:
        # Get room info
        room = await AsyncDatabaseService.get_room(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        # Get all associated data
        db_service = AsyncDatabaseService
        audio_segments = await db_service.get_room_audio_segments(room_id)
        subtitle_segments = await db_service.get_room_subtitle_segments(room_id)
        session_history = await db_service.get_room_session_history(room_id)
        
        # Create ZIP file in memory
        zip_buffer = BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Add room metadata
            room_metadata = {
                "room_id": room.room_id,
                "title": room.title,
                "description": room.description,
                "created_at": room.created_at.isoformat(),
                "updated_at": room.updated_at.isoformat(),
                "is_live": room.is_live,
                "duration_ms": room.duration_ms,
                "total_audio_segments": len(audio_segments),
                "total_subtitle_segments": len(subtitle_segments),
                "session_count": len(session_history)
            }
            zip_file.writestr("room_metadata.json", json.dumps(room_metadata, indent=2))
            
            # Add transcripts as JSON and TXT
            if subtitle_segments:
                # JSON format with all metadata
                subtitles_json = []
                # TXT format for easy reading
                transcript_en = []
                transcript_th = []
                
                for segment in subtitle_segments:
                    subtitles_json.append({
                        "timestamp_ms": segment.timestamp_ms,
                        "sequence_number": segment.sequence_number,
                        "text_en": segment.text_en,
                        "text_th": segment.text_th,
                        "confidence_score": segment.confidence_score,
                        "created_at": segment.created_at.isoformat()
                    })
                    
                    if segment.text_en:
                        transcript_en.append(f"[{segment.timestamp_ms//1000}s] {segment.text_en}")
                    if segment.text_th:
                        transcript_th.append(f"[{segment.timestamp_ms//1000}s] {segment.text_th}")
                
                zip_file.writestr("subtitles.json", json.dumps(subtitles_json, indent=2))
                zip_file.writestr("transcript_english.txt", "\n".join(transcript_en))
                zip_file.writestr("transcript_thai.txt", "\n".join(transcript_th))
            
            # Add audio segments
            if audio_segments:
                audio_metadata = []
                for i, segment in enumerate(audio_segments):
                    if segment.audio_data:
                        # Save audio as WAV file
                        filename = f"audio_segment_{i:04d}_{segment.timestamp_ms}ms.wav"
                        zip_file.writestr(f"audio/{filename}", segment.audio_data)
                        
                        audio_metadata.append({
                            "filename": filename,
                            "segment_id": segment.segment_id,
                            "timestamp_ms": segment.timestamp_ms,
                            "duration_ms": segment.duration_ms,
                            "sequence_number": segment.sequence_number,
                            "audio_language": segment.audio_language,
                            "sample_rate": segment.sample_rate,
                            "channels": segment.channels,
                            "bit_depth": segment.bit_depth,
                            "created_at": segment.created_at.isoformat()
                        })
                
                zip_file.writestr("audio_metadata.json", json.dumps(audio_metadata, indent=2))
            
            # Add session history
            if session_history:
                sessions_data = []
                for session in session_history:
                    sessions_data.append({
                        "session_id": session.session_id,
                        "started_at": session.started_at.isoformat(),
                        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
                        "duration_ms": session.duration_ms,
                        "total_segments": session.total_segments,
                        "metadata": session.metadata
                    })
                
                zip_file.writestr("session_history.json", json.dumps(sessions_data, indent=2))
        
        zip_buffer.seek(0)
        
        # Return ZIP file
        return Response(
            content=zip_buffer.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=room_{room_id}_export.zip"}
        )
        
    except Exception as e:
        logger.error(f"Error exporting room data for {room_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@app.delete("/api/rooms/{room_id}")
async def delete_room(room_id: str):
    """Delete a room and all associated data"""
    try:
        # Check if room exists
        room = await AsyncDatabaseService.get_room(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        # Check if room is currently live
        if room.is_live:
            raise HTTPException(status_code=400, detail="Cannot delete a live room")
        
        # Delete all associated data (cascading deletes should handle this)
        success = await AsyncDatabaseService.delete_room(room_id)
        
        if success:
            return {"message": "Room deleted successfully", "room_id": room_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete room")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting room {room_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


# Add helper methods to DatabaseService
async def get_room_audio_segments(room_id: str):
    """Get all audio segments for a room"""
    async with get_async_session() as session:
        result = await session.execute(
            select(AudioSegment).where(AudioSegment.room_id == room_id).order_by(AudioSegment.timestamp_ms)
        )
        return result.scalars().all()


async def get_room_subtitle_segments(room_id: str):
    """Get all subtitle segments for a room"""
    async with get_async_session() as session:
        result = await session.execute(
            select(SubtitleSegment).where(SubtitleSegment.room_id == room_id).order_by(SubtitleSegment.timestamp_ms)
        )
        return result.scalars().all()


async def get_room_session_history(room_id: str):
    """Get all session history for a room"""
    async with get_async_session() as session:
        result = await session.execute(
            select(SessionHistory).where(SessionHistory.room_id == room_id).order_by(SessionHistory.started_at)
        )
        return result.scalars().all()


async def delete_room(room_id: str):
    """Delete a room and all associated data"""
    async with get_async_session() as session:
        try:
            # Delete room (cascading should handle related data)
            result = await session.execute(
                delete(SeminarRoom).where(SeminarRoom.room_id == room_id)
            )
            await session.commit()
            return result.rowcount > 0
        except Exception as e:
            await session.rollback()
            raise


# Add these methods to AsyncDatabaseService class
AsyncDatabaseService.get_room_audio_segments = staticmethod(get_room_audio_segments)
AsyncDatabaseService.get_room_subtitle_segments = staticmethod(get_room_subtitle_segments)
AsyncDatabaseService.get_room_session_history = staticmethod(get_room_session_history)
AsyncDatabaseService.delete_room = staticmethod(delete_room)
