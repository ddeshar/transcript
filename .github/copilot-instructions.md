# AI Coding Assistant Instructions

This is a real-time English-to-Thai subtitle application with WebSocket streaming, offline ML models, and pluggable cloud providers.

## Architecture Overview

**Core Data Flow**: Browser microphone → WebSocket → ASR Provider → MT Provider → Thai subtitles
- Frontend: Vanilla JS with Web Audio API streaming 16kHz PCM chunks to `/ws/transcribe`
- Backend: FastAPI with async WebSocket handling, pluggable provider architecture
- Models: Offline-first (Vosk ASR + MarianMT), cloud fallbacks (OpenAI Whisper, Google/AWS Translate)

**Key Components**:
- `backend/app.py`: Main WebSocket endpoint with session management and audio streaming
- `backend/providers/`: Plugin architecture for ASR (`asr_*.py`) and MT (`mt_*.py`) providers
- `backend/vad.py`: Voice Activity Detection for segment boundaries
- `frontend/app.js`: Audio capture, WebSocket client, and live subtitle rendering

## Provider Architecture

All providers implement base classes (`ASRProvider`/`MTProvider`) with async `setup()` and pluggable instantiation via `create_*_provider()` factories in `providers/__init__.py`.

**ASR Providers**:
- `vosk`: Streaming recognition via `VoskASRProvider` (default, offline)
- `whispercpp`: Local Whisper.cpp bindings 
- `whisper_api`: OpenAI cloud API

**MT Providers**:
- `marian`: Helsinki-NLP MarianMT models (default, offline)
- `gtranslate`: Google Cloud Translate
- `awstranslate`: AWS Translate

Switch providers via env vars (`ASR_PROVIDER`, `MT_PROVIDER`) - see `.env.example` for all options.

## Development Workflows

**Setup**: Always run `python scripts/download_models.py` first to download offline models (~6GB)

**Local Development**:
```bash
# Full Docker stack (preferred)
docker-compose up --build

# Local Python backend only
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app:app --reload
```

**Testing Audio Pipeline**: Use `scripts/simulate_client.py --audio sample_audio/en_sample.wav` to test without microphone

**Model Management**: Models auto-download to `models/` with expected directory structure:
- `models/vosk/vosk-model-small-en-us-0.15/`
- `models/whisper.cpp/ggml-small.en.bin`
- `models/marian/` (HuggingFace snapshot)

## Critical Patterns

**WebSocket Message Flow**: 
- Client sends binary audio chunks + JSON control messages (`{"type": "control", "action": "clear"}`)
- Server responds with typed messages: `partial`/`final` transcriptions, `status` updates, `transcript` export

**Session Management**: Each WebSocket gets a UUID session via `utils.session_id()`, stored in `SessionTranscript` for export

**Async Streaming**: `ASRStream.results()` yields `ASRResult` objects; main loop forwards to MT provider and client in `forward_results()`

**VAD Integration**: `VoiceActivityDetector` processes audio chunks and triggers `mark_segment_end()` on silence detection

**Error Handling**: Use `contextlib.suppress()` for WebSocket cleanup; structured logging via `utils.jsonify_log()`

## Common Issues & Debugging

**Model Loading Failures**: Most startup errors relate to missing model files. Check:
- `models/vosk/vosk-model-small-en-us-0.15/` contains actual model files (not just empty dirs)
- `models/whisper.cpp/ggml-small.en.bin` exists and is not corrupted
- MarianMT models downloaded to `models/marian/` via HuggingFace

**Docker Issues**:
- Backend: Import errors fixed by setting `PYTHONPATH=/app` and `WORKDIR /app`, then running `uvicorn backend.app:app`
- Frontend: Static files served via FastAPI at `/static/*` path - ensure HTML references match serving method

**Static File Serving**: FastAPI serves frontend files via `/static` mount; Docker nginx setup creates separate frontend container on port 5173

**Testing Without Models**: Use `python3 -m http.server` in `frontend/` for UI testing without backend dependencies

## Configuration Conventions

Environment variables control all provider selection and model paths. The `Settings` class uses Pydantic with `Field(alias=...)` for env var mapping.

Provider credentials follow standard conventions:
- OpenAI: `OPENAI_API_KEY`
- Google: `GOOGLE_APPLICATION_CREDENTIALS` (service account JSON path)
- AWS: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`

Frontend audio settings in `app.js`: `TARGET_SAMPLE_RATE = 16000`, adjustable chunk sizes for latency tuning.

## CSS & Frontend Notes

The frontend uses a modern dark theme with:
- CSS custom properties (variables) for consistent theming
- Responsive design with `clamp()` for scalable typography
- Status indicators with color-coded backgrounds for real-time feedback
- Smooth transitions and hover effects for better UX

The CSS is fully functional and styled for the subtitle application - if styles appear broken, check static file serving paths.