from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import wave
import audioop
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
    Depends,
    status,
    Request,
)
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from .auth import auth_service, get_current_user_dep, require_admin_dep
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
    tts_provider: str = Field(default="mock", alias="TTS_PROVIDER")
    tts_voice: str = Field(default="nova", alias="TTS_VOICE")
    tts_speed: float = Field(default=1.0, alias="TTS_SPEED")
    supported_languages: str = Field(
        default="en,th", alias="SUPPORTED_LANGUAGES"
    )
    default_source_language: str = Field(
        default="en", alias="DEFAULT_SOURCE_LANGUAGE"
    )
    default_target_language: str = Field(
        default="th", alias="DEFAULT_TARGET_LANGUAGE"
    )
    sample_audio_files: str = Field(
        default="en_sample.wav", alias="SAMPLE_AUDIO_FILES"
    )
    cors_origins: str = Field(
        default="http://localhost:8000",
        alias="CORS_ORIGINS",
    )
    audio_sample_rate: int = Field(default=16000, alias="AUDIO_SAMPLE_RATE")
    audio_storage_path: str = Field(
        default="/app/media/audio", alias="AUDIO_STORAGE_PATH"
    )
    max_audio_file_size_mb: int = Field(
        default=100, alias="MAX_AUDIO_FILE_SIZE_MB"
    )
    min_silence_ms: int = Field(default=600, alias="MIN_SILENCE_MS")
    status_broadcast_interval_ms: int = Field(
        default=1000,
        alias="STATUS_INTERVAL_MS",
    )
    thai_politeness_gender: str = Field(
        default="neutral",
        alias="THAI_POLITENESS_GENDER",
    )

    class Config:
        case_sensitive = False
        env_file = ".env"
        extra = "ignore"
# Helper to resolve the public base URL for links
def resolve_base_url(request: "Request") -> str:
    # Prefer explicit env override, else derive from incoming request
    env_base = os.getenv("BASE_URL")
    if env_base:
        return env_base.rstrip("/")
    try:
        return str(request.base_url).rstrip("/")
    except Exception:
        # Sensible default if request context not available
        return "http://localhost:8000"


# Audio storage utilities
async def ensure_audio_directory(path: str) -> None:
    """Ensure audio storage directory exists"""
    os.makedirs(path, exist_ok=True)


def get_audio_filename(room_id: str, segment_id: int, language: str) -> str:
    """Generate standardized audio filename"""
    return f"{segment_id:06d}_{language}.wav"


def get_audio_file_path(
    storage_path: str, room_id: str, segment_id: int, language: str
) -> str:
    """Get full path for audio file"""
    filename = get_audio_filename(room_id, segment_id, language)
    return os.path.join(storage_path, room_id, filename)


