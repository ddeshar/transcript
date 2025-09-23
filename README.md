# English → Thai Realtime Subtitle App

Production-oriented demo that captures microphone audio in the browser, streams it to a FastAPI backend, performs streaming ASR (English) and machine translation (English→Thai), and renders Thai subtitles with live updates. The stack is designed for <1.5 s latency on a laptop using offline models, with pluggable cloud fallbacks.

## Features
- Streaming audio capture via browser microphone (Web Audio) and WebSockets.
- Offline, low-latency ASR using Vosk (default) or Whisper.cpp; cloud Whisper API optional.
- Offline translation via Helsinki-NLP MarianMT, or cloud (Google Translate / AWS Translate).
- Word-by-word partials with rapid updates, finalized lines carry timestamps and persist per session.
- Responsive UI (no build step) with adjustable caption size, English preview toggle, status chip, Start/Stop/Clear/Save controls.
- Download UTF-8 transcript (`.txt`) with timestamps and Thai lines.
- VAD-based segmentation (python-webrtcvad) to shorten end-to-end latency.
- Docker one-command startup (`docker-compose up --build`) plus local scripts for models/tests.
- Structured JSON logging with session IDs (see backend utils).

## Prerequisites
- Docker & Docker Compose v2
- macOS/Linux with Python 3.11+ if you plan to run scripts locally (optional)
- ~6 GB free disk (models, Docker layers)

## Repo Layout
```
.
├── backend/               # FastAPI app + provider implementations
├── frontend/              # Static assets (index, JS, CSS)
├── scripts/               # Model downloader & simulator
├── models/                # Populated by download script
├── sample_audio/          # Short English WAV sample
├── docker/                # Dockerfiles + compose definition
├── .env.example
├── docker-compose.yml     # Extends docker/docker-compose.yml
└── README.md
```

## Quick Start (Docker)
1. Copy env template and adjust if needed:
   ```bash
   cp .env.example .env
   ```
2. Download offline models (run once, host or container):
   ```bash
   python scripts/download_models.py
   ```
   > Downloads Vosk (`vosk-model-small-en-us-0.15`), Whisper.cpp `ggml-small.en.bin`, and MarianMT model into `./models`.
3. Build & launch:
   ```bash
   docker-compose up --build
   ```
4. Open [http://localhost:8000](http://localhost:8000), grant mic access, and click **Start**.

The UI streams audio to `/ws/transcribe`, displays partial Thai captions almost instantly, and finalizes with timestamps. Click **Save (.txt)** to download the transcript.

## Switching Providers
Environment variables control providers (set in `.env`). Restart the stack after changes.

| Variable | Options | Notes |
| --- | --- | --- |
| `ASR_PROVIDER` | `vosk` (default), `whispercpp`, `whisper_api` | `whisper_api` uses OpenAI Whisper, supply `OPENAI_API_KEY`. |
| `MT_PROVIDER` | `marian` (default), `gtranslate`, `awstranslate` | Cloud providers pull credentials from standard env vars. |
| `VOSK_MODEL_DIR` | Path to Vosk model directory | Set automatically by download script. |
| `WHISPER_CPP_MODEL_PATH` | Path to `ggml-*.bin` file | Required for Whisper.cpp mode. |
| `MARIAN_MODEL_DIR` | Local MarianMT snapshot path | Defaults to `models/marian`. |

### Cloud Credentials
- **OpenAI Whisper API**: set `OPENAI_API_KEY` and optionally `OPENAI_WHISPER_MODEL`.
- **Google Translate**: set `MT_PROVIDER=gtranslate`, `GCP_PROJECT`, and `GOOGLE_APPLICATION_CREDENTIALS` pointing to service account JSON.
- **AWS Translate**: set `MT_PROVIDER=awstranslate`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, and `AWS_SECRET_ACCESS_KEY`.

## Local Development Tips
- Install Python deps locally if you want to run without Docker:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r backend/requirements.txt
  python scripts/download_models.py
  uvicorn backend.app:app --reload
  ```
- Serve frontend by visiting [`http://localhost:8000`](http://localhost:8000); static assets are bundled with FastAPI.

## Testing & Simulation
- Automated test coverage is minimal; manual smoke tests are recommended.
- Use the included WAV sample to simulate mic input:
  ```bash
  python scripts/simulate_client.py --audio sample_audio/en_sample.wav
  ```
  Observe partial/final logs in the terminal.

## Performance Notes
- **CPU vs GPU**: MarianMT runs on CPU by default. Running inside Docker on machines with GPUs requires additional setup (e.g., `nvidia/cuda` base image, `--gpus all`).
- **Model choices**: For faster ASR, swap Vosk model for `vosk-model-small-en-us-0.15`. For higher accuracy with more compute, use Whisper.cpp `medium.en` (update env path accordingly).
- **Chunking**: Web Audio pipeline downsamples to 16 kHz PCM and chunks ~256 ms; adjust `TARGET_SAMPLE_RATE` or buffer size in `frontend/app.js` if needed.
- **VAD tuning**: `MIN_SILENCE_MS` env var controls how quickly segments finalize.

## Troubleshooting
- **No microphone audio**: Ensure browser permissions are granted. Reload page after granting.
- **Slow translations**: MarianMT is CPU-heavy; consider running `MT_PROVIDER=gtranslate` with cloud credentials.
- **Docker build failures**: Confirm sufficient RAM/disk. If model download fails inside container, run `scripts/download_models.py` on host and retry.
- **Transcript button disabled**: Button enables after first finalized line; speak a sentence before saving.
- **Thai rendering**: The UI uses system fonts; install Noto Sans Thai for improved glyph coverage if characters look clipped.

## Security
- WebSocket endpoint accepts audio only; CORS defaults to `http://localhost:8000`.
- Cloud API keys stay on the server—never shipped to the browser.
- Add HTTPS/Authentication in front of FastAPI for production deployments (left as stretch).

## License
MIT License – see [LICENSE](LICENSE).
