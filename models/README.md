# Models

Models are downloaded by running `python scripts/download_models.py`. The script fetches:

- **Vosk streaming ASR** (`vosk-model-small-en-us-0.15`) into `models/vosk/`
- **Whisper.cpp English model** (`ggml-small.en.bin`) into `models/whisper.cpp/`
- **Helsinki-NLP MarianMT en→th** into `models/marian/`

These locations line up with the defaults expected by the application.