async def save_audio_to_file(
    audio_data: bytes, file_path: str, sample_rate: int = 16000
) -> bool:
    """Save audio data to WAV file"""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Save as WAV file
        with wave.open(file_path, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            
            # Convert to 16-bit if needed
            if len(audio_data) % 2 != 0:
                audio_data = audio_data[:-1]  # Remove odd byte
            
            wav_file.writeframes(audio_data)
        
        return True
    except Exception as e:
        print(f"Error saving audio file {file_path}: {e}")
        return False


async def save_thai_audio_to_file(
    audio_base64: str, file_path: str, audio_format: str = "mp3"
) -> bool:
    """Save Thai TTS audio from base64 to file"""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Decode base64 audio
        audio_bytes = base64.b64decode(audio_base64)
        
        # Determine file extension
        if audio_format.lower() == "wav":
            final_path = file_path.replace(".wav", "_thai.wav")
        else:
            final_path = file_path.replace(".wav", "_thai.mp3")
        
        # Save the audio file
        with open(final_path, 'wb') as f:
            f.write(audio_bytes)
        
        return True
    except Exception as e:
        print(f"Error saving Thai audio file {file_path}: {e}")
        return False


async def generate_thai_audio_placeholder(
    file_path: str, duration_ms: int, sample_rate: int = 16000
) -> bool:
    """Generate a placeholder silent audio file for Thai audio"""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Calculate number of samples for the given duration
        duration_seconds = duration_ms / 1000.0
        num_samples = int(duration_seconds * sample_rate)
        
        # Generate silent audio data (16-bit mono)
        silent_data = b'\x00' * (num_samples * 2)  # 2 bytes per 16-bit sample
        
        with wave.open(file_path, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(silent_data)
        
        return True
    except Exception as e:
        print(f"Error generating Thai audio placeholder {file_path}: {e}")
        return False


async def render_final_audio_files(room_id: str, storage_path: str) -> dict:
    """Render final audio files by concatenating all segments for a room"""
    try:
        room_path = os.path.join(storage_path, room_id)
        if not os.path.exists(room_path):
            return {"success": False, "error": "Room audio directory not found"}
        
        # Get all audio files
        audio_files = []
        for filename in sorted(os.listdir(room_path)):
            if filename.endswith('.wav') or filename.endswith('.mp3'):
                audio_files.append(os.path.join(room_path, filename))
        
        if not audio_files:
            return {"success": False, "error": "No audio files found"}
        
        # Separate English and Thai audio files
        english_files = [f for f in audio_files if '_en.wav' in f]
        thai_files = [f for f in audio_files if '_th.wav' in f]
        
        final_files = {}
        
        # Render English audio
        if english_files:
            english_output = os.path.join(room_path, f"{room_id}_final_english.wav")
            if await concatenate_wav_files(english_files, english_output):
                final_files['english'] = english_output
        
        # Render Thai audio  
        if thai_files:
            thai_output = os.path.join(room_path, f"{room_id}_final_thai.wav")
            if await concatenate_audio_files(thai_files, thai_output):
                final_files['thai'] = thai_output
        
        return {
            "success": True,
            "files": final_files,
            "total_segments": len(audio_files),
            "english_segments": len(english_files),
            "thai_segments": len(thai_files)
        }
    
    except Exception as e:
        print(f"Error rendering final audio files for room {room_id}: {e}")
        return {"success": False, "error": str(e)}


async def concatenate_wav_files(input_files: list, output_file: str) -> bool:
    """Concatenate multiple WAV files into a single file"""
    try:
        if not input_files:
            return False
        
        # Open first file to get parameters
        with wave.open(input_files[0], 'rb') as first_wav:
            params = first_wav.getparams()
        
        # Create output file with same parameters
        with wave.open(output_file, 'wb') as output_wav:
            output_wav.setparams(params)
            
            # Concatenate all input files
            for input_file in input_files:
                with wave.open(input_file, 'rb') as input_wav:
                    frames = input_wav.readframes(input_wav.getnframes())
                    output_wav.writeframes(frames)
        
        return True
    except Exception as e:
        print(f"Error concatenating WAV files: {e}")
        return False


async def concatenate_audio_files(input_files: list, output_file: str) -> bool:
    """Concatenate mixed audio files (WAV/MP3) into a single WAV file"""
    try:
        if not input_files:
            return False
        
        # Use ffmpeg if available, otherwise fallback to simple concatenation for WAV
        wav_files = [f for f in input_files if f.endswith('.wav')]
        
        if len(wav_files) == len(input_files):
            # All WAV files, use simple concatenation
            return await concatenate_wav_files(input_files, output_file)
        else:
            # Mixed formats, create a simple WAV output for compatibility
            # For now, create a placeholder final file
            return await create_audio_placeholder(output_file, len(input_files) * 5000)  # 5 seconds per segment estimate
    
    except Exception as e:
        print(f"Error concatenating mixed audio files: {e}")
        return False


async def create_audio_placeholder(file_path: str, duration_ms: int) -> bool:
    """Create placeholder audio file"""
    return await generate_thai_audio_placeholder(file_path, duration_ms)


async def synthesize_thai_audio(
    thai_text: str, file_path: str, sample_rate: int = 16000
) -> bool:
    """Synthesize Thai audio using TTS provider"""
    try:
        from .providers import create_tts_provider
        from .providers.tts_base import TTSRequest
        
        if not thai_text.strip():
            return False
        
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Get TTS provider configuration
        tts_provider_name = os.getenv("TTS_PROVIDER", "mock")
        
        # Skip synthesis for disabled or mock providers
        if tts_provider_name in ["disabled", "mock"]:
            return await generate_thai_audio_placeholder(
                file_path, 2000, sample_rate
            )
        
        # Get or create singleton TTS provider to prevent session leaks
        global TTS_PROVIDER_INSTANCE
        if (TTS_PROVIDER_INSTANCE is None or 
            getattr(TTS_PROVIDER_INSTANCE, 'name', None) != tts_provider_name):
            # Cleanup old provider if exists
            if TTS_PROVIDER_INSTANCE is not None:
                try:
                    await TTS_PROVIDER_INSTANCE.cleanup()
                except:
                    pass
            # Create new provider
            TTS_PROVIDER_INSTANCE = create_tts_provider(tts_provider_name)
            TTS_PROVIDER_INSTANCE.name = tts_provider_name  # Track provider type
            await TTS_PROVIDER_INSTANCE.setup()
        tts_provider = TTS_PROVIDER_INSTANCE
        
        # Configure Thai voice based on provider
        voice_id = "alloy"  # Default fallback
        if tts_provider_name == "google":
            # Use high-quality Thai neural voice
            voice_id = "th-TH-Neural2-A"  # Female Thai voice
        elif tts_provider_name == "aws_polly":
            voice_id = "Naja"  # Thai female voice
        elif tts_provider_name == "openai":
            voice_id = "nova"  # OpenAI voice (multilingual)
        
        # Create TTS request
        tts_request = TTSRequest(
            text=thai_text,
            voice_id=voice_id,
            speed=float(os.getenv("TTS_SPEED", "1.0")),
            language="th"
        )
        
        # Synthesize speech
        result = await tts_provider.synthesize(tts_request)
        
        if result.success and result.audio_data:
            # Save audio data to file
            with open(file_path, 'wb') as f:
                f.write(result.audio_data)
            
            jsonify_log("INFO", {
                "message": "✅ Thai audio synthesized",
                "file_path": file_path,
                "text_length": len(thai_text),
                "voice": result.voice_used,
                "duration_ms": result.duration_ms
            })
            return True
        else:
            error_msg = (
                result.error_message if hasattr(result, 'error_message')
                else "Unknown error"
            )
            jsonify_log("WARNING", {
                "message": "❌ TTS synthesis failed, using placeholder",
                "text": thai_text[:50] + "...",
                "error": error_msg
            })
            # Fallback to placeholder
            return await generate_thai_audio_placeholder(
                file_path, 2000, sample_rate
            )
        
    except Exception as e:
        jsonify_log("ERROR", {
            "message": "💥 Exception in Thai audio synthesis",
            "error": str(e),
            "text": thai_text[:50] + "..."
        })
        # Fallback to placeholder
        return await generate_thai_audio_placeholder(
            file_path, 2000, sample_rate
        )


async def synthesize_thai_audio_base64(thai_text: str) -> Optional[str]:
    """Synthesize Thai audio and return as base64 for WebSocket streaming"""
    try:
        from .providers import create_tts_provider
        from .providers.tts_base import TTSRequest
        import base64
        
        if not thai_text.strip():
            return None
        
        # Get TTS provider configuration
        tts_provider_name = os.getenv("TTS_PROVIDER", "mock")
        
        # Skip synthesis for disabled or mock providers
        if tts_provider_name in ["disabled", "mock"]:
            return None
        
        # Get or create singleton TTS provider to prevent session leaks
        global TTS_PROVIDER_INSTANCE
        if (TTS_PROVIDER_INSTANCE is None or 
            getattr(TTS_PROVIDER_INSTANCE, 'name', None) != tts_provider_name):
            # Cleanup old provider if exists
            if TTS_PROVIDER_INSTANCE is not None:
                try:
                    await TTS_PROVIDER_INSTANCE.cleanup()
                except Exception:
                    pass
            # Create new provider
            TTS_PROVIDER_INSTANCE = create_tts_provider(tts_provider_name)
            TTS_PROVIDER_INSTANCE.name = tts_provider_name  # Track provider
            await TTS_PROVIDER_INSTANCE.setup()
        tts_provider = TTS_PROVIDER_INSTANCE
        
        # Configure voice
        voice_id = "nova"  # Default for streaming
        if tts_provider_name == "aws_polly":
            voice_id = "Naja"  # Thai female voice
        
        # Create TTS request
        tts_request = TTSRequest(
            text=thai_text,
            voice_id=voice_id,
            speed=float(os.getenv("OPENAI_TTS_SPEED", "1.0")),
            language="th"
        )
        
        # Synthesize speech
        result = await tts_provider.synthesize(tts_request)
        
        if result and hasattr(result, 'success') and result.success and result.audio_data:
            # Return audio as base64
            audio_base64 = base64.b64encode(result.audio_data).decode()
            return audio_base64
        elif result and hasattr(result, 'audio_data') and result.audio_data:
            # Handle direct audio data return
            audio_base64 = base64.b64encode(result.audio_data).decode()
            return audio_base64
        else:
            return None
            
    except Exception as e:
        jsonify_log("ERROR", {
            "message": "Failed to synthesize audio for streaming",
            "error": str(e),
            "text": thai_text[:50] + "..."
        })
        return None


async def synthesize_english_audio_base64(english_text: str) -> Optional[str]:
    """Synthesize English audio and return as base64 for WebSocket streaming"""
    try:
        from .providers import create_tts_provider
        from .providers.tts_base import TTSRequest
        import base64
        
        if not english_text.strip():
            return None
        
        # Get TTS provider configuration
        tts_provider_name = os.getenv("TTS_PROVIDER", "mock")
        
        # Skip synthesis for disabled or mock providers
        if tts_provider_name in ["disabled", "mock"]:
            return None
        
        # Get or create singleton TTS provider to prevent session leaks
        global TTS_PROVIDER_INSTANCE
        if (TTS_PROVIDER_INSTANCE is None or 
            getattr(TTS_PROVIDER_INSTANCE, 'name', None) != tts_provider_name):
            # Cleanup old provider if exists
            if TTS_PROVIDER_INSTANCE is not None:
                try:
                    await TTS_PROVIDER_INSTANCE.cleanup()
                except Exception:
                    pass
            # Create new provider
            TTS_PROVIDER_INSTANCE = create_tts_provider(tts_provider_name)
            TTS_PROVIDER_INSTANCE.name = tts_provider_name  # Track provider
            await TTS_PROVIDER_INSTANCE.setup()
        tts_provider = TTS_PROVIDER_INSTANCE
        
        # Configure voice for English
        voice_id = "alloy"  # Different voice for English
        if tts_provider_name == "aws_polly":
            voice_id = "Matthew"  # English male voice
        
        # Create TTS request
        tts_request = TTSRequest(
            text=english_text,
            voice_id=voice_id,
            speed=float(os.getenv("OPENAI_TTS_SPEED", "1.0")),
            language="en"
        )
        
        # Synthesize audio
        result = await tts_provider.synthesize(tts_request)
        if result and hasattr(result, 'audio_data') and result.audio_data:
            # Convert to base64
            return base64.b64encode(result.audio_data).decode('utf-8')
        elif result and hasattr(result, 'success') and result.success and result.audio_data:
            return base64.b64encode(result.audio_data).decode('utf-8')
        else:
            return None
            
    except Exception as e:
        jsonify_log("ERROR", {
            "message": "Failed to synthesize English audio for streaming",
            "error": str(e),
            "text": english_text[:50] + "..."
        })
        return None


async def get_room_audio_files(storage_path: str, room_id: str) -> list[dict]:
    """Get all audio files for a room with metadata"""
    room_path = os.path.join(storage_path, room_id)
    if not os.path.exists(room_path):
        return []
    
    files = []
    for filename in sorted(os.listdir(room_path)):
        if filename.endswith('.wav'):
            file_path = os.path.join(room_path, filename)
            # Parse filename: {segment_id:06d}_{language}.wav
            parts = filename.replace('.wav', '').split('_')
            if len(parts) >= 2:
                try:
                    segment_id = int(parts[0])  # First part is segment_id
                    language = parts[1]         # Second part is language
                    file_size = os.path.getsize(file_path)
                    files.append({
                        'segment_id': segment_id,
                        'language': language,
                        'filename': filename,
                        'path': file_path,
                        'size': file_size
                    })
                except ValueError:
                    continue
    
    return sorted(files, key=lambda x: x['segment_id'])



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

# Mount sample audio directory
SAMPLE_AUDIO_DIR = BASE_DIR / "sample_audio"
if SAMPLE_AUDIO_DIR.exists():
    app.mount(
        "/static/sample_audio",
        StaticFiles(directory=str(SAMPLE_AUDIO_DIR)),
        name="sample_audio",
    )


ASR_PROVIDER = create_asr_provider(
    settings.asr_provider,
    base_dir=BASE_DIR,
    settings=os.environ,
)
get_logger().info(f"ASR Provider: {ASR_PROVIDER.__class__.__name__} ({settings.asr_provider})")
MT_PROVIDER: MTProvider = create_mt_provider(
    settings.mt_provider,
    base_dir=BASE_DIR,
    settings=os.environ,
)

# TTS Provider singleton to prevent HTTP session leaks
TTS_PROVIDER_INSTANCE = None

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


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Clean up resources on shutdown to prevent session leaks"""
    global TTS_PROVIDER_INSTANCE
    if TTS_PROVIDER_INSTANCE is not None:
        try:
            await TTS_PROVIDER_INSTANCE.cleanup()
            TTS_PROVIDER_INSTANCE = None
        except Exception:
            pass


# ===== AUTHENTICATION ENDPOINTS =====

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict

class UserResponse(BaseModel):
    username: str
    email: str
    is_admin: bool
    created_at: datetime
    is_active: bool

class CreateUserRequest(BaseModel):
    username: str
    email: str
    password: str
    is_admin: bool = False

@app.post("/api/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Authenticate user and return access tokens"""
    user = auth_service.authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = auth_service.create_access_token(
        data={"sub": user["username"], "is_admin": user.get("is_admin", False)}
    )
    refresh_token = auth_service.create_refresh_token(
        data={"sub": user["username"]}
    )
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={k: v for k, v in user.items() if k != "hashed_password"}
    )

@app.post("/api/auth/refresh")
async def refresh_token(refresh_token: str):
    """Refresh access token using refresh token"""
    payload = auth_service.verify_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    username = payload.get("sub")
    user = auth_service.get_user_by_username(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    access_token = auth_service.create_access_token(
        data={"sub": username, "is_admin": user.get("is_admin", False)}
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user_dep)):
    """Get current user information"""
    return UserResponse(**current_user)

@app.post("/api/auth/users", response_model=UserResponse)
async def create_user(request: CreateUserRequest, current_user: dict = Depends(require_admin_dep)):
    """Create a new user (admin only)"""
    user = auth_service.create_user(
        username=request.username,
        email=request.email,
        password=request.password,
        is_admin=request.is_admin
    )
    return UserResponse(**user)

@app.get("/api/auth/users", response_model=list[UserResponse])
async def list_users(current_user: dict = Depends(require_admin_dep)):
    """List all users (admin only)"""
    users = auth_service.list_users()
    return [UserResponse(**user) for user in users]


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "asr_provider": ASR_PROVIDER.name,
        "mt_provider": MT_PROVIDER.name,
        "timestamp": utc_timestamp_ms(),
    })


