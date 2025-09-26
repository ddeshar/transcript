# Archive Directory

This directory contains files that have been moved from the main project to keep the codebase clean and focused on the seminar platform functionality.

## Files Moved (Date: September 26, 2025)

### Frontend Files (`./frontend/`)

- `provider-config.html` - Unused HTML file with no routes or references in the application

### Backend Files (`./backend/providers/`)

- `asr_aws_transcribe.py` - AWS Transcribe ASR provider that is not imported or used in the current provider system

### Development Files (`./development/`)

- `compare_performance.py` - Performance comparison script for different ASR approaches
- `test_all_approaches.py` - Test script for comparing ASR providers
- `test_optimized_system.py` - Performance testing utility
- `test_server.py` - Simple frontend-only test server
- `test_faster_whisper.py` - Standalone faster-whisper testing script
- `test_aws_setup.py` - AWS configuration testing utility
- `test_audio_storage.py` - Audio recording and storage testing script
- `test_openai_setup.py` - Empty OpenAI setup test file
- `convert_marian_to_ctranslate2.py` - Corrupted model conversion script

### Docker Alternative Setup (`./docker-alternative/`)

- `docker-compose.yml` - Alternative Docker Compose configuration with bind mounts and separate frontend service

## Rationale

These files were moved to archive because:

1. **Unused Frontend Files**: No routes or references found in the application
2. **Unused Backend Providers**: Not imported in the provider system
3. **Development Tools**: Test scripts and utilities used during development but not needed for production
4. **Corrupted Files**: Files with parsing errors or incomplete implementations
5. **Duplicate Docker Setup**: Alternative Docker configuration with different volume mounting strategy

## Recovery

If any of these files are needed in the future, they can be moved back to their original locations. The file structure has been preserved to make recovery straightforward.