@app.get("/", include_in_schema=False)
async def root_redirect() -> RedirectResponse:
    """Primary entry point redirects to login page."""
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)


@app.get("/dashboard")
async def dashboard() -> FileResponse:
    """Main dashboard - authentication handled by frontend JavaScript"""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/login")
async def login_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "login.html")


@app.get("/analytics")
async def analytics_page() -> FileResponse:
    """Analytics dashboard - authentication handled by frontend JavaScript"""
    return FileResponse(FRONTEND_DIR / "analytics.html")


@app.get("/settings") 
async def settings_page() -> FileResponse:
    """Settings page - authentication handled by frontend JavaScript"""
    return FileResponse(FRONTEND_DIR / "settings.html")


@app.get("/public")
async def public_rooms() -> FileResponse:
    """Public participant access - no authentication required"""
    return FileResponse(FRONTEND_DIR / "participant.html")


@app.get("/room-audio")
async def room_audio_page() -> FileResponse:
    """Room audio playback page - authentication handled by frontend"""
    return FileResponse(FRONTEND_DIR / "room-audio.html")


@app.get("/settings-admin")
async def settings_admin_page(
    current_user: dict = Depends(require_admin_dep),
) -> FileResponse:
    """Settings page - Admin only"""
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
            ["whisper_api", "whisper_gpt", "gpt_realtime",
             "gpt_4o_audio", "hybrid"]
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
                    "description": "OpenAI Whisper API ($0.006/min - English only)"
                },
                "gpt_realtime": {
                    "requires_mt": False,
                    "recommended_mt": "simple_thai",
                    "compatible_mt": ["simple_thai"],
                    "description": (
                        "GPT-4o Real-time Audio ($0.06/min input, "
                        "$0.24/min output - Live conversation)"
                    )
                },
                "gpt_4o_audio": {
                    "requires_mt": False,
                    "recommended_mt": "simple_thai",
                    "compatible_mt": ["simple_thai"],
                    "description": (
                        "GPT-4o Audio Preview ($0.15/1M input tokens, "
                        "$0.60/1M output tokens - Audio input/output model)"
                    )
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
            "mt_provider_info": {
                "openai_gpt": {
                    "description": (
                        "OpenAI GPT models ($0.50/1M input tokens, "
                        "$1.50/1M output tokens)"
                    )
                },
                "marian": {
                    "description": "Helsinki-NLP Marian models (Free, offline)"
                },
                "ctranslate2": {
                    "description": (
                        "Fast CTranslate2 inference engine (Free, offline)"
                    )
                },
                "gtranslate": {
                    "description": (
                        "Google Cloud Translate API ($20/1M characters)"
                    )
                },
                "awstranslate": {
                    "description": "AWS Translate service ($15/1M characters)"
                },
                "simple_thai": {
                    "description": (
                        "Simple word-mapping Thai translation "
                        "(Free, fast but basic)"
                    )
                },
                "mock": {
                    "description": "Mock translation provider for testing"
                }
            },
            "tts_provider_info": {
                "openai": {
                    "description": "OpenAI Text-to-Speech API ($15/1M characters)"
                },
                "aws_polly": {
                    "description": "AWS Polly TTS service ($4/1M characters)"
                },
                "mock": {
                    "description": "Mock TTS provider for testing"
                }
            },
            "provider_categories": {
                "cloud_asr": [
                    "whisper_api", "whisper_gpt", "gpt_realtime",
                    "gpt_4o_audio"
                ],
                "local_asr": [
                    "vosk", "faster_whisper", "whisper_local", "whispercpp"
                ],
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
            "supported": settings.supported_languages.split(","),
            "source": settings.default_source_language,
            "target": settings.default_target_language,
            "available_sources": ["en"],
            "available_targets": ["th"],
        },
        "sample_audio": {
            "available_files": settings.sample_audio_files.split(","),
            "base_path": "/static/sample_audio/"
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


class TranslateRequest(BaseModel):
    text: str
    source_language: str = "en"
    target_language: str = "th"
    politeness_gender: Optional[str] = None


class TranslateResponse(BaseModel):
    text: str
    translated_text: str
    source_language: str
    target_language: str
    politeness_gender: Optional[str] = None
    provider: str


@app.post("/api/translate", response_model=TranslateResponse)
async def translate_text(request: TranslateRequest) -> TranslateResponse:
    """Translate text using MT provider with Thai gender support."""
    try:
        # Set Thai politeness gender if provided
        original_env = None
        if request.politeness_gender:
            original_env = os.environ.get("THAI_POLITENESS_GENDER")
            os.environ["THAI_POLITENESS_GENDER"] = request.politeness_gender
        
        # Use the global MT provider
        mt_provider = MT_PROVIDER
        
        # Perform translation
        mt_result = await mt_provider.translate(
            request.text,
            is_final=True
        )
        
        translated_text = mt_result.text
        
        # Restore original environment variable if it was changed
        if original_env is not None:
            os.environ["THAI_POLITENESS_GENDER"] = original_env
        elif request.politeness_gender:
            del os.environ["THAI_POLITENESS_GENDER"]
        
        return TranslateResponse(
            text=request.text,
            translated_text=translated_text,
            source_language=request.source_language,
            target_language=request.target_language,
            politeness_gender=request.politeness_gender,
            provider=MT_PROVIDER.name
        )
        
    except Exception as e:
        # Restore environment variable on error
        if original_env is not None:
            os.environ["THAI_POLITENESS_GENDER"] = original_env
        elif (request.politeness_gender and 
              "THAI_POLITENESS_GENDER" in os.environ):
            del os.environ["THAI_POLITENESS_GENDER"]
            
        raise HTTPException(
            status_code=500,
            detail=f"Translation failed: {str(e)}"
        )

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


@app.get("/api/env")
async def get_env_vars() -> JSONResponse:
    """Get current environment variables for settings page."""
    try:
        import os
        # Return current environment variables that are safe to display
        env_vars = {
            # Core Providers
            "ASR_PROVIDER": os.getenv("ASR_PROVIDER", "vosk"),
            "MT_PROVIDER": os.getenv("MT_PROVIDER", "marian"),
            "TTS_PROVIDER": os.getenv("TTS_PROVIDER", "mock"),
            "TTS_VOICE": os.getenv("TTS_VOICE", "nova"),
            "TTS_SPEED": os.getenv("TTS_SPEED", "1.0"),
            
            # Audio Settings
            "AUDIO_SAMPLE_RATE": os.getenv("AUDIO_SAMPLE_RATE", "16000"),
            "MIN_SILENCE_MS": os.getenv("MIN_SILENCE_MS", "500"),
            "STATUS_INTERVAL_MS": os.getenv("STATUS_INTERVAL_MS", "100"),
            
            # OpenAI
            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
            "OPENAI_WHISPER_MODEL": os.getenv("OPENAI_WHISPER_MODEL", "whisper-1"),
            "OPENAI_GPT_MODEL": os.getenv("OPENAI_GPT_MODEL", "gpt-3.5-turbo"),
            
            # Faster-Whisper
            "FASTER_WHISPER_MODEL": os.getenv("FASTER_WHISPER_MODEL", "small.en"),
            "FASTER_WHISPER_DEVICE": os.getenv("FASTER_WHISPER_DEVICE", "cpu"),
            "FASTER_WHISPER_COMPUTE_TYPE": os.getenv("FASTER_WHISPER_COMPUTE_TYPE", "int8"),
            "FASTER_WHISPER_LANGUAGE": os.getenv("FASTER_WHISPER_LANGUAGE", ""),
            "FASTER_WHISPER_BEAM_SIZE": os.getenv("FASTER_WHISPER_BEAM_SIZE", ""),
            "FASTER_WHISPER_CHUNK_DURATION": os.getenv("FASTER_WHISPER_CHUNK_DURATION", ""),
            
            # Official Whisper
            "WHISPER_MODEL_SIZE": os.getenv("WHISPER_MODEL_SIZE", ""),
            "WHISPER_DEVICE": os.getenv("WHISPER_DEVICE", ""),
            "WHISPER_CHUNK_DURATION": os.getenv("WHISPER_CHUNK_DURATION", ""),
            
            # Google Cloud
            "GCP_PROJECT": os.getenv("GCP_PROJECT", ""),
            "GOOGLE_APPLICATION_CREDENTIALS": os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
            
            # AWS
            "AWS_REGION": os.getenv("AWS_REGION", ""),
            "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID", ""),
            "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
            
            # HuggingFace
            "HUGGINGFACE_TOKEN": os.getenv("HUGGINGFACE_TOKEN", ""),
            
            # Thai Translation
            "THAI_POLITENESS_GENDER": os.getenv("THAI_POLITENESS_GENDER", "female"),
            
            # Admin/Auth (for backward compatibility)
            "JWT_ACCESS_TOKEN_EXPIRE_MINUTES": os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"),
            "ADMIN_USERNAME": os.getenv("ADMIN_USERNAME", "admin"),
            "ADMIN_EMAIL": os.getenv("ADMIN_EMAIL", "admin@example.com"),
        }
        return JSONResponse(content={"status": "success", "env_vars": env_vars})
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


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


# TTS (Text-to-Speech) API Endpoints
@app.get("/api/tts/voices")
async def get_tts_voices() -> JSONResponse:
    """Get available TTS voices for the configured provider."""
    try:
        from .providers import create_tts_provider
        
        tts_provider_name = os.getenv("TTS_PROVIDER", "mock")
        tts_provider = create_tts_provider(tts_provider_name)
        
        await tts_provider.setup()
        voices = tts_provider.get_available_voices()
        
        voices_data = [
            {
                "id": voice.id,
                "name": voice.name,
                "gender": voice.gender,
                "language": voice.language,
                "accent": voice.accent,
                "description": voice.description
            }
            for voice in voices
        ]
        
        return JSONResponse({
            "voices": voices_data,
            "provider": tts_provider_name,
            "status": "success"
        })
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": "Failed to get TTS voices",
                "details": str(e)
            }
        )


@app.post("/api/tts/synthesize")
async def synthesize_speech(request: dict) -> JSONResponse:
    """Synthesize speech from text using TTS provider."""
    try:
        from .providers import create_tts_provider
        from .providers.tts_base import TTSRequest
        
        # Get request parameters
        text = request.get("text", "")
        voice_id = request.get("voice_id", "alloy")
        speed = float(request.get("speed", 1.0))
        language = request.get("language", "th")
        
        if not text:
            return JSONResponse(
                status_code=400,
                content={"error": "Text is required"}
            )
        
        # Create TTS provider
        tts_provider_name = os.getenv("TTS_PROVIDER", "mock")
        tts_provider = create_tts_provider(tts_provider_name)
        
        await tts_provider.setup()
        
        # Create TTS request
        tts_request = TTSRequest(
            text=text,
            voice_id=voice_id,
            speed=speed,
            language=language
        )
        
        # Synthesize speech
        result = await tts_provider.synthesize(tts_request)
        
        if result.success:
            # For mock provider, return metadata only
            if tts_provider_name == "mock":
                return JSONResponse({
                    "status": "success",
                    "mock": True,
                    "message": "Mock TTS synthesis completed",
                    "duration_ms": result.duration_ms,
                    "voice_used": result.voice_used,
                    "text_length": len(text)
                })
            else:
                # For real providers, return audio as base64
                import base64
                audio_base64 = base64.b64encode(result.audio_data).decode()
                
                return JSONResponse({
                    "status": "success",
                    "audio_data": audio_base64,
                    "format": result.format,
                    "duration_ms": result.duration_ms,
                    "voice_used": result.voice_used
                })
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "TTS synthesis failed",
                    "details": result.error_message
                }
            )
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": "Failed to synthesize speech",
                "details": str(e)
            }
        )


@app.post("/api/audio/render")
async def render_room_audio(
    request: dict,
    current_user: dict = Depends(get_current_user_dep)
) -> JSONResponse:
    """Render final audio files for a room session"""
    try:
        room_id = request.get("room_id")
        if not room_id:
            return JSONResponse(
                status_code=400,
                content={"error": "room_id is required"}
            )
        
        # Render final audio files
        result = await render_final_audio_files(room_id, settings.audio_storage_path)
        
        if result["success"]:
            return JSONResponse({
                "status": "success",
                "message": "Audio files rendered successfully",
                "files": result["files"],
                "statistics": {
                    "total_segments": result["total_segments"],
                    "english_segments": result["english_segments"],
                    "thai_segments": result["thai_segments"]
                }
            })
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Failed to render audio files",
                    "details": result["error"]
                }
            )
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": "Audio rendering failed",
                "details": str(e)
            }
        )


@app.get("/teleprompter")
async def teleprompter() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "teleprompter.html")


# === SEMINAR ROOM API ENDPOINTS ===

class CreateRoomRequest(BaseModel):
    title: str
    description: str | None = None
    password: str | None = None
    max_participants: int | None = None


class RoomResponse(BaseModel):
    room_id: str
    title: str
    description: str | None = None
    password: str | None = None
    max_participants: int | None = None
    is_live: bool
    participant_url: str
    presenter_url: str
    created_at: str
    started_at: str | None = None
    ended_at: str | None = None
    participant_count: int = 0
    max_concurrent_participants: int = 0
    duration_ms: int | None = None


@app.post("/api/rooms", response_model=RoomResponse)
async def create_room(payload: CreateRoomRequest, request: Request, current_user: dict = Depends(get_current_user_dep)) -> RoomResponse:
    """Create a new seminar room. Requires authentication."""
    # Create room in database
    room = await AsyncDatabaseService.create_room(
        title=payload.title,
        description=payload.description,
        password=payload.password,
        max_participants=payload.max_participants
    )
    
    # Get base URL from request (or env override)
    base_url = resolve_base_url(request)
    return RoomResponse(
        room_id=room.room_id,
        title=room.title,
        description=room.description,
        password=room.password,
        max_participants=room.max_participants,
        is_live=room.is_live,
        participant_url=room.get_room_url(base_url),
        presenter_url=room.get_presenter_url(base_url),
        created_at=room.created_at.isoformat(),
        started_at=room.started_at.isoformat() if room.started_at else None,
        ended_at=room.ended_at.isoformat() if room.ended_at else None,
        participant_count=len(ROOM_PARTICIPANTS.get(room.room_id, set())),
        max_concurrent_participants=room.max_concurrent_participants,
        duration_ms=room.total_duration_ms
    )


@app.get("/api/rooms", response_model=list[RoomResponse])
async def list_rooms(request: Request) -> list[RoomResponse]:
    """List all seminar rooms."""
    base_url = resolve_base_url(request)
    rooms_data = await AsyncDatabaseService.list_rooms()
    rooms = []
    
    for room in rooms_data:
        rooms.append(RoomResponse(
            room_id=room.room_id,
            title=room.title,
            description=room.description,
            password=room.password,
            max_participants=room.max_participants,
            is_live=room.is_live,
            participant_url=room.get_room_url(base_url),
            presenter_url=room.get_presenter_url(base_url),
            created_at=room.created_at.isoformat(),
            started_at=(room.started_at.isoformat()
                        if room.started_at else None),
            ended_at=room.ended_at.isoformat() if room.ended_at else None,
            participant_count=len(ROOM_PARTICIPANTS.get(room.room_id, set())),
            max_concurrent_participants=room.max_concurrent_participants,
            duration_ms=room.total_duration_ms
        ))
    
    return sorted(rooms, key=lambda r: r.created_at, reverse=True)


@app.get("/api/rooms/{room_id}", response_model=RoomResponse)
async def get_room(room_id: str, request: Request) -> RoomResponse:
    """Get details of a specific room."""
    room = await AsyncDatabaseService.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    base_url = resolve_base_url(request)
    
    return RoomResponse(
        room_id=room.room_id,
        title=room.title,
        description=room.description,
        password=room.password,
        max_participants=room.max_participants,
        is_live=room.is_live,
        participant_url=room.get_room_url(base_url),
        presenter_url=room.get_presenter_url(base_url),
        created_at=room.created_at.isoformat(),
        started_at=(room.started_at.isoformat()
                    if room.started_at else None),
        ended_at=room.ended_at.isoformat() if room.ended_at else None,
        participant_count=len(ROOM_PARTICIPANTS.get(room.room_id, set())),
        max_concurrent_participants=room.max_concurrent_participants,
        duration_ms=room.total_duration_ms
    )


@app.get("/api/rooms/{room_id}/stats")
async def get_room_stats(room_id: str):
    """Get real-time statistics for a room."""
    room = await AsyncDatabaseService.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    # Get current participant count
    current_participants = ROOM_PARTICIPANTS.get(room_id, set())
    
    # Get segment count from presenter session if active
    segments = 0
    presenter_id = room.presenter_session_id
    if presenter_id and presenter_id in ACTIVE_SESSIONS:
        session_state = ACTIVE_SESSIONS[presenter_id]
        if hasattr(session_state, 'transcript') and session_state.transcript:
            segments = len(session_state.transcript._segments)
    
    return {
        "room_id": room_id,
        "participant_count": len(current_participants),
        "active_participants": len(current_participants),
        "max_concurrent_participants": room.max_concurrent_participants,
        "segments": segments,
        "is_live": room.is_live,
        "duration_ms": room.total_duration_ms,
        "status": "live" if room.is_live else "inactive"
    }


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


# Platform Analytics Endpoints
@app.get("/api/analytics/platform")
async def get_platform_analytics(hours: int = 24):
    """Get platform-wide analytics."""
    try:
        # Get total rooms count
        total_rooms = len(await AsyncDatabaseService.get_all_rooms())
        
        # Mock data for now - you can implement actual analytics later
        return JSONResponse(content={
            "status": "success",
            "total_rooms": total_rooms,
            "active_rooms": 0,
            "total_participants": 0,
            "total_sessions": 0,
            "events": [],
            "participant_timeline": [],
            "hours": hours
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


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


@app.get("/api/rooms/{room_id}/subtitles")
async def get_room_subtitles(room_id: str):
    """Get all subtitle segments for a room (for late joiners)"""
    try:
        from .db_service import AsyncDatabaseService
        
        # Get all subtitle segments for the room
        subtitles = await AsyncDatabaseService.get_room_subtitle_segments(room_id)
        
        # Format as timeline data
        timeline_data = []
        for subtitle in subtitles:
            timeline_data.append({
                "segmentId": subtitle.segment_id,
                "startMs": subtitle.timestamp_ms,
                "endMs": subtitle.timestamp_ms + subtitle.duration_ms,
                "text": subtitle.text_en or "",
                "thai": subtitle.text_th or "",
                "confidence": subtitle.confidence_en or 0.0,
                "processingMs": subtitle.processing_time_ms or 0,
                "isPartial": False,
                "isFinal": subtitle.is_final
            })
        
        return {
            "room_id": room_id,
            "subtitles": timeline_data,
            "total_segments": len(timeline_data)
        }
        
    except Exception as e:
        get_logger().error(f"Error getting subtitles for {room_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/rooms/{room_id}/audio/files")
async def get_room_audio_files_api(room_id: str):
    """Get list of audio files for a room"""
    try:
        files = await get_room_audio_files(settings.audio_storage_path, room_id)
        return {
            "room_id": room_id,
            "files": files,
            "total_files": len(files)
        }
    except Exception as e:
        get_logger().error(f"Error getting audio files for {room_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/rooms/{room_id}/audio/{segment_id}/{language}")
async def get_audio_file(room_id: str, segment_id: int, language: str):
    """Stream audio file for a specific segment"""
    try:
        file_path = get_audio_file_path(
            settings.audio_storage_path, room_id, segment_id, language
        )
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        # Check file size
        file_size = os.path.getsize(file_path)
        max_size = settings.max_audio_file_size_mb * 1024 * 1024
        if file_size > max_size:
            raise HTTPException(
                status_code=413,
                detail=f"Audio file too large: {file_size} bytes"
            )
        
        return FileResponse(
            path=file_path,
            media_type='audio/wav',
            filename=get_audio_filename(room_id, segment_id, language)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        get_logger().error(f"Error serving audio file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/rooms/{room_id}/audio/playlist")
async def get_room_audio_playlist(room_id: str):
    """Get chronological playlist of all audio files for room playback"""
    try:
        files = await get_room_audio_files(settings.audio_storage_path, room_id)
        
        # Group by segment_id and create playlist entries
        playlist = []
        segments = {}
        
        for file_info in files:
            seg_id = file_info['segment_id']
            if seg_id not in segments:
                segments[seg_id] = {
                    'segment_id': seg_id,
                    'files': {}
                }
            segments[seg_id]['files'][file_info['language']] = {
                'url': f"/api/rooms/{room_id}/audio/{seg_id}/"
                       f"{file_info['language']}",
                'size': file_info['size'],
                'filename': file_info['filename']
            }
        
        # Convert to sorted playlist
        for seg_id in sorted(segments.keys()):
            playlist.append(segments[seg_id])
        
        return {
            "room_id": room_id,
            "playlist": playlist,
            "total_segments": len(playlist)
        }
        
    except Exception as e:
        get_logger().error(f"Error creating audio playlist for {room_id}: {e}")
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
    audio_segment_counter: int = 0

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

    # Wait for and process config message immediately after connection
    try:
        config_message = await asyncio.wait_for(websocket.receive(), timeout=5.0)
        
        if "text" in config_message and config_message["text"]:
            try:
                config_data = json.loads(config_message["text"])
                
                if config_data.get("type") == "config":
                    sr = config_data.get("sampleRate")
                    room_id = config_data.get("roomId")
                    
                    # Link session to room if roomId provided
                    if room_id:
                        room = await AsyncDatabaseService.get_room(room_id)
                        if room:
                            state.room_id = room_id
                            # Always update presenter session with current session ID
                            await AsyncDatabaseService.update_presenter_session(
                                room_id, sess_id
                            )
                            get_logger().info(
                                f"✅ PRESENTER linked session {sess_id} to room {room_id} - subtitles will be saved"
                            )
                            
                            # Send confirmation back to client
                            await websocket.send_text(json.dumps({
                                "type": "status",
                                "message": f"Connected to room {room_id} - subtitles will be saved",
                                "room_linked": True,
                                "session_id": sess_id
                            }))
                        else:
                            get_logger().error(
                                f"❌ Room {room_id} not found - subtitles will NOT be saved"
                            )
                            await websocket.send_text(json.dumps({
                                "type": "error",
                                "message": f"Room {room_id} not found",
                                "room_linked": False
                            }))
                    else:
                        get_logger().warning(
                            f"⚠️  No roomId provided in config - subtitles will NOT be saved"
                        )
                    
                    if isinstance(sr, int) and sr > 0:
                        state.sample_rate = sr
                        
            except json.JSONDecodeError:
                pass  # Continue with default settings if config parsing fails
    except asyncio.TimeoutError:
        pass  # Continue with default settings if no config received

    vad = VoiceActivityDetector(
        sample_rate=state.sample_rate,
        aggressiveness=3,  # Most aggressive noise filtering (0-3)
        padding_duration_ms=200  # Shorter padding to reduce false speech detection
    )
    asr_stream: Optional[ASRStream] = None

    async def forward_results(stream: ASRStream) -> None:
        nonlocal state
        print(f"DEBUG: forward_results function called for session {sess_id}")
        try:
            print(f"DEBUG: About to log forward_results_starting")
            jsonify_log("forward_results_starting",
                        message=f"🎯 Starting forward_results for session {sess_id}",
                        stream_type=type(stream).__name__)
            print(f"DEBUG: Logged forward_results_starting successfully")
            result_count = 0
            async for result in stream.results():
                result_count += 1
                jsonify_log("INFO", {
                    "message": f"� GOT RESULT for session {sess_id}",
                    "text": (result.text[:50] + "..." 
                            if len(result.text) > 50 else result.text),
                    "is_final": result.is_final,
                    "has_text": bool(result.text.strip())
                })
                english_text = result.text.strip()
                if not english_text:
                    continue
                
                # TARGETED FILTER: Block pure disclaimer content (not normal speech containing keywords)
                full_disclaimer_patterns = [
                    "please see the complete disclaimer at https://sites.google.com",
                    "please see the complete disclaimer at sites.google.com",
                    "see the complete disclaimer at https://sites.google.com",
                    "see the complete disclaimer at sites.google.com"
                ]
                # Only block if the entire text is primarily disclaimer content (>80% match)
                is_pure_disclaimer = any(
                    pattern in english_text.lower() and 
                    len(pattern) / len(english_text) > 0.8
                    for pattern in full_disclaimer_patterns
                )
                if is_pure_disclaimer:
                    # Log blocked content for debugging
                    jsonify_log("WARNING", {
                        "message": "Blocked pure disclaimer content",
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
                
                # Check if ASR already provided Thai translation
                is_already_thai = (
                    result.raw and 
                    result.raw.get("language") == "th" and 
                    result.raw.get("type") == "translation"
                )
                
                if is_already_thai:
                    # ASR provider already translated to Thai
                    await send({"type": "status", "status": "ready"})
                    thai_text = english_text  # The "english_text" is actually Thai
                    source_english = result.raw.get("source", "")
                    message = {
                        "type": "partial" if not result.is_final else "final",
                        "sessionId": sess_id,
                        "segmentId": result.segment_id or f"{sess_id}-{result.end_ms}",
                        "english": source_english,
                        "thai": thai_text,
                        "timestamp_ms": result.end_ms or utc_timestamp_ms(),
                        "provider": {
                            "asr": ASR_PROVIDER.name,
                            "mt": "built_in",
                        },
                    }
                    
                    # Add audio synthesis for final results (both Thai and English)
                    if result.is_final:
                        try:
                            audio_dict = {}
                            
                            # Generate Thai audio
                            if thai_text:
                                thai_audio_data = await synthesize_thai_audio_base64(thai_text)
                                if thai_audio_data:
                                    audio_dict["thai_audio_base64"] = thai_audio_data
                            
                            # Generate English audio
                            if source_english:
                                english_audio_data = await synthesize_english_audio_base64(source_english)
                                if english_audio_data:
                                    audio_dict["english_audio_base64"] = english_audio_data
                            
                            if audio_dict:
                                message["audio"] = {
                                    **audio_dict,
                                    "audio_format": "mp3",
                                    "voice": "nova"
                                }
                                
                                # Save audio files for timeline
                                segment_id = result.segment_id or \
                                    f"{sess_id}-{result.end_ms}"
                                
                                # Save Thai audio if available
                                if thai_audio_data:
                                    thai_path = get_audio_file_path(
                                        settings.audio_storage_path, sess_id,
                                        hash(segment_id) % 1000000, "th"
                                    )
                                    await save_thai_audio_to_file(
                                        thai_audio_data, thai_path, "mp3"
                                    )
                                
                                # Save English audio if available  
                                if english_audio_data:
                                    eng_path = get_audio_file_path(
                                        settings.audio_storage_path, sess_id,
                                        hash(segment_id) % 1000000, "en"
                                    )
                                    await save_thai_audio_to_file(
                                        english_audio_data, eng_path, "mp3"
                                    )
                                
                        except Exception as e:
                            jsonify_log("WARNING", {
                                "message": "Failed to add audio to message",
                                "error": str(e)
                            })
                else:
                    # Use MT provider for translation
                    await send({"type": "status", "status": "translating"})
                    translation = await MT_PROVIDER.translate(
                        english_text, is_final=result.is_final
                    )
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
                    
                    # Add audio synthesis for final results (both Thai and English)
                    if result.is_final:
                        try:
                            audio_dict = {}
                            
                            # Generate Thai audio
                            if translation.text:
                                thai_audio_data = await synthesize_thai_audio_base64(
                                    translation.text
                                )
                                if thai_audio_data:
                                    audio_dict["thai_audio_base64"] = thai_audio_data
                            
                            # Generate English audio
                            if english_text:
                                english_audio_data = await synthesize_english_audio_base64(
                                    english_text
                                )
                                if english_audio_data:
                                    audio_dict["english_audio_base64"] = english_audio_data
                            
                            if audio_dict:
                                message["audio"] = {
                                    **audio_dict,
                                    "audio_format": "mp3",
                                    "voice": "nova"
                                }
                                
                                # Save audio files for timeline
                                segment_id = result.segment_id or \
                                    f"{sess_id}-{result.end_ms}"
                                
                                # Save Thai audio if available
                                if thai_audio_data:
                                    thai_path = get_audio_file_path(
                                        settings.audio_storage_path, sess_id,
                                        hash(segment_id) % 1000000, "th"
                                    )
                                    await save_thai_audio_to_file(
                                        thai_audio_data, thai_path, "mp3"
                                    )
                                
                                # Save English audio if available
                                if english_audio_data:
                                    eng_path = get_audio_file_path(
                                        settings.audio_storage_path, sess_id,
                                        hash(segment_id) % 1000000, "en"
                                    )
                                    await save_thai_audio_to_file(
                                        english_audio_data, eng_path, "mp3"
                                    )
                                
                        except Exception as e:
                            jsonify_log("WARNING", {
                                "message": "Failed to add audio to message",
                                "error": str(e)
                            })
                await send(message)
                # Broadcast to any registered followers for this session
                followers = SESSION_FOLLOWERS.get(sess_id)
                if followers:
                    for q in list(followers):
                        with contextlib.suppress(Exception):
                            await q.put(message)
                
                # Broadcast to room participants if this session is a presenter
                active_rooms = await AsyncDatabaseService.get_active_rooms()
                jsonify_log("DEBUG", {
                    "message": f"🔍 Checking broadcast for session {sess_id}",
                    "active_rooms_count": len(active_rooms),
                    "rooms": [f"{r.room_id}:{r.presenter_session_id[:8]}"
                              for r in active_rooms]
                })
                for room in active_rooms:
                    if room.presenter_session_id == sess_id:
                        participants = ROOM_PARTICIPANTS.get(
                            room.room_id, set()
                        )
                        jsonify_log("INFO", {
                            "message": f"🔊 Broadcasting to {len(participants)} participants in room {room.room_id}",
                            "session": sess_id,
                            "text": message.get("thai", "")[:50] + "..."
                        })
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
                            get_logger().debug(
                                f"💾 Saving subtitle segment to database for room {state.room_id}"
                            )
                            # Save subtitle segment
                            await AsyncDatabaseService.save_subtitle_segment(
                                room_id=state.room_id,
                                segment_id=message.get("segmentId", ""),
                                timestamp_ms=message.get("timestamp_ms", 0),
                                duration_ms=0,  # Duration not available in this context
                                sequence_number=len(
                                    state.transcript._segments
                                ),
                                text_en=message.get("english", ""),
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
                            
                            # Generate and save Thai audio placeholder
                            if message.get("thai"):
                                segment_id = state.audio_segment_counter
                                thai_audio_file_path = os.path.join(
                                    settings.audio_storage_path,
                                    state.room_id,
                                    f"{segment_id:06d}_th.wav"
                                )
                                
                                # Estimate duration from English text
                                english_text = message.get("english", "")
                                # ~100ms per character
                                estimated_duration_ms = len(english_text) * 100
                                # Clamp to 0.5-10 seconds
                                estimated_duration_ms = max(
                                    500, min(10000, estimated_duration_ms)
                                )
                                
                                # Synthesize Thai audio using TTS
                                thai_audio_saved = await (
                                    synthesize_thai_audio(
                                        message.get("thai", ""),
                                        thai_audio_file_path,
                                        state.sample_rate
                                    )
                                )
                                
                                if thai_audio_saved:
                                    # Create unique segment ID with timestamp to prevent duplicates
                                    import time
                                    unique_audio_id = f"{sess_id}-{int(time.time() * 1000)}-{segment_id}"
                                    
                                    # Save Thai audio metadata to database
                                    await (
                                        AsyncDatabaseService.save_audio_segment(
                                            room_id=state.room_id,
                                            segment_id=unique_audio_id,
                                            timestamp_ms=message.get(
                                                "timestamp_ms", 0
                                            ),
                                            duration_ms=estimated_duration_ms,
                                            sequence_number=segment_id,
                                            audio_data=b"",
                                            audio_language="th",
                                            sample_rate=state.sample_rate,
                                            channels=1,
                                            format="wav",
                                            file_path=thai_audio_file_path
                                        )
                                    )
                        except Exception as e:
                            get_logger().error(f"Failed to save subtitle: {e}")
                    
                    await send({"type": "status", "status": "listening"})
        except asyncio.CancelledError:
            jsonify_log("INFO", {
                "message": f"🛑 forward_results cancelled for session {sess_id}",
                "results_processed": result_count
            })
        except Exception as e:
            jsonify_log("ERROR", {
                "message": f"💥 Exception in forward_results for session {sess_id}",
                "error": str(e),
                "type": type(e).__name__,
                "results_processed": result_count
            })
            raise

    results_task: Optional[asyncio.Task] = None

    try:
        jsonify_log("asr_stream_creating",
                    message=f"🎙️ Creating ASR stream for session {sess_id}",
                    provider=ASR_PROVIDER.name,
                    sample_rate=state.sample_rate)
        asr_stream = await ASR_PROVIDER.create_stream(sess_id, state.sample_rate)
        jsonify_log("asr_stream_created",
                    message=f"✅ ASR stream created, starting results task")
        try:
            print(f"DEBUG: About to create forward_results task for session {sess_id}")
            results_task = asyncio.create_task(forward_results(asr_stream))
            print(f"DEBUG: Task created successfully for session {sess_id}")
        except Exception as e:
            print(f"DEBUG: Failed to create task: {e}")
            raise
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
                jsonify_log("INFO", {
                    "message": f"📨 Received message for session {sess_id}",
                    "type": kind,
                    "data_keys": list(data.keys()) if isinstance(data, dict) else "not_dict"
                })
                if kind == "config":
                    sr = data.get("sampleRate")
                    room_id = data.get("roomId")
                    
                    jsonify_log("DEBUG", {
                        "message": "📡 Config message received",
                        "session": sess_id,
                        "room_id": room_id,
                        "sample_rate": sr
                    })
                    
                    # Link session to room if roomId provided
                    if room_id:
                        room = await AsyncDatabaseService.get_room(room_id)
                        if room:
                            state.room_id = room_id
                            # For participants, don't override presenter session
                            # Only update if no presenter session exists
                            if not room.presenter_session_id:
                                await AsyncDatabaseService.update_presenter_session(
                                    room_id, sess_id
                                )
                                get_logger().info(
                                    f"🔗 PARTICIPANT linked as presenter for room {room_id}"
                                )
                            else:
                                get_logger().info(
                                    f"👥 PARTICIPANT joined room {room_id} (presenter: {room.presenter_session_id})"
                                )
                            
                            # Send room info to participant
                            await websocket.send_text(json.dumps({
                                "type": "room_info",
                                "room_id": room_id,
                                "title": room.title,
                                "is_live": room.is_live
                            }))
                    
                    if isinstance(sr, int) and sr > 0:
                        jsonify_log("INFO", {
                            "message": f"🔧 Updating sample rate for session {sess_id}",
                            "old_rate": state.sample_rate,
                            "new_rate": sr
                        })
                        state.sample_rate = sr
                        vad = VoiceActivityDetector(
                            sample_rate=state.sample_rate,
                            aggressiveness=3,  # Most aggressive filtering
                            padding_duration_ms=200
                        )
                        if asr_stream:
                            jsonify_log("INFO", {
                                "message": f"🔄 Recreating ASR stream for session {sess_id}",
                                "sample_rate": state.sample_rate
                            })
                            # recreate stream with new rate
                            await asr_stream.finalize()
                            if results_task:
                                results_task.cancel()
                            asr_stream = await ASR_PROVIDER.create_stream(sess_id, state.sample_rate)
                            results_task = asyncio.create_task(forward_results(asr_stream))
                        else:
                            jsonify_log("WARNING", {
                                "message": f"⚠️ No existing ASR stream to recreate for session {sess_id}"
                            })
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
            
            # Save audio chunk to file and database if linked to room
            if state.room_id:
                try:
                    # Ensure audio storage directory exists
                    await ensure_audio_directory(settings.audio_storage_path)
                    
                    # Increment segment counter for sequential IDs
                    state.audio_segment_counter += 1
                    segment_id = state.audio_segment_counter
                    
                    # Save English audio chunk to file
                    audio_file_path = get_audio_file_path(
                        settings.audio_storage_path,
                        state.room_id,
                        segment_id,
                        "en"
                    )
                    
                    # Save to file (async)
                    audio_saved = await save_audio_to_file(
                        chunk, audio_file_path, state.sample_rate
                    )
                    
                    # Create unique segment ID with timestamp to prevent duplicates
                    import time
                    unique_audio_id = f"{sess_id}-{int(time.time() * 1000)}-{segment_id}"
                    
                    # Save metadata to database with file path
                    await AsyncDatabaseService.save_audio_segment(
                        room_id=state.room_id,
                        segment_id=unique_audio_id,
                        timestamp_ms=timestamp,
                        duration_ms=(len(chunk) * 1000 //
                                     (state.sample_rate * 2)),
                        sequence_number=segment_id,
                        # Empty if saved to file
                        audio_data=chunk if not audio_saved else b"",
                        audio_language="en",
                        sample_rate=state.sample_rate,
                        channels=1,
                        format="wav",
                        file_path=audio_file_path if audio_saved else None
                    )
                except Exception as e:
                    # Log significant errors but don't spam
                    if timestamp % 10000 == 0:  # Log every ~10 seconds
                        get_logger().error(f"Audio save error: {e}")
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
        
        # Clear presenter session from database if this was a presenter
        if hasattr(state, 'room_id') and state.room_id:
            try:
                # Only clear if this session was the current presenter
                room = await AsyncDatabaseService.get_room(state.room_id)
                if room and room.presenter_session_id == sess_id:
                    await AsyncDatabaseService.update_presenter_session(
                        state.room_id, None
                    )
                    get_logger().info(
                        f"Cleared presenter session for room {state.room_id}"
                    )
            except Exception as e:
                get_logger().error(f"Error clearing presenter session: {e}")
        
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


# Helper methods moved to AsyncDatabaseService for proper async handling